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
from playwright.async_api import Page, Route, async_playwright

import app.runtime as runtime
from app.browser.playwright_driver import PlaywrightDriver
from app.config import Settings
from app.core.events import Action, Mode
from app.core.state import RunStatus
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import BrowserDriver, PreviewChannel
from app.main import create_app
from app.preview.cdp import CdpScreencastChannel
from app.preview.factory import create_preview_channel
from app.preview.hub import PreviewHub
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
    llm = FakeLLMClient(
        actions=[
            Action(action="navigate", value=testsite + "/popup.html", rationale="Open local demo."),
            Action(action="handoff", value="Please sign in, then Resume", rationale="Ask a human."),
            Action(action="done", value="Human flow completed", rationale="Complete local task."),
        ],
        delay=0.02,
    )
    channels: list[CdpScreencastChannel] = []

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
                    # Force a real session detach while the same preview viewer stays mounted.
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
                    await page.set_viewport_size({"width": 1100, "height": 820})
                    await page.wait_for_function(
                        "document.querySelector('canvas').getBoundingClientRect().width < 1000"
                    )
                    rect = await canvas.bounding_box()
                    assert rect and 0 < rect["width"] <= 1280 and rect["height"] <= 720
                    assert abs(rect["width"] / rect["height"] - 1280 / 720) < 0.01
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
