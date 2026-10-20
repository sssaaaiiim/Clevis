"""Per-run controller ownership. Contains no input payloads or history."""

import asyncio
from time import monotonic
from typing import Protocol

from app.core.state import RunStateMachine, RunStatus
from app.preview.input_protocol import Input


class InputRelay(Protocol):
    async def send(self, message: Input) -> bool: ...
    async def close(self) -> None: ...


class ControlSession:
    def __init__(self, machine: RunStateMachine) -> None:
        self.machine = machine
        self.lock = asyncio.Lock()
        self.owner: object | None = None
        self.disconnected = asyncio.Event()
        self.ready = False
        self.last_activity = monotonic()
        self.relay: InputRelay | None = None

    def claim(self) -> object | None:
        if self.owner is not None:
            return None
        self.owner = object()
        self.disconnected = asyncio.Event()
        return self.owner

    async def accepting(self, owner: object) -> bool:
        run = await self.machine.store.get(self.machine.run_id)
        return (
            owner is self.owner
            and self.ready
            and run.status == RunStatus.PAUSED
            and self.machine.pause_reason in {"takeover", "handoff"}
        )

    async def release(self, owner: object | None = None) -> None:
        if owner is not None and self.owner is not owner:
            return
        self.disconnected.set()
        self.owner = None
        if self.relay:
            await self.relay.close()
            self.relay = None
