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
from playwright.async_api import Frame as BrowserFrame

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
        self._supervisor: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._page: Page | None = None
        self._session_frames = 0
        self._navigation_handler: Callable[[BrowserFrame], None] | None = None
        self.reconnect_delay = 0.1
        self.first_frame_timeout = 3.0
        self.retry_screencast_s = 30.0

    def _tab_id(self, page: Page) -> str:
        return self._tabs.setdefault(page, secrets.token_hex(8))

    async def start_stream(self, on_frame: FrameCallback) -> None:
        if self.running:
            return
        self.running = True
        self._on_frame = on_frame
        self.hub.start()
        self._worker = asyncio.create_task(self._decode())
        self.driver.on_active_page_changed(self._page_changed)
        self._supervisor = asyncio.create_task(self._supervise())

    def _page_changed(self, page: Page) -> None:
        if self.running and page is not self._page:
            self._wake.set()

    def _session_closed(self, session: CDPSession) -> None:
        if self.running and session is self.session:
            self._wake.set()

    async def _supervise(self) -> None:
        attempts = 0
        fallback = False
        retry_at = 0.0
        while self.running:
            if fallback:
                if monotonic() >= retry_at or self._wake.is_set():
                    fallback = False
                    attempts = 0
                    continue
                await self._screenshot()
                try:
                    await asyncio.wait_for(
                        self._wake.wait(), 1 / self.settings.screencast_fallback_fps
                    )
                except TimeoutError:
                    pass
                continue
            self._wake.clear()
            try:
                async with asyncio.timeout(1):
                    await self._attach()
                self._wake.clear()
                healthy = await self._monitor()
                await self._detach()
                if healthy:
                    attempts = 0  # New page or detached session: reattach immediately.
                    continue
                fallback = True  # No first frame within three seconds.
            except asyncio.CancelledError:
                raise
            except Exception:
                await self._detach()
                attempts += 1
                if attempts < 3:
                    await asyncio.sleep(self.reconnect_delay * 2 ** (attempts - 1))
                    continue
                fallback = True
            if fallback:
                retry_at = monotonic() + self.retry_screencast_s
                self._wake.clear()
                self.hub.set_status("fallback", "Using low-frame-rate mode")

    async def _monitor(self) -> bool:
        started = monotonic()
        while self.running:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=0.5)
                return True
            except TimeoutError:
                pass
            if self.driver.get_active_page() is not self._page:
                return True
            if self._session_frames == 0 and monotonic() - started >= self.first_frame_timeout:
                return False
            if self.session:
                async with asyncio.timeout(0.5):
                    await self.session.send("Page.getLayoutMetrics")
                self.hub.heartbeat()  # Static pages are healthy even without repaints.
        return True

    async def _screenshot(self) -> None:
        try:
            page = self.driver.get_active_page()
            async with asyncio.timeout(1):
                image = await page.screenshot(
                    type="jpeg",
                    quality=self.settings.screencast_quality,
                    scale="device",
                    timeout=800,
                )
                raw = await page.evaluate("""() => ({pageScaleFactor:visualViewport?.scale || 1,
                    scrollOffsetX:scrollX, scrollOffsetY:scrollY})""")
            # Only inspect dimensions. Never resize, re-encode, or write image bytes to disk.
            with Image.open(io.BytesIO(image)) as header:
                width, height = header.size
            self.hub.set_status("fallback", "Using low-frame-rate mode")
            self.hub.publish(
                Frame(image, self._metadata(width, height, raw, self._tab_id(page), "jpeg"))
            )
            if self._on_frame:
                await self._on_frame(image)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # Hub's independent health clock reports stalled if capture stays broken.

    async def _attach(self) -> None:
        page = self.driver.get_active_page()
        session = await self.driver.get_context().new_cdp_session(page)
        self.session = session
        self._page = page

        def navigated(frame: BrowserFrame) -> None:
            if frame.parent_frame is None and session is self.session:
                self._wake.set()

        self._navigation_handler = navigated
        page.on("framenavigated", navigated)
        self._session_frames = 0
        self._last_accepted = -math.inf
        session.on("close", lambda closed: self._session_closed(session))
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
            self._session_closed(session)
            return  # The detached target cannot accept an ack; recovery owns a new session.
        if not self.running or session is not self.session:
            return
        self._session_frames += 1
        self.hub.heartbeat()
        now = monotonic()
        if now - self._last_accepted < 1 / self.settings.screencast_max_fps:
            return
        self._last_accepted = now
        self.hub.set_status("live", "Live preview")
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
        if self._page and self._navigation_handler:
            self._page.remove_listener("framenavigated", self._navigation_handler)
            self._navigation_handler = None
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
        if self._supervisor:
            self._supervisor.cancel()
            await asyncio.gather(self._supervisor, return_exceptions=True)
            self._supervisor = None
        await self._detach()
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None
        while not self._raw.empty():
            self._raw.get_nowait()
        self._tabs.clear()
        self._page = None
        await self.hub.end()

    async def input(self, event: InputEvent) -> None:
        # TODO Task 6: operator input belongs to the separate authenticated input channel.
        return None
