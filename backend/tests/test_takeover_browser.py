"""Real network input → real Chromium, with fake model decisions and fake demo credentials."""

import asyncio
import json
import logging
from typing import Any, Literal, TypeVar, cast

import httpx
import pytest
from pydantic import BaseModel
from websockets.asyncio.client import ClientConnection, connect
from websockets.typing import Origin

from app.browser.playwright_driver import PlaywrightDriver
from app.browser.safety import display_available
from app.core.events import Action, Mode, Target
from app.core.state import RunStatus
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.llm import LLMResponse, Message
from app.main import create_app
from app.preview.framing import decode_frame
from app.runtime import RunService
from tests.settings import IsolatedSettings
from tests.test_browser_process_cleanup import browser_descendants, wait_for_exit
from tests.test_input_privacy import CANARY
from tests.test_preview_browser_ws import serve
from tests.test_takeover_state import wait_status

T = TypeVar("T", bound=BaseModel)


class BrowserLLM(FakeLLMClient):
    def __init__(self, url: str) -> None:
        super().__init__(
            actions=[
                Action(action="navigate", value=url, rationale="Open demo login."),
                Action(
                    action="handoff",
                    value="Please sign in, then click Resume",
                    rationale="Need a human.",
                ),
                Action(action="extract", rationale="Read the welcome message."),
                Action(
                    action="done",
                    value="Welcome, [redacted]-[redacted]",
                    rationale="Login succeeded.",
                ),
            ],
            delay=0.01,
        )
        self.requests: list[str] = []

    async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
        self.requests.append(json.dumps([m.model_dump() for m in messages]))
        return await super().propose(messages, schema)


async def barrier(socket: ClientConnection, *messages: dict[str, Any]) -> None:
    for message in messages:
        await socket.send(json.dumps(message))
    await socket.send('{"type":"ping"}')
    async with asyncio.timeout(2):
        while json.loads(await socket.recv())["type"] != "pong":
            pass


async def click(
    socket: ClientConnection, driver: PlaywrightDriver, selector: str, metadata: dict[str, Any]
) -> None:
    box = await driver.get_active_page().locator(selector).bounding_box()
    assert box
    # Model a resized/letterboxed canvas; the inverse mapping must yield CSS viewport coordinates.
    left, top, width, height = 103, 61, 640, 360
    client_x = left + (box["x"] + box["width"] / 2) * width / metadata["viewportWidth"]
    client_y = top + (box["y"] + box["height"] / 2) * height / metadata["viewportHeight"]
    x = (client_x - left) * metadata["viewportWidth"] / width
    y = (client_y - top) * metadata["viewportHeight"] / height
    await barrier(
        socket,
        *[
            dict(type="mouse", action=action, x=x, y=y, button="left", clickCount=1, modifiers=0)
            for action in ["down", "up"]
        ],
    )


async def login(testsite: str, mode: Mode, scale: int, caplog: pytest.LogCaptureFixture) -> None:
    before = await asyncio.to_thread(browser_descendants)
    driver = PlaywrightDriver(IsolatedSettings(device_scale_factor=scale))
    llm = BrowserLLM(testsite + "/login.html")
    application = create_app(
        IsolatedSettings(device_scale_factor=scale),
        driver_factory=lambda: driver,
        llm_factory=lambda: llm,
    )
    service = cast(RunService, application.state.service)
    caplog.set_level(logging.DEBUG)
    async with serve(application) as host:
        async with httpx.AsyncClient(base_url="http://" + host, trust_env=False) as http:
            created = (
                await http.post(
                    "/api/runs",
                    json={"goal": "Log in and report the welcome message", "mode": mode},
                )
            ).json()
            run_id = created["runId"]
            await wait_status(service, run_id, RunStatus.PAUSED)
            generation = driver.generation
            owned = await asyncio.to_thread(browser_descendants) - before
            origin = Origin(service.settings.frontend_origin)
            async with connect(
                f"ws://{host}/api/runs/{run_id}/preview",
                origin=origin,
                proxy=None,
                max_size=8_000_000,
            ) as preview:
                await preview.send(json.dumps({"type": "auth", "token": created["previewToken"]}))
                async with asyncio.timeout(3):
                    while True:
                        frame = await preview.recv()
                        if isinstance(frame, bytes):
                            metadata, _ = decode_frame(frame)
                            break
            assert metadata["viewportWidth"] == 1280 and metadata["deviceScaleFactor"] == scale
            async with connect(
                f"ws://{host}/api/runs/{run_id}/input", origin=origin, proxy=None
            ) as ws:
                await ws.send(json.dumps({"type": "auth", "token": created["controlToken"]}))
                assert json.loads(await ws.recv())["accepting"]
                await click(ws, driver, "#username", metadata)
                await barrier(ws, {"type": "text", "value": "demo-user"})
                await click(ws, driver, "#password", metadata)
                await barrier(ws, {"type": "text", "value": CANARY})
                observation = await driver.observe()
                assert CANARY not in observation.model_dump_json()
                assert (
                    next(e for e in observation.elements if e.type == "password").value
                    == "[redacted]"
                )
                await barrier(
                    ws,
                    {"type": "key", "action": "down", "key": "a", "code": "KeyA", "modifiers": 2},
                    {"type": "key", "action": "up", "key": "a", "code": "KeyA", "modifiers": 2},
                    {"type": "text", "value": "demo-pass-only"},
                )
                await click(ws, driver, "button", metadata)
                assert (
                    await driver.get_active_page().locator("#login-status").inner_text()
                    == "Welcome, demo-user"
                )
                # Disconnect frees ownership but never resumes the agent.
            assert (await service.store.get(run_id)).status == RunStatus.PAUSED
            await http.post(f"/api/runs/{run_id}/resume")
            await wait_status(service, run_id, RunStatus.FINISHED)
            assert driver.generation > generation
            events = await service.store.list_events(run_id)
            resumed = next(i for i, event in enumerate(events) if event.type == "run.resumed")
            assert events[resumed + 1].type == "observation.summary"
            assert (await service.store.get(run_id)).result == "Welcome, [redacted]-[redacted]"
            assert not service.controls[run_id].owner and service.controls[run_id].relay is None
            for private in [CANARY, "demo-pass-only", "demo-user", created["controlToken"]]:
                assert private not in caplog.text
                assert private not in "".join(llm.requests)
                assert (
                    private not in str(events) + (await service.store.get(run_id)).model_dump_json()
                )
            assert "Welcome" in llm.requests[-1]
    assert await asyncio.to_thread(wait_for_exit, owned)


@pytest.mark.parametrize("scale", [1, 2])
async def test_headless_login_handoff(
    testsite: str, scale: int, caplog: pytest.LogCaptureFixture
) -> None:
    await login(testsite, "headless", scale, caplog)


@pytest.mark.headed
@pytest.mark.skipif(
    not display_available(), reason="Headed input needs DISPLAY or WAYLAND_DISPLAY."
)
async def test_headed_login_handoff(testsite: str, caplog: pytest.LogCaptureFixture) -> None:
    await login(testsite, "headed", 1, caplog)


async def test_cancelled_playwright_autowait_cannot_click_after_takeover(
    driver: PlaywrightDriver, testsite: str
) -> None:
    page = driver.get_active_page()
    await driver.navigate(testsite + "/popup.html")
    observation = await driver.observe()
    button = next(e for e in observation.elements if e.name == "Show alert")
    await page.evaluate("""() => {
        window.agentClicks=0;
        const b=document.querySelector('#alert-button');
        b.onclick=()=>window.agentClicks++;
        b.style.pointerEvents='none';
    }""")
    pending = asyncio.create_task(
        driver.act(Action(action="click", target=Target(ref=button.ref), rationale="Click button."))
    )
    await asyncio.sleep(0.1)
    assert not pending.done()
    await driver.pause_actions()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(pending, 2)
    # Installed Playwright's cancellation waits for protocol __abort__ acknowledgement.
    await page.evaluate("document.querySelector('#alert-button').style.pointerEvents='auto'")
    await asyncio.sleep(0.3)
    assert await page.evaluate("window.agentClicks") == 0
    assert not page.is_closed()


async def test_user_takeover_form_popup_disconnect_and_stop(testsite: str) -> None:
    driver = PlaywrightDriver(IsolatedSettings())
    llm = FakeLLMClient(
        actions=[
            Action(action="navigate", value=testsite + "/form.html", rationale="Open demo form."),
            Action(action="wait", value="10", rationale="Wait for human control."),
            Action(action="done", value="Finished", rationale="Finish."),
        ],
        delay=0.01,
    )
    application = create_app(
        IsolatedSettings(), driver_factory=lambda: driver, llm_factory=lambda: llm
    )
    service = cast(RunService, application.state.service)
    async with serve(application) as host:
        async with httpx.AsyncClient(base_url="http://" + host, trust_env=False) as http:
            created = (
                await http.post("/api/runs", json={"goal": "Read the form", "mode": "headless"})
            ).json()
            run_id = created["runId"]
            async with service.emitter.subscribe(run_id) as events:
                async with asyncio.timeout(4):
                    while True:
                        event = await events.queue.get()
                        if event.type == "step.proposed" and event.data.action == "wait":
                            break
            assert (await http.post(f"/api/runs/{run_id}/takeover")).status_code == 200
            endpoint = f"ws://{host}/api/runs/{run_id}/input"
            origin = Origin(service.settings.frontend_origin)
            async with connect(endpoint, origin=origin, proxy=None) as socket:
                await socket.send(json.dumps({"type": "auth", "token": created["controlToken"]}))
                assert json.loads(await socket.recv())["accepting"]
                metadata = {"viewportWidth": 1280, "viewportHeight": 720}
                await click(socket, driver, "#name", metadata)
                await barrier(socket, {"type": "text", "value": "Demo person"})
                assert (
                    await driver.get_active_page().locator("#name").input_value() == "Demo person"
                )
                # Open a real popup from the controlled page, then relay into its newly active tab.
                async with driver.get_active_page().expect_popup() as popup:
                    await driver.get_active_page().evaluate(
                        "(url)=>window.open(url)", testsite + "/index.html"
                    )
                new_page = await popup.value
                await new_page.wait_for_load_state("domcontentloaded")
                assert driver.get_active_page() is new_page
                await click(socket, driver, "#search", metadata)
                await barrier(socket, {"type": "text", "value": "Notebook"})
                assert await new_page.locator("#search").input_value() == "Notebook"
            assert (await service.store.get(run_id)).status == RunStatus.PAUSED
            # A reconnect can own the released slot; no implicit resume on WebSocket loss.
            async with connect(endpoint, origin=origin, proxy=None) as socket:
                await socket.send(json.dumps({"type": "auth", "token": created["controlToken"]}))
                assert json.loads(await socket.recv())["accepting"]
                assert (await http.post(f"/api/runs/{run_id}/stop")).json()["status"] == "stopped"
            assert not service.controls[run_id].owner


async def test_cdp_enter_submits_and_tab_backspace_work(
    driver: PlaywrightDriver, testsite: str
) -> None:
    from app.preview.input_protocol import Key, Text
    from app.preview.input_relay import CdpInputRelay

    await driver.navigate(testsite + "/login.html")
    page = driver.get_active_page()
    await page.locator("#username").focus()
    relay = CdpInputRelay(driver)
    directions: list[Literal["down", "up"]] = ["down", "up"]
    try:
        assert await relay.send(Text(type="text", value="demo-userX"))
        for action in directions:
            assert await relay.send(
                Key(type="key", action=action, key="Backspace", code="Backspace")
            )
        assert await page.locator("#username").input_value() == "demo-user"
        for action in directions:
            assert await relay.send(Key(type="key", action=action, key="Tab", code="Tab"))
        assert await relay.send(Text(type="text", value="demo-pass-only"))
        assert await page.locator("#password").input_value() == "demo-pass-only"
        for action in directions:
            assert await relay.send(Key(type="key", action=action, key="Enter", code="Enter"))
        assert await page.locator("#login-status").inner_text() == "Welcome, demo-user"
    finally:
        await relay.close()
