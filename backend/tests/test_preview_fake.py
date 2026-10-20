import asyncio
import io

from PIL import Image

from app.fakes.fake_driver import FakeBrowserDriver
from app.preview.factory import create_preview_channel
from app.preview.fake import FakePreviewChannel
from app.preview.hub import PreviewHub
from tests.settings import IsolatedSettings


async def test_fake_pattern_changes_and_lifecycle() -> None:
    settings = IsolatedSettings()
    hub = PreviewHub(settings)
    channel = create_preview_channel(FakeBrowserDriver(), hub, settings)
    assert isinstance(channel, FakePreviewChannel)
    seen: list[bytes] = []
    received = asyncio.Event()

    async def callback(image: bytes) -> None:
        seen.append(image)
        received.set()

    try:
        await channel.start_stream(callback)
        await asyncio.wait_for(received.wait(), 1)
        assert hub.latest and hub.latest.metadata.seq == 1
        with Image.open(io.BytesIO(seen[0])) as image:
            assert image.size == (640, 360) and image.format == "JPEG"
        assert FakePreviewChannel.pattern(1, "one") != FakePreviewChannel.pattern(2, "two")
    finally:
        await channel.stop_stream()
        await channel.stop_stream()
        await hub.close()
    assert channel._task is None and hub.latest is None
