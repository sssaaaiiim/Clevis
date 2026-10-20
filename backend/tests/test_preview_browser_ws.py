import asyncio
import io
import json
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic
from typing import cast

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from PIL import Image
from websockets.asyncio.client import connect
from websockets.typing import Origin

from app.browser.playwright_driver import PlaywrightDriver
from app.browser.safety import display_available
from app.core.events import Action, Mode
from app.fakes.fake_llm import FakeLLMClient
from app.main import create_app
from app.preview.framing import decode_frame
from app.runtime import RunService
from tests.settings import IsolatedSettings
from tests.test_browser_process_cleanup import browser_descendants, wait_for_exit


@asynccontextmanager
async def serve(application: FastAPI, port: int = 0) -> AsyncIterator[str]:
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(128)
    port = listener.getsockname()[1]
    ready = asyncio.Event()
    original = application.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with original(app):
            ready.set()
            yield

    application.router.lifespan_context = lifespan
    server = uvicorn.Server(
        uvicorn.Config(application, log_level="warning", access_log=False, ws="websockets-sansio")
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        await asyncio.wait_for(ready.wait(), 3)
        yield f"127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        listener.close()


async def browser_ws(testsite: str, mode: Mode, scale: int) -> None:
    settings = IsolatedSettings(
        browser_driver="playwright", device_scale_factor=scale, preview_retain_after_end_s=0.1
    )
    drivers: list[PlaywrightDriver] = []

    def driver_factory() -> PlaywrightDriver:
        driver = PlaywrightDriver(settings)
        drivers.append(driver)
        return driver

    actions = [
        Action(action="navigate", value=testsite + "/form.html", rationale="Open demo."),
        Action(action="wait", value="10", rationale="Keep preview available."),
    ]
    application = create_app(
        settings,
        driver_factory=driver_factory,
        llm_factory=lambda: FakeLLMClient(actions=actions, delay=0.1),
    )
    service = cast(RunService, application.state.service)
    before = await asyncio.to_thread(browser_descendants)
    async with serve(application) as host:
        async with httpx.AsyncClient(base_url=f"http://{host}", trust_env=False) as client:
            started = monotonic()
            created = (
                await client.post("/api/runs", json={"goal": "Preview the demo", "mode": mode})
            ).json()
            run_id, token = created["runId"], created["previewToken"]
            async with connect(
                f"ws://{host}/api/runs/{run_id}/preview",
                origin=Origin(settings.frontend_origin),
                proxy=None,
                max_size=8_000_000,
            ) as viewer:
                await viewer.send(json.dumps({"type": "auth", "token": token}))
                async with asyncio.timeout(3):
                    while True:
                        message = await viewer.recv()
                        if isinstance(message, bytes):
                            metadata, image = decode_frame(message)
                            break
                assert monotonic() - started < 3
                assert image.startswith(b"\xff\xd8")
                with Image.open(io.BytesIO(image)) as header:
                    assert header.size == (1280 * scale, 720 * scale)
                assert metadata["deviceScaleFactor"] == scale
                # Verify the actual goal page, not just the initial blank browser repaint.
                async with asyncio.timeout(4):
                    while len(image) < 10_000:
                        message = await viewer.recv()
                        if isinstance(message, str):
                            assert json.loads(message).get("status") != "fallback"
                        else:
                            metadata, image = decode_frame(message)
                with Image.open(io.BytesIO(image)) as header:
                    assert header.size == (1280 * scale, 720 * scale)
                owned = await asyncio.to_thread(browser_descendants) - before
                assert owned
                response = await client.post(f"/api/runs/{run_id}/stop")
                assert response.status_code == 200
                async with asyncio.timeout(3):
                    while True:
                        message = await viewer.recv()
                        if (
                            isinstance(message, str)
                            and json.loads(message).get("status") == "ended"
                        ):
                            break
            assert service.preview_hubs[run_id].latest
            await asyncio.sleep(0.15)
            assert service.preview_hubs[run_id].latest is None
            assert not service.preview_hubs[run_id].viewers
            events = await service.store.list_events(run_id)
            assert image not in b"".join(e.model_dump_json().encode() for e in events)
            assert token not in str(events)
            assert await asyncio.to_thread(wait_for_exit, owned)
            with pytest.raises(Exception, match="not running"):
                drivers[0].get_context()


@pytest.mark.parametrize("scale", [1, 2])
async def test_headless_browser_preview_websocket(testsite: str, scale: int) -> None:
    await browser_ws(testsite, "headless", scale)


@pytest.mark.headed
@pytest.mark.skipif(
    not display_available(), reason="Headed preview needs DISPLAY or WAYLAND_DISPLAY."
)
async def test_headed_browser_preview_websocket(testsite: str) -> None:
    await browser_ws(testsite, "headed", 1)
