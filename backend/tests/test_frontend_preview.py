"""Real React + headless browser preview flow; local fake data, no LLM network or frame files."""

import asyncio
import contextlib
import json
import os
import signal
import socket
from collections.abc import Callable
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import httpx
import pytest
from playwright.async_api import Page, Route, async_playwright, expect

import app.runtime as runtime
from app.browser.playwright_driver import PlaywrightDriver
from app.config import Settings
from app.core.events import Action, Mode
from app.core.state import RunStatus
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import BrowserDriver, PreviewChannel
from app.interfaces.llm import LLMResponse, Message, T
from app.main import create_app
from app.preview.cdp import CdpScreencastChannel
from app.preview.factory import create_preview_channel
from app.preview.hub import PreviewHub
from app.preview.input_protocol import Input, Mouse
from app.preview.input_relay import CdpInputRelay
from app.runtime import RunService
from tests.settings import IsolatedSettings
from tests.test_preview_browser_ws import serve
from tests.test_takeover_state import wait_status

ROOT = Path(__file__).resolve().parents[2]


async def wait_until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(8):
        for _ in range(400):
            if predicate():
                return
            await asyncio.sleep(0.02)
        raise AssertionError("Preview condition did not become true")


async def click_source(viewer: Page, driver: PlaywrightDriver, selector: str) -> None:
    box = await driver.get_active_page().locator(selector).bounding_box()
    canvas = await viewer.locator("canvas").bounding_box()
    assert box and canvas
    viewport = driver.get_viewport()
    await viewer.mouse.click(
        canvas["x"] + (box["x"] + box["width"] / 2) * canvas["width"] / viewport["width"],
        canvas["y"] + (box["y"] + box["height"] / 2) * canvas["height"] / viewport["height"],
    )


@pytest.mark.parametrize("scale", [1, 2])
async def test_one_frontend_preview_navigation_popup_recovery_and_takeover(
    testsite: str, scale: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The real frontend uses an isolated ephemeral Vite proxy, leaving operator servers untouched.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        front_port = probe.getsockname()[1]
    origin = f"http://127.0.0.1:{front_port}"
    settings = IsolatedSettings(
        frontend_origin=origin,
        device_scale_factor=scale,
        screencast_quality=90,
        takeover_max_seconds=60,
        input_idle_timeout_s=60,
    )
    modes: list[Mode] = []

    class CheckedDriver(PlaywrightDriver):
        async def start(self, mode: Mode) -> None:
            modes.append(mode)
            assert mode == "headless", "Frontend must never launch a visible agent window"
            await super().start(mode)

    driver = CheckedDriver(settings)
    handoff_ready = asyncio.Event()

    class HeldHandoffLLM(FakeLLMClient):
        async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
            response = await super().propose(messages, schema)
            if isinstance(response.parsed, Action) and response.parsed.action == "handoff":
                await handoff_ready.wait()
            return response

    llm = HeldHandoffLLM(
        actions=[
            Action(action="navigate", value=testsite + "/popup.html", rationale="Open local demo."),
            Action(action="handoff", value="Please sign in, then Resume", rationale="Ask a human."),
            Action(action="done", value="Human flow completed", rationale="Complete local task."),
        ],
        delay=0.02,
    )
    channels: list[CdpScreencastChannel] = []
    expected_point: dict[str, float] = {}
    delivered_hits: list[bool] = []
    original_send = CdpInputRelay.send

    async def checked_send(relay: CdpInputRelay, message: Input) -> bool:
        if expected_point and isinstance(message, Mouse) and message.action in {"down", "up"}:
            delivered_hits.append(
                abs(message.x - expected_point["x"]) < 1
                and abs(message.y - expected_point["y"]) < 1
            )
        return await original_send(relay, message)

    monkeypatch.setattr(CdpInputRelay, "send", checked_send)

    def capture(instance: BrowserDriver, hub: PreviewHub, options: Settings) -> PreviewChannel:
        channel = create_preview_channel(instance, hub, options)
        assert isinstance(channel, CdpScreencastChannel)
        channels.append(channel)
        return channel

    monkeypatch.setattr(runtime, "create_preview_channel", capture)
    application = create_app(settings, driver_factory=lambda: driver, llm_factory=lambda: llm)
    service = cast(RunService, application.state.service)
    async with serve(application) as host:
        config = json.dumps(
            {
                "server": {
                    "host": "127.0.0.1",
                    "port": front_port,
                    "strictPort": True,
                    "proxy": {
                        "/api": {
                            "target": "http://" + host,
                            "ws": True,
                            "changeOrigin": True,
                        }
                    },
                }
            }
        )
        script = (
            'import {createServer} from "vite";'
            f"const server=await createServer({config});await server.listen();"
            'process.on("SIGTERM",async()=>{await server.close();process.exit(0)});'
        )
        process = await asyncio.create_subprocess_exec(
            "node",
            "--input-type=module",
            "-e",
            script,
            cwd=ROOT / "front end",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            async with httpx.AsyncClient(trust_env=False) as client:
                for _ in range(150):
                    try:
                        if (await client.get(origin, timeout=0.2)).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.05)
                else:
                    raise AssertionError("Isolated frontend server failed to start")
            async with async_playwright() as manager:
                browser = await manager.chromium.launch(channel="chromium", headless=True)
                try:
                    context = await browser.new_context(
                        viewport={"width": 1900, "height": 1200},
                        device_scale_factor=scale,
                    )

                    async def local_only(route: Route) -> None:
                        if urlsplit(route.request.url).hostname in {"127.0.0.1", "localhost"}:
                            await route.continue_()
                        else:
                            await route.abort()

                    await context.route("**/*", local_only)
                    page = await context.new_page()
                    errors: list[str] = []
                    page.on("pageerror", lambda error: errors.append(type(error).__name__))
                    await page.goto(origin + "/?debug=1", wait_until="domcontentloaded")
                    await page.get_by_role("button", name="CLEVIS COMMAND", exact=True).click()
                    await page.get_by_role("button", name="Parameters", exact=True).click()
                    assert await page.get_by_text("Browser runs inside preview").is_visible()
                    assert await page.get_by_role("button", name="Headless ON").count() == 0
                    await page.get_by_placeholder("Let Clevis handle the workflow.").fill(
                        "Open the local demo and let me sign in"
                    )
                    await page.get_by_role("button", name="Run Task", exact=True).click()
                    await wait_until(lambda: bool(service.tasks))
                    run_id = next(iter(service.tasks))
                    hub = service.preview_hubs[run_id]
                    await wait_until(
                        lambda: (
                            bool(channels)
                            and channels[0].session is not None
                            and channels[0]._valid_frames > 0
                            and not channels[0]._navigation_changed
                            and driver.get_active_page().url.endswith("popup.html")
                            and hub.latest is not None
                        )
                    )
                    # Test screencast recovery before HiDPI human-control fallback begins.
                    channel = channels[0]
                    session = channel.session
                    assert session and hub.latest
                    seq = hub.latest.metadata.seq
                    await session.detach()
                    await wait_until(
                        lambda: channel.session is not None and channel.session is not session
                    )
                    await wait_until(
                        lambda: hub.latest is not None and hub.latest.metadata.seq > seq
                    )
                    handoff_ready.set()
                    await page.get_by_text(
                        "You are in control. The agent is paused", exact=True
                    ).wait_for()
                    await page.get_by_role("button", name="CLEVIS COMMAND", exact=True).click()
                    await page.wait_for_function("document.querySelector('canvas')?.width > 0")
                    assert await page.locator("canvas").count() == 1
                    canvas = page.locator("canvas")
                    assert await canvas.get_attribute("width") == str(1280 * scale)
                    assert await canvas.get_attribute("height") == str(720 * scale)
                    await page.get_by_text("Browser is not accepting input", exact=True).wait_for(
                        state="hidden"
                    )
                    run_id = next(iter(service.tasks))
                    assert modes == ["headless"]
                    assert (await service.store.get(run_id)).mode == "headless"
                    hub = service.preview_hubs[run_id]
                    assert hub.latest
                    first_tab = hub.latest.metadata.tabId
                    await click_source(page, driver, "a[target=_blank]")
                    await wait_until(lambda: len(driver.get_context().pages) == 2)
                    await wait_until(
                        lambda: hub.latest is not None and hub.latest.metadata.tabId != first_tab
                    )
                    assert hub.latest
                    seq = hub.latest.metadata.seq
                    await page.set_viewport_size({"width": 1100, "height": 820})
                    await page.wait_for_function(
                        """() => {
                            const r=document.querySelector('canvas').getBoundingClientRect();
                            return r.width < 1000 && Math.abs(r.width/r.height-1280/720) < .01;
                        }"""
                    )
                    rect = await canvas.bounding_box()
                    assert rect and 0 < rect["width"] <= 1280 and rect["height"] <= 720
                    assert abs(rect["width"] / rect["height"] - 1280 / 720) < 0.01
                    # A dropped controller must be recoverable without resuming the agent.
                    controller = service.controls[run_id]
                    controller.disconnected.set()
                    reconnect = page.get_by_role("button", name="Reconnect control", exact=True)
                    await reconnect.wait_for()
                    await wait_until(lambda: controller.owner is None)
                    await reconnect.click()
                    await page.get_by_text("Browser is not accepting input", exact=True).wait_for(
                        state="hidden"
                    )
                    await reconnect.wait_for(state="hidden")
                    assert (await service.store.get(run_id)).status == RunStatus.PAUSED

                    # Human CDP input must reach a checkbox inside a cross-origin iframe.
                    # Observation remains main-frame-only; the relay never inspects frame DOM.
                    source = driver.get_active_page()
                    assert hub.latest
                    before_iframe = hub.latest.metadata.seq
                    await source.evaluate(
                        """url => {
                            const frame=document.createElement('iframe');
                            frame.id='takeover-frame'; frame.src=url;
                            frame.style.cssText='position:fixed;left:70px;top:70px;'
                              +'width:850px;height:550px;border:0;z-index:9999;background:white';
                            document.body.append(frame);
                        }""",
                        testsite.replace("127.0.0.1", "localhost") + "/form.html",
                    )
                    checkbox = source.frame_locator("#takeover-frame").get_by_label("Newsletter")
                    await checkbox.wait_for(state="visible")
                    await wait_until(
                        lambda: hub.latest is not None and hub.latest.metadata.seq > before_iframe
                    )
                    assert hub.latest
                    await page.wait_for_function(
                        "seq => Number(document.querySelector('[data-preview-seq]')"
                        "?.dataset.previewSeq) >= seq",
                        arg=hub.latest.metadata.seq,
                    )
                    assert not await checkbox.is_checked()
                    box = await checkbox.bounding_box()
                    rect = await canvas.bounding_box()
                    assert box and rect
                    local = await checkbox.evaluate(
                        "el => { const r=el.getBoundingClientRect();return {x:r.x,y:r.y}; }"
                    )
                    outer = await source.locator("#takeover-frame").bounding_box()
                    assert outer
                    assert abs(box["y"] - (outer["y"] + local["y"])) < 1, (
                        "Iframe checkbox bounding box must use CSS pixels"
                    )
                    assert await source.evaluate(
                        "p => document.elementFromPoint(p.x, p.y)?.id === 'takeover-frame'",
                        {"x": box["x"] + box["width"] / 2, "y": box["y"] + box["height"] / 2},
                    ), "Source checkbox coordinates must fall inside the iframe"
                    assert await page.evaluate(
                        "p => document.elementFromPoint(p.x,p.y)?.tagName === 'CANVAS'",
                        {
                            "x": rect["x"] + (box["x"] + box["width"] / 2) * rect["width"] / 1280,
                            "y": rect["y"] + (box["y"] + box["height"] / 2) * rect["height"] / 720,
                        },
                    ), "The preview click must hit the canvas rather than an overlay"
                    before_input = controller.counters.received
                    expected_point.update(
                        x=box["x"] + box["width"] / 2,
                        y=box["y"] + box["height"] / 2,
                    )
                    await page.mouse.click(
                        rect["x"] + (box["x"] + box["width"] / 2) * rect["width"] / 1280,
                        rect["y"] + (box["y"] + box["height"] / 2) * rect["height"] / 720,
                    )
                    await wait_until(lambda: controller.counters.received >= before_input + 2)
                    await wait_until(lambda: len(delivered_hits) >= 2)
                    assert delivered_hits == [True, True], "Both events must reach the CSS target"
                    expected_point.clear()
                    await expect(checkbox).to_be_checked()
                    await source.locator("#takeover-frame").evaluate("el => el.remove()")
                    await click_source(page, driver, 'a[href="login.html"]')
                    await wait_until(lambda: driver.get_active_page().url.endswith("login.html"))
                    # Wait for a real paint, not just a backend navigation.
                    await wait_until(
                        lambda: hub.latest is not None and hub.latest.metadata.seq > seq + 1
                    )
                    assert hub.latest
                    await page.wait_for_function(
                        "seq => Number(document.querySelector('[data-preview-seq]')"
                        "?.dataset.previewSeq) >= seq",
                        arg=hub.latest.metadata.seq,
                    )
                    await page.wait_for_function("""() => {
                        const canvas=document.querySelector('canvas');
                        const ctx=canvas.getContext('2d');
                        const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data;
                        const colors=new Set();
                        for(let i=0;i<pixels.length;i+=1024) {
                            colors.add(`${pixels[i]},${pixels[i+1]},${pixels[i+2]}`);
                        }
                        return colors.size > 20;
                    }""")
                    await click_source(page, driver, "#username")
                    await page.keyboard.insert_text("demo-user")
                    await click_source(page, driver, "#password")
                    await page.keyboard.insert_text("demo-pass-only")
                    await driver.get_active_page().wait_for_function(
                        "document.querySelector('#password').value.length === 14"
                    )
                    await click_source(page, driver, "button")
                    await (
                        driver.get_active_page()
                        .get_by_text("Welcome, demo-user", exact=True)
                        .wait_for()
                    )
                    await page.get_by_role("button", name="CLEVIS COMMAND", exact=True).click()
                    await page.get_by_role("button", name="Resume agent", exact=True).click()
                    await wait_status(service, run_id, RunStatus.FINISHED)
                    await page.get_by_text("Run ended", exact=True).wait_for()
                    assert await canvas.is_visible()
                    assert not errors
                finally:
                    await browser.close()
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            await asyncio.wait_for(process.wait(), 5)
