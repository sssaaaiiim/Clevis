import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol

from app.core.events import TERMINAL_EVENTS, Event
from app.core.store import RunStore


class EventEmitter(Protocol):
    async def emit(self, run_id: str, event: Event) -> Event: ...


@dataclass
class Subscription:
    queue: asyncio.Queue[Event]
    terminal: bool


class FanoutEventEmitter:
    """Persist before delivery; serialize subscribe/replay with emit to avoid lost events."""

    def __init__(self, store: RunStore) -> None:
        self.store = store
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[Event]]] = {}

    @property
    def subscriber_count(self) -> int:
        return sum(len(queues) for queues in self._subscribers.values())

    async def emit(self, run_id: str, event: Event) -> Event:
        async with self._lock:
            stored = await self.store.append_event(run_id, event)
            for queue in self._subscribers.get(run_id, set()):
                queue.put_nowait(stored.model_copy(deep=True))
            return stored

    @asynccontextmanager
    async def subscribe(self, run_id: str, after_seq: int = 0) -> AsyncIterator[Subscription]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        async with self._lock:
            history = await self.store.list_events(run_id)
            for event in history:
                if event.seq > after_seq:
                    queue.put_nowait(event)
            self._subscribers.setdefault(run_id, set()).add(queue)
            subscription = Subscription(queue, bool(history and history[-1].type in TERMINAL_EVENTS))
        try:
            yield subscription
        finally:
            async with self._lock:
                queues = self._subscribers[run_id]
                queues.discard(queue)
                if not queues:
                    del self._subscribers[run_id]
