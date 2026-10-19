import asyncio
from typing import Protocol
from uuid import uuid4

from app.core.events import Event, Mode, utc_now
from app.core.state import RunRecord


class RunNotFound(KeyError):
    def __init__(self, run_id: str) -> None:
        super().__init__("Run not found.")
        self.run_id = run_id


class RunStore(Protocol):
    async def create(self, goal: str, mode: Mode) -> RunRecord: ...
    async def get(self, run_id: str) -> RunRecord: ...
    async def update(self, run: RunRecord) -> None: ...
    async def append_event(self, run_id: str, event: Event) -> Event: ...
    async def list_events(self, run_id: str, after_seq: int = 0) -> list[Event]: ...


class InMemoryRunStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._runs: dict[str, RunRecord] = {}
        self._events: dict[str, list[Event]] = {}

    def _get(self, run_id: str) -> RunRecord:
        try:
            return self._runs[run_id]
        except KeyError:
            raise RunNotFound(run_id) from None

    async def create(self, goal: str, mode: Mode) -> RunRecord:
        async with self._lock:
            run = RunRecord(runId=str(uuid4()), goal=goal, mode=mode)
            self._runs[run.runId] = run
            self._events[run.runId] = []
            return run.model_copy(deep=True)

    async def get(self, run_id: str) -> RunRecord:
        async with self._lock:
            return self._get(run_id).model_copy(deep=True)

    async def update(self, run: RunRecord) -> None:
        async with self._lock:
            self._get(run.runId)
            self._runs[run.runId] = run.model_copy(deep=True)

    async def append_event(self, run_id: str, event: Event) -> Event:
        async with self._lock:
            self._get(run_id)
            if event.runId != run_id:
                raise ValueError("Event runId does not match run.")
            events = self._events[run_id]
            stored = event.model_copy(update={"seq": len(events) + 1, "ts": utc_now()}, deep=True)
            events.append(stored)
            return stored.model_copy(deep=True)

    async def list_events(self, run_id: str, after_seq: int = 0) -> list[Event]:
        async with self._lock:
            self._get(run_id)
            return [e.model_copy(deep=True) for e in self._events[run_id] if e.seq > after_seq]
