import asyncio
import base64
import io
from time import monotonic
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
    channel._last_accepted = monotonic()
    for i in range(100):
        await channel._receive(
            {"sessionId": i, "data": "not decoded", "metadata": {}}, session, "tab"
        )
    assert channel.received == channel.acked == channel.throttled == 100
    assert channel._raw.empty()
    channel._last_accepted -= 2
    await channel._receive(
        {"sessionId": 100, "data": "not decoded", "metadata": {}}, session, "tab"
    )
    assert channel.received == channel.acked == 101 and channel._raw.qsize() == 1
    assert cast(Any, session).ids == list(range(101))
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


async def test_navigation_popup_and_forced_detach_recover(
    testsite: str, driver: PlaywrightDriver
) -> None:
    settings = IsolatedSettings(preview_idle_resend_s=0.03)
    hub = PreviewHub(settings)
    channel = CdpScreencastChannel(driver, hub, settings)
    try:
        await driver.navigate(testsite + "/index.html")
        await channel.start_stream(ignore)
        await latest(channel)
        assert hub.latest
        initial = hub.latest.metadata
        await driver.navigate(testsite + "/form.html")
        await latest(channel, initial.seq)
        old_tab = hub.latest.metadata.tabId
        await driver.get_active_page().evaluate("window.open('popup.html')")
        async with hub.subscribe() as queue:
            async with asyncio.timeout(3):
                while hub.latest.metadata.tabId == old_tab:
                    await queue.get()
        assert hub.latest.metadata.tabId != old_tab
        assert channel.session
        old_session = channel.session
        seq = hub.latest.metadata.seq
        await old_session.detach()
        await latest(channel, seq)
        assert channel.session is not old_session
        # Closing the popup falls back to the original page and reattaches.
        await driver.get_active_page().close()
        async with hub.subscribe() as queue:
            async with asyncio.timeout(3):
                while hub.latest.metadata.tabId != old_tab:
                    await queue.get()
        assert hub.latest.metadata.tabId == old_tab
    finally:
        await channel.stop_stream()
        await hub.close()


async def test_fallback_and_periodic_screencast_retry(
    testsite: str,
    driver: PlaywrightDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = IsolatedSettings(screencast_fallback_fps=20)
    hub = PreviewHub(settings)
    channel = CdpScreencastChannel(driver, hub, settings)
    original = channel._attach
    calls = 0

    async def fail_then_work() -> None:
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise RuntimeError("Injected startup failure")
        await original()

    monkeypatch.setattr(channel, "_attach", fail_then_work)
    channel.reconnect_delay = 0.01
    channel.retry_screencast_s = 0.1
    try:
        await driver.navigate(testsite + "/index.html")
        await channel.start_stream(ignore)
        await latest(channel)
        assert hub.status.status == "fallback"
        assert hub.latest and hub.latest.image.startswith(b"\xff\xd8")
        async with hub.subscribe() as queue:
            async with asyncio.timeout(3):
                while str(hub.status.status) != "live":
                    await queue.get()
        assert calls >= 4
    finally:
        await channel.stop_stream()
        await hub.close()


async def test_static_idle_resends_without_stall(driver: PlaywrightDriver) -> None:
    settings = IsolatedSettings(preview_idle_resend_s=0.02)
    hub = PreviewHub(settings)
    channel = CdpScreencastChannel(driver, hub, settings)
    try:
        await channel.start_stream(ignore)
        await latest(channel)
        assert hub.latest
        seq = hub.latest.metadata.seq
        async with hub.subscribe() as queue:
            async with asyncio.timeout(1):
                while True:
                    message = await queue.get()
                    if isinstance(message, type(hub.latest)) and message.metadata.seq == seq:
                        break
        assert hub.status.status == "live"
    finally:
        await channel.stop_stream()
        await hub.close()


async def test_no_first_frame_switches_to_fallback(
    driver: PlaywrightDriver, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = IsolatedSettings()
    hub = PreviewHub(settings)
    channel = CdpScreencastChannel(driver, hub, settings)

    async def ack_without_frame(event: dict[str, Any], session: CDPSession, tab_id: str) -> None:
        await session.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})

    monkeypatch.setattr(channel, "_receive", ack_without_frame)
    channel.first_frame_timeout = 0.1
    try:
        await channel.start_stream(ignore)
        async with hub.subscribe() as queue:
            async with asyncio.timeout(3):
                while hub.status.status != "fallback":
                    await queue.get()
        await latest(channel)
        assert hub.latest and hub.latest.image.startswith(b"\xff\xd8")
    finally:
        await channel.stop_stream()
        await hub.close()


async def test_animation_throttle_and_nonreading_viewer_do_not_block_browser(
    driver: PlaywrightDriver,
) -> None:
    settings = IsolatedSettings(screencast_max_fps=15, preview_client_queue=2)
    hub = PreviewHub(settings)
    channel = CdpScreencastChannel(driver, hub, settings)
    await driver.get_active_page().set_content("<h1>Animated fake preview</h1>")
    await driver.get_active_page().evaluate("""() => {
        let n=0; window.demoTimer=setInterval(() => {
            document.body.style.backgroundColor=`hsl(${n++ % 360} 80% 80%)`;
        }, 16);
    }""")
    try:
        await channel.start_stream(ignore)
        await latest(channel)
        assert hub.latest
        first = hub.latest.metadata.seq
        async with hub.subscribe() as slow:
            started = monotonic()
            await driver.observe()
            assert monotonic() - started < 1
            await asyncio.sleep(0.75)
            assert slow.qsize() <= settings.preview_client_queue
            assert hub.latest.metadata.seq >= first + 3
            assert hub.latest.metadata.seq - first <= 15
    finally:
        await channel.stop_stream()
        await hub.close()

    assert channel.received == channel.acked


async def test_stop_during_detach_preserves_session_and_drains_acks() -> None:
    entered = asyncio.Event()
    settings = IsolatedSettings()
    hub = PreviewHub(settings)
    channel = CdpScreencastChannel(PlaywrightDriver(settings), hub, settings)

    class Session:
        stops = 0
        detached = False

        async def send(self, method: str, params: dict[str, Any] | None = None) -> None:
            if method == "Page.stopScreencast":
                self.stops += 1
                if self.stops == 1:
                    entered.set()
                    await asyncio.Event().wait()
                # A final frame was delivered while stopping. It still needs its ACK.
                pending = asyncio.create_task(
                    channel._receive({"sessionId": 7}, cast(CDPSession, self), "tab")
                )
                channel._acks.add(pending)
                pending.add_done_callback(channel._acks.discard)
            elif method == "Page.screencastFrameAck":
                await asyncio.sleep(0.01)
                assert not self.detached
                assert params == {"sessionId": 7}
            else:
                raise AssertionError("Unexpected CDP method")

        async def detach(self) -> None:
            assert channel.received == channel.acked == 1
            self.detached = True

    session = Session()
    channel.session = cast(CDPSession, session)
    channel.running = True
    channel._supervisor = asyncio.create_task(channel._detach())
    await asyncio.wait_for(entered.wait(), 1)
    await channel.stop_stream()
    assert session.stops == 2 and session.detached
    assert channel.session is None and not channel._acks
    await hub.close()
