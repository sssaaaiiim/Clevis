import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import ParamSpec, TypeVar, cast

from app.agent.prompts import redact
from app.core.budgets import Budget
from app.core.emitter import EventEmitter
from app.core.events import (
    Event,
)
from app.core.state import TERMINAL_STATES, InvalidTransition, RunStateMachine, RunStatus

logger = logging.getLogger("clevis")
T = TypeVar("T")
P = ParamSpec("P")


class TurnInterrupted(Exception):
    """Discard an interrupted turn; resume always starts with a new observation."""


class AgentFailure(RuntimeError):
    pass


class _Execution:
    def __init__(
        self, machine: RunStateMachine, budget: Budget, emitter: EventEmitter, api_key: str
    ) -> None:
        self.machine = machine
        self.budget = budget
        self.emitter = emitter
        self.started = monotonic()
        self.typed_values: set[str] = set()
        self.public_values: set[str] = set()
        self.secret_values: set[str] = set()
        self.api_key = api_key

    def safe_text(self, text: str, *, public_result: bool = False) -> str:
        text = self.machine.input_privacy.scrub(redact(text, self.api_key))
        values = (
            (self.typed_values - self.public_values) | self.secret_values
            if public_result
            else self.typed_values
        )
        if not values:
            return text
        pattern = "|".join(re.escape(value) for value in sorted(values, key=len, reverse=True))
        return re.sub(pattern, "[redacted]", text)

    async def checkpoint(self) -> None:
        while True:
            async with self.machine.lock:
                run = await self.machine.store.get(self.machine.run_id)
                if self.machine.cancelled.is_set() or run.status in TERMINAL_STATES:
                    raise asyncio.CancelledError
                paused = run.status == RunStatus.PAUSED
                if paused:
                    self.machine.changed.clear()
                else:
                    self.budget.seconds_used = self.machine.elapsed(self.started)
                    self.budget.check()
                    return
            resumed = asyncio.create_task(self.machine.changed.wait())
            cancelled = asyncio.create_task(self.machine.cancelled.wait())
            try:
                await asyncio.wait({resumed, cancelled}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                resumed.cancel()
                cancelled.cancel()
                await asyncio.gather(resumed, cancelled, return_exceptions=True)

    async def call(
        self, operation: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs
    ) -> T:
        """Interrupt slow I/O on stop/deadline; defer its result while paused."""
        epoch = self.machine.resume_count
        await self.checkpoint()
        if epoch != self.machine.resume_count:
            raise TurnInterrupted
        pending = asyncio.ensure_future(operation(*args, **kwargs))
        self.machine.in_flight = cast(asyncio.Future[object], pending)
        try:
            while not pending.done():
                await self.checkpoint()
                remaining = self.budget.max_seconds - self.budget.seconds_used
                await asyncio.wait({pending}, timeout=min(0.02, max(0, remaining)))
            await self.checkpoint()
            if pending.cancelled() and not self.machine.cancelled.is_set():
                raise TurnInterrupted
            return pending.result()
        finally:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            if self.machine.in_flight is pending:
                self.machine.in_flight = None

    async def publish(self, *events: Event) -> None:
        while True:
            await self.checkpoint()
            async with self.machine.lock:
                run = await self.machine.store.get(self.machine.run_id)
                if run.status == RunStatus.RUNNING:
                    for event in events:
                        await self.emitter.emit(self.machine.run_id, event)
                    return
                if run.status in TERMINAL_STATES:
                    raise asyncio.CancelledError

    async def finish(self, result: str) -> None:
        while True:
            await self.checkpoint()
            try:
                await self.machine.transition(
                    RunStatus.FINISHED, expected=RunStatus.RUNNING, result=result
                )
                return
            except InvalidTransition:
                # A takeover may have won the lock after the checkpoint.
                continue
