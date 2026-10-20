"""CDP frames are acknowledged independently from decoding, callbacks and viewers."""

import asyncio
import base64
import io
import math
import secrets
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from PIL import Image
from playwright.async_api import CDPSession, Page

from app.browser.playwright_driver import PlaywrightDriver
from app.config import Settings
from app.core.events import utc_now
from app.interfaces.browser import InputEvent
from app.preview.framing import Frame, FrameMetadata
from app.preview.hub import PreviewHub

FrameCallback = Callable[[bytes], Awaitable[None]]


class CdpScreencastChannel:
    def __init__(self, driver: PlaywrightDriver, hub: PreviewHub, settings: Settings) -> None:
        self.driver = driver
        self.hub = hub
        self.settings = settings
        self.session: CDPSession | None = None
        self.running = False
        self.seq = 0
        self.received = 0
        self.acked = 0
        self._last_accepted = -math.inf
        self._tabs: dict[Page, str] = {}
        self._raw: asyncio.Queue[tuple[dict[str, Any], CDPSession, str]] = asyncio.Queue(1)
        self._worker: asyncio.Task[None] | None = None
        self._acks: set[asyncio.Task[None]] = set()
        self._on_frame: FrameCallback | None = None

    def _tab_id(self, page: Page) -> str:
        return self._tabs.setdefault(page, secrets.token_hex(8))

    async def start_stream(self, on_frame: FrameCallback) -> None:
        if self.running:
            return
        self.running = True
        self._on_frame = on_frame
        self.hub.start()
        self._worker = asyncio.create_task(self._decode())
        await self._attach()

    async def _attach(self) -> None:
        page = self.driver.get_active_page()
        session = await self.driver.get_context().new_cdp_session(page)
        self.session = session
        viewport = self.driver.get_viewport()
        width, height, dsf = viewport["width"], viewport["height"], viewport["deviceScaleFactor"]
        # Chromium otherwise screencasts DIP-sized surfaces, even when maxWidth allows HiDPI.
        # This scales the compositor viewport without changing window.innerWidth/Height or DPR.
        if dsf != 1:
            await session.send(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": dsf,
                    "mobile": False,
                    "viewport": {"x": 0, "y": 0, "width": width, "height": height, "scale": dsf},
                },
            )
        tab_id = self._tab_id(page)

        def frame(event: dict[str, Any]) -> None:
            task = asyncio.create_task(self._receive(event, session, tab_id))
            self._acks.add(task)
            task.add_done_callback(self._acks.discard)

        session.on("Page.screencastFrame", frame)
        parameters: dict[str, Any] = {
            "format": self.settings.screencast_format,
            "maxWidth": math.ceil(width * dsf),
            "maxHeight": math.ceil(height * dsf),
            "everyNthFrame": self.settings.screencast_every_nth_frame,
        }
        if self.settings.screencast_format == "jpeg":
            parameters["quality"] = self.settings.screencast_quality
        await session.send("Page.startScreencast", parameters)

    async def _receive(self, event: dict[str, Any], session: CDPSession, tab_id: str) -> None:
        self.received += 1
        try:
            # Ack before throttle, decode, publish or viewer I/O, including dropped frames.
            await session.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})
            self.acked += 1
        except Exception:
            return  # The detached target cannot accept an ack; recovery owns a new session.
        if not self.running or session is not self.session:
            return
        self.hub.heartbeat()
        now = monotonic()
        if now - self._last_accepted < 1 / self.settings.screencast_max_fps:
            return
        self._last_accepted = now
        if self._raw.full():
            self._raw.get_nowait()
        self._raw.put_nowait((event, session, tab_id))

    @staticmethod
    def _image(data: str) -> tuple[bytes, int, int]:
        image = base64.b64decode(data, validate=True)
        with Image.open(io.BytesIO(image)) as header:
            width, height = header.size
        return image, width, height

    def _metadata(
        self, width: int, height: int, raw: dict[str, Any], tab_id: str, format_: str | None = None
    ) -> FrameMetadata:
        viewport = self.driver.get_viewport()
        self.seq += 1
        timestamp = raw.get("timestamp")
        ts = (
            datetime.fromtimestamp(timestamp, UTC).isoformat()
            if isinstance(timestamp, (int, float))
            else utc_now()
        )
        return FrameMetadata(
            format=format_ or self.settings.screencast_format,
            width=width,
            height=height,
            deviceScaleFactor=viewport["deviceScaleFactor"],
            viewportWidth=viewport["width"],
            viewportHeight=viewport["height"],
            pageScaleFactor=raw.get("pageScaleFactor", 1),
            scrollOffsetX=raw.get("scrollOffsetX", 0),
            scrollOffsetY=raw.get("scrollOffsetY", 0),
            offsetTop=raw.get("offsetTop", 0),
            seq=self.seq,
            ts=ts,
            tabId=tab_id,
        )

    async def _decode(self) -> None:
        while True:
            event, session, tab_id = await self._raw.get()
            try:
                image, width, height = await asyncio.to_thread(self._image, event["data"])
                if session is not self.session or not self.running:
                    continue
                metadata = self._metadata(width, height, event["metadata"], tab_id)
                self.hub.publish(Frame(image, metadata))
                if self._on_frame:
                    await self._on_frame(image)
            except Exception:
                self.hub.set_status("stalled", "Waiting for the page…")

    async def _detach(self) -> None:
        session, self.session = self.session, None
        if session:
            with suppress(Exception):
                async with asyncio.timeout(0.3):
                    await session.send("Page.stopScreencast")
            # Let already received frames finish their acknowledgements before detaching.
            if self._acks:
                with suppress(TimeoutError):
                    async with asyncio.timeout(0.3):
                        await asyncio.gather(*list(self._acks), return_exceptions=True)
            with suppress(Exception):
                async with asyncio.timeout(0.3):
                    await session.detach()

    async def stop_stream(self) -> None:
        if not self.running:
            return
        self.running = False
        await self._detach()
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        while not self._raw.empty():
            self._raw.get_nowait()
        self._tabs.clear()
        await self.hub.end()

    async def input(self, event: InputEvent) -> None:
        # TODO Task 6: operator input belongs to the separate authenticated input channel.
        return None
