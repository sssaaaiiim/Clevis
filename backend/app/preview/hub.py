import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import monotonic
from typing import Literal

from app.config import Settings
from app.preview.framing import Frame

StatusName = Literal["waiting", "live", "stalled", "fallback", "ended"]


@dataclass(frozen=True)
class Status:
    status: StatusName
    message: str

    def json(self) -> dict[str, str]:
        return {"type": "status", "status": self.status, "message": self.message}


Message = Frame | Status


class PreviewHub:
    """Event-loop confined, bounded fan-out. Never sends to a socket or stores an event."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.latest: Frame | None = None
        self.status = Status("waiting", "Starting browser…")
        self.viewers: set[asyncio.Queue[Message]] = set()
        self.last_frame_at = monotonic()
        self.last_activity = monotonic()
        self._idle_task: asyncio.Task[None] | None = None
        self._retention: asyncio.Task[None] | None = None

    @staticmethod
    def offer(queue: asyncio.Queue[Message], message: Message) -> None:
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(message)

    def _broadcast(self, message: Message) -> None:
        for viewer in self.viewers:
            self.offer(viewer, message)

    def set_status(self, status: StatusName, message: str) -> None:
        if self.status.status == "ended":
            return
        next_status = Status(status, message)
        if next_status != self.status:
            self.status = next_status
            self._broadcast(next_status)

    def heartbeat(self) -> None:
        self.last_activity = monotonic()

    def publish(self, frame: Frame) -> None:
        if self.status.status == "ended":
            return
        self.latest = frame
        self.last_frame_at = self.last_activity = monotonic()
        if self.status.status != "fallback":
            self.set_status("live", "Live preview")
        self._broadcast(frame)

    def start(self) -> None:
        if self._idle_task is None:
            self._idle_task = asyncio.create_task(self._idle())

    async def _idle(self) -> None:
        while True:
            await asyncio.sleep(self.settings.preview_idle_resend_s)
            if monotonic() - self.last_activity >= 5:
                self.set_status("stalled", "Waiting for the page…")
            elif (
                self.latest
                and monotonic() - self.last_frame_at >= self.settings.preview_idle_resend_s
            ):
                if self.status.status == "live":
                    self.set_status("live", "Preview paused: page is idle")
                self._broadcast(self.latest)

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Message]]:
        queue: asyncio.Queue[Message] = asyncio.Queue(self.settings.preview_client_queue)
        self.viewers.add(queue)
        # Route sends the initial status and latest directly, so queue=1 cannot lose either.
        try:
            yield queue
        finally:
            self.viewers.discard(queue)
            while not queue.empty():
                queue.get_nowait()

    async def end(self) -> None:
        if self.status.status == "ended":
            return
        self.set_status("ended", "Run ended")
        if self._idle_task:
            self._idle_task.cancel()
            await asyncio.gather(self._idle_task, return_exceptions=True)
            self._idle_task = None
        self._retention = asyncio.create_task(self._expire())

    async def _expire(self) -> None:
        await asyncio.sleep(self.settings.preview_retain_after_end_s)
        self.latest = None
        for queue in self.viewers:
            while not queue.empty():
                queue.get_nowait()
            self.offer(queue, self.status)

    async def close(self) -> None:
        await self.end()
        if self._retention:
            self._retention.cancel()
            await asyncio.gather(self._retention, return_exceptions=True)
        self.latest = None
