"""In-memory fake preview. Generated pixels never enter the driver, store or event log."""

import asyncio
import io
from collections.abc import Awaitable, Callable

from PIL import Image, ImageDraw

from app.config import Settings
from app.core.events import utc_now
from app.interfaces.browser import InputEvent
from app.preview.framing import Frame, FrameMetadata
from app.preview.hub import PreviewHub


class FakePreviewChannel:
    def __init__(self, hub: PreviewHub, settings: Settings) -> None:
        self.hub = hub
        self.settings = settings
        self._task: asyncio.Task[None] | None = None
        self._closed = False

    @staticmethod
    def pattern(counter: int, timestamp: str) -> bytes:
        image = Image.new("RGB", (640, 360), "#f5f8ff")
        draw = ImageDraw.Draw(image)
        for x in range(0, 640, 32):
            draw.line((x, 0, x, 360), fill="#cfdaec")
        for y in range(0, 360, 32):
            draw.line((0, y, 640, y), fill="#cfdaec")
        draw.rectangle((24, 24, 616, 110), fill="white", outline="#285dab")
        draw.text((40, 40), f"FAKE BROWSER PREVIEW - FRAME {counter}", fill="#10213a")
        draw.text((40, 72), timestamp, fill="#10213a")
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85)
        return output.getvalue()

    async def start_stream(self, on_frame: Callable[[bytes], Awaitable[None]]) -> None:
        if self._task or self._closed:
            return
        self.hub.start()
        self._task = asyncio.create_task(self._loop(on_frame))

    async def _loop(self, on_frame: Callable[[bytes], Awaitable[None]]) -> None:
        counter = 0
        while True:
            counter += 1
            timestamp = utc_now()
            image = await asyncio.to_thread(self.pattern, counter, timestamp)
            self.hub.publish(
                Frame(
                    image,
                    FrameMetadata(
                        format="jpeg",
                        width=640,
                        height=360,
                        deviceScaleFactor=1,
                        viewportWidth=640,
                        viewportHeight=360,
                        seq=counter,
                        ts=timestamp,
                        tabId="fake-tab",
                    ),
                )
            )
            await on_frame(image)
            await asyncio.sleep(1 / min(2, self.settings.screencast_max_fps))

    async def stop_stream(self) -> None:
        self._closed = True
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        await self.hub.end()

    async def input(self, event: InputEvent) -> None:
        # TODO Task 6: fake preview is display-only.
        return None
