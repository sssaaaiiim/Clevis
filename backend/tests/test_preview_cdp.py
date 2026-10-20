import asyncio
import base64
import io
from typing import Any, cast

import pytest
from PIL import Image
from playwright.async_api import CDPSession

from app.browser.playwright_driver import PlaywrightDriver
from app.preview.cdp import CdpScreencastChannel
from app.preview.hub import PreviewHub
from tests.settings import IsolatedSettings


async def ignore(image: bytes) -> None:
    pass


async def latest(channel: CdpScreencastChannel, after: int = 0) -> None:
    async with channel.hub.subscribe() as queue:
        async with asyncio.timeout(3):
            while not channel.hub.latest or channel.hub.latest.metadata.seq <= after:
                await queue.get()


async def test_every_received_frame_acked_even_when_throttled() -> None:
    class Session:
        ids: list[int] = []

        async def send(self, method: str, params: dict[str, Any]) -> None:
            assert method == "Page.screencastFrameAck"
            self.ids.append(params["sessionId"])

    settings = IsolatedSettings(screencast_max_fps=1)
    channel = CdpScreencastChannel(PlaywrightDriver(settings), PreviewHub(settings), settings)
    session = cast(CDPSession, Session())
    channel.session = session
    channel.running = True
    for i in range(100):
        await channel._receive(
            {"sessionId": i, "data": "not decoded", "metadata": {}}, session, "tab"
        )
    assert channel.received == channel.acked == 100
    assert channel._raw.qsize() == 1
    assert cast(Any, session).ids == list(range(100))
    channel.running = False
    channel._raw.get_nowait()


@pytest.mark.parametrize("scale", [1, 2])
async def test_native_pixels_and_full_viewport(testsite: str, scale: int) -> None:
    settings = IsolatedSettings(device_scale_factor=scale)
    driver = PlaywrightDriver(settings)
    hub = PreviewHub(settings)
    channel = CdpScreencastChannel(driver, hub, settings)
    await driver.start("headless")
    try:
        await driver.navigate(testsite + "/index.html")
        await driver.get_active_page().evaluate("""() => {
            const corner=document.createElement('div');
            corner.style='position:fixed;right:0;bottom:0;width:30px;height:30px;background:red';
            document.body.append(corner);
        }""")
        await channel.start_stream(ignore)
        await latest(channel)
        assert hub.latest
        frame = hub.latest
        assert frame.image.startswith(b"\xff\xd8")
        with Image.open(io.BytesIO(frame.image)) as image:
            assert image.size == (1280 * scale, 720 * scale)
            red, green, blue = cast(
                tuple[int, int, int],
                image.convert("RGB").getpixel((image.width - 10, image.height - 10)),
            )
            assert red > 200 and green < 50 and blue < 50
        assert await driver.get_active_page().evaluate("innerWidth") == 1280
        assert frame.metadata.deviceScaleFactor == scale
        assert channel.received == channel.acked
        # A header read/decode never changes the forwarded encoded bytes.
        original = base64.b64encode(frame.image).decode()
        assert channel._image(original)[0] == frame.image
    finally:
        await channel.stop_stream()
        await driver.close()
        await hub.close()
    await channel.stop_stream()
    assert channel.session is None and channel._worker is None
