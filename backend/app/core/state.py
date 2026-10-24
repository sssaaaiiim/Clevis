import asyncio
import logging
from enum import StrEnum
from time import monotonic
from typing import TYPE_CHECKING

from pydantic import Field

from app.browser.input_privacy import InputPrivacy
from app.core.events import (
    ApprovalPausedData,
    ApprovalRequest,
    EmptyData,
    Event,
    EventType,
    FailedData,
    FinishedData,
    HandoffData,
    Mode,
    Model,
    Plan,
    ReasonData,
    StartedData,
    make_event,
    utc_now,
)

if TYPE_CHECKING:
    from app.core.emitter import EventEmitter
    from app.core.store import RunStore

logger = logging.getLogger("clevis")


class RunStatus(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    FAILED = "failed"
    STOPPED = "stopped"


TERMINAL_STATES = {RunStatus.FINISHED, RunStatus.FAILED, RunStatus.STOPPED}
ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset({RunStatus.PLANNING, RunStatus.FAILED, RunStatus.STOPPED}),
    RunStatus.PLANNING: frozenset({RunStatus.RUNNING, RunStatus.FAILED, RunStatus.STOPPED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.PAUSED,
            RunStatus.FINISHED,
            RunStatus.FAILED,
            RunStatus.STOPPED,
        }
    ),
    RunStatus.PAUSED: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.FINISHED,
            RunStatus.FAILED,
            RunStatus.STOPPED,
        }
    ),
    RunStatus.FINISHED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.STOPPED: frozenset(),
}


class InvalidTransition(ValueError):
    pass


class RunRecord(Model):
    runId: str
    status: RunStatus = RunStatus.CREATED
    goal: str
    mode: Mode
    result: str | None = None
    error: str | None = None
    createdAt: str = Field(default_factory=utc_now)


class RunStateMachine:
    """One per run. The lock serializes control transitions and runner event batches."""

    def __init__(self, run_id: str, store: "RunStore", emitter: "EventEmitter") -> None:
        self.run_id = run_id
        self.store = store
        self.emitter = emitter
        self.lock = asyncio.Lock()
        self.cancelled = asyncio.Event()
        self.changed = asyncio.Event()
        self.paused_at: float | None = None
        self.paused_seconds = 0.0
        self.resume_count = 0
        self.input_privacy = InputPrivacy()
        self.pause_reason: str | None = None
        self.in_flight: asyncio.Future[object] | None = None
        self.control_lock = asyncio.Lock()
        self.approval_decisions: asyncio.Queue[str] = asyncio.Queue(maxsize=1)

    def elapsed(self, since: float) -> float:
        now = monotonic()
        pending = 0.0 if self.paused_at is None else now - self.paused_at
        return max(0.0, now - since - self.paused_seconds - pending)

    async def transition(
        self,
        target: RunStatus,
        *,
        expected: RunStatus | None = None,
        reason: str = "operator",
        message: str = "",
        plan: Plan | None = None,
        result: str = "Task finished.",
        error: str = "Run failed.",
        approval: ApprovalRequest | None = None,
    ) -> RunRecord:
        async with self.lock:
            run = await self.store.get(self.run_id)
            if expected is not None and run.status != expected:
                raise InvalidTransition(f"Expected {expected}, found {run.status}.")
            if target not in ALLOWED_TRANSITIONS[run.status]:
                raise InvalidTransition(f"Cannot transition from {run.status} to {target}.")
            event: Event
            if target == RunStatus.PLANNING:
                event = make_event(
                    self.run_id, EventType.RUN_STARTED, StartedData(goal=run.goal, mode=run.mode)
                )
            elif target == RunStatus.RUNNING:
                if run.status == RunStatus.PAUSED:
                    self.resume_count += 1
                    event = make_event(
                        self.run_id, EventType.RUN_RESUMED, ReasonData(reason=reason)
                    )
                else:
                    if plan is None:
                        raise ValueError("A plan is required to start running.")
                    event = make_event(self.run_id, EventType.PLAN_CREATED, plan)
            elif target == RunStatus.PAUSED:
                event = make_event(
                    self.run_id,
                    EventType.RUN_PAUSED,
                    ApprovalPausedData(request=approval)
                    if reason == "approval" and approval is not None
                    else HandoffData(message=message[:300])
                    if reason == "handoff"
                    else ReasonData(reason=reason),
                )
            elif target == RunStatus.FINISHED:
                run = run.model_copy(update={"result": result})
                event = make_event(self.run_id, EventType.RUN_FINISHED, FinishedData(result=result))
            elif target == RunStatus.FAILED:
                run = run.model_copy(update={"error": error})
                event = make_event(self.run_id, EventType.RUN_FAILED, FailedData(error=error))
            else:
                self.cancelled.set()
                event = make_event(self.run_id, EventType.RUN_STOPPED, EmptyData())
            if run.status == RunStatus.PAUSED and self.paused_at is not None:
                self.paused_seconds += monotonic() - self.paused_at
                self.paused_at = None
                self.pause_reason = None
            if target == RunStatus.PAUSED:
                self.paused_at = monotonic()
                self.pause_reason = reason
            run = run.model_copy(update={"status": target})
            await self.store.update(run)
            await self.emitter.emit(self.run_id, event)
            self.changed.set()
            logger.info("state.transition", extra={"runId": self.run_id, "status": target.value})
            return run
