import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import ParamSpec, TypeVar

from app.core.budgets import Budget
from app.core.emitter import EventEmitter
from app.core.events import (
    Action,
    Event,
    EventType,
    ExecutedData,
    ObservationData,
    Plan,
    ProposedData,
    make_event,
)
from app.core.state import TERMINAL_STATES, InvalidTransition, RunStateMachine, RunStatus
from app.core.store import RunStore
from app.interfaces.browser import BrowserDriver, PreviewChannel
from app.interfaces.llm import LLMClient, Message
from app.interfaces.skills import SkillProvider
from app.interfaces.validator import ActionValidator

logger = logging.getLogger("clevis")
T = TypeVar("T")
P = ParamSpec("P")


class BudgetExceeded(RuntimeError):
    pass


class AgentFailure(RuntimeError):
    pass


class _Execution:
    def __init__(self, machine: RunStateMachine, budget: Budget, emitter: EventEmitter) -> None:
        self.machine = machine
        self.budget = budget
        self.emitter = emitter
        self.started = monotonic()

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
                    if self.budget.seconds_used >= self.budget.max_seconds:
                        raise BudgetExceeded("MAX_SECONDS exceeded.")
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
        await self.checkpoint()
        pending = asyncio.ensure_future(operation(*args, **kwargs))
        try:
            while not pending.done():
                await self.checkpoint()
                remaining = self.budget.max_seconds - self.budget.seconds_used
                await asyncio.wait({pending}, timeout=min(0.02, max(0, remaining)))
            await self.checkpoint()
            return pending.result()
        finally:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

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


async def run_agent(
    run_id: str,
    *,
    store: RunStore,
    emitter: EventEmitter,
    machine: RunStateMachine,
    driver: BrowserDriver,
    llm: LLMClient,
    validator: ActionValidator,
    skills: SkillProvider,
    budget: Budget,
    preview: PreviewChannel | None = None,
) -> None:
    """Dependencies are injected; this module has no dependency on fake implementations."""
    execution = _Execution(machine, budget, emitter)
    closed = False

    async def ignore_frame(frame: bytes) -> None:
        # Preview transport is reserved for Task 5/6; never put image data on the timeline.
        return None

    try:
        run = await store.get(run_id)
        await machine.transition(RunStatus.PLANNING)
        await execution.call(driver.start, run.mode)
        await execution.call(driver.navigate, "about:blank")
        available_skills = await execution.call(skills.get_skills, run.goal, "about:blank")
        messages = [Message(role="user", content=run.goal)]
        messages.extend(
            Message(role="system", content=skill.instructions) for skill in available_skills
        )
        planned = await execution.call(llm.propose, messages, Plan)
        budget.tokens_used += planned.tokens_used
        await machine.transition(RunStatus.RUNNING, plan=planned.parsed)
        if preview is not None:
            await execution.call(preview.start_stream, ignore_frame)
        previous: tuple[str, str | None] | None = None
        repetitions = 0
        while True:
            await execution.checkpoint()
            if budget.steps_used >= budget.max_steps:
                raise BudgetExceeded("MAX_STEPS exceeded.")
            observation = await execution.call(driver.observe)
            response = await execution.call(
                llm.propose,
                [*messages, Message(role="system", content=observation.summary)],
                Action,
            )
            action = response.parsed
            budget.tokens_used += response.tokens_used
            target = (
                action.target.ref if action.target.ref is not None else action.target.description
            )
            if target is None and action.action == "navigate":
                target = action.value
            signature = (action.action, target)
            repetitions = repetitions + 1 if signature == previous else 1
            previous = signature
            if repetitions >= 3:
                raise AgentFailure(
                    "Loop detected: same action on the same target 3 times in a row."
                )
            step_id = budget.steps_used + 1
            await execution.publish(
                make_event(
                    run_id,
                    EventType.STEP_PROPOSED,
                    ProposedData(
                        stepId=step_id,
                        planStepId=action.plan_step_id,
                        action=action.action,
                        target=action.target,
                        value=action.value,
                        rationale=action.rationale,
                    ),
                )
            )
            current = await execution.call(store.get, run_id)
            verdict = await execution.call(validator.validate, current, action)
            if verdict.verdict != "allow":
                raise AgentFailure(f"Action rejected: {verdict.reason}")
            result = await execution.call(driver.act, action)
            if not result.ok:
                raise AgentFailure("Browser action was unsuccessful.")
            if action.action == "extract":
                # Only a short result enters the event stream, never a full page dump.
                text = await execution.call(driver.get_text)
                result = result.model_copy(update={"summary": text[:1000]})
            budget.steps_used += 1
            budget.seconds_used = machine.elapsed(execution.started)
            await execution.publish(
                make_event(
                    run_id,
                    EventType.STEP_EXECUTED,
                    ExecutedData(
                        stepId=step_id,
                        ok=result.ok,
                        resultSummary=result.summary[:1000],
                    ),
                ),
                make_event(
                    run_id,
                    EventType.OBSERVATION_SUMMARY,
                    ObservationData(
                        stepId=step_id,
                        summary=observation.summary[:1000],
                    ),
                ),
                make_event(run_id, EventType.BUDGET_UPDATE, budget.event_data()),
            )
            if action.action == "done":
                await execution.call(driver.close)
                closed = True
                await execution.finish(action.value or result.summary[:1000])
                return
    except asyncio.CancelledError:
        if (await store.get(run_id)).status not in TERMINAL_STATES:
            await machine.transition(RunStatus.STOPPED)
        # Cancellation is handled as a terminal lifecycle event, including during shutdown.
    except Exception as exc:
        error = (
            str(exc)
            if isinstance(exc, (BudgetExceeded, AgentFailure))
            else (f"Unexpected {type(exc).__name__} during agent execution.")
        )
        logger.error("agent.failed", extra={"runId": run_id, "errorType": type(exc).__name__})
        if (await store.get(run_id)).status not in TERMINAL_STATES:
            await machine.transition(RunStatus.FAILED, error=error)
    finally:
        try:
            async with asyncio.timeout(1):
                if preview is not None:
                    await preview.stop_stream()
                if not closed:
                    await driver.close()
        except Exception as exc:
            logger.error(
                "agent.cleanup_failed",
                extra={
                    "runId": run_id,
                    "errorType": type(exc).__name__,
                },
            )
