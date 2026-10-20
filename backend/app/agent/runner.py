import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import ParamSpec, TypeVar
from urllib.parse import urlsplit

from app.agent import steps
from app.agent.loops import NoProgress
from app.agent.prompts import redact
from app.agent.state import AgentState, HistoryStep
from app.config import Settings
from app.core.budgets import Budget, BudgetExceeded
from app.core.emitter import EventEmitter
from app.core.events import (
    Event,
    EventType,
    ExecutedData,
    ObservationData,
    ProposedData,
    make_event,
)
from app.core.state import TERMINAL_STATES, InvalidTransition, RunStateMachine, RunStatus
from app.core.store import RunStore
from app.interfaces.browser import ActionResult, BrowserDriver, BrowserFailure, PreviewChannel
from app.interfaces.llm import LLMClient, LLMError
from app.interfaces.skills import SkillProvider
from app.interfaces.validator import ActionValidator

logger = logging.getLogger("clevis")
T = TypeVar("T")
P = ParamSpec("P")


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
        self.api_key = api_key

    def safe_text(self, text: str) -> str:
        text = redact(text, self.api_key)
        if not self.typed_values:
            return text
        pattern = "|".join(
            re.escape(value) for value in sorted(self.typed_values, key=len, reverse=True)
        )
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
    settings: Settings | None = None,
) -> None:
    """Dependencies are injected; this module has no dependency on fake implementations."""
    options = settings or Settings(_env_file=None)
    execution = _Execution(machine, budget, emitter, options.openrouter_api_key.get_secret_value())
    closed = False
    stopping = False

    async def ignore_frame(frame: bytes) -> None:
        # Preview transport is reserved for Task 5/6; never put image data on the timeline.
        return None

    try:
        run = await store.get(run_id)
        await machine.transition(RunStatus.PLANNING)
        await execution.call(driver.start, run.mode)
        await execution.call(driver.navigate, "about:blank")
        # Skills are retrieved through the interface; website content is never a system instruction.
        await execution.call(skills.get_skills, run.goal, "about:blank")
        state = AgentState(goal=run.goal)
        planned = await execution.call(steps.plan, llm, run.goal)
        budget.add_usage(planned.usage, planned.tokens_used)
        state.plan = planned.parsed
        await machine.transition(RunStatus.RUNNING, plan=planned.parsed)
        if preview is not None:
            await execution.call(preview.start_stream, ignore_frame)
        previous: tuple[str, str | None, str | None] | None = None
        repetitions = 0
        no_progress = NoProgress()
        recent: list[str] = []
        while True:
            await execution.checkpoint()
            if budget.steps_used >= budget.max_steps:
                raise BudgetExceeded(f"MAX_STEPS exceeded after {budget.steps_used} steps.")
            epoch = machine.resume_count
            observation = await execution.call(steps.observe, driver)
            step_id = budget.steps_used + 1
            path = urlsplit(observation.url).path
            await execution.publish(
                make_event(
                    run_id,
                    EventType.OBSERVATION_SUMMARY,
                    ObservationData(
                        stepId=step_id,
                        summary=execution.safe_text(
                            f"{observation.title[:160]} | {path[:160]} | "
                            f"{len(observation.elements)} elements"
                        )[:1000],
                    ),
                )
            )
            response = await execution.call(
                steps.propose,
                llm,
                state,
                observation,
                budget.max_steps - budget.steps_used,
                options.max_history_steps_in_prompt,
                execution.api_key,
            )
            action = response.parsed
            budget.add_usage(response.usage, response.tokens_used)
            budget.steps_used += 1
            if action.action == "type" and action.value:
                execution.typed_values.add(action.value)
            if epoch != machine.resume_count:
                await execution.publish(
                    make_event(run_id, EventType.BUDGET_UPDATE, budget.event_data())
                )
                continue  # A resumed run must re-observe and propose using fresh refs.
            state.current_plan_step = action.plan_step_id
            signature = (action.action, action.target.ref, action.value)
            repetitions = repetitions + 1 if signature == previous else 1
            previous = signature
            recent = [
                *recent[-4:],
                f"{action.action} {execution.safe_text(action.target.ref or '-')}",
            ]
            if repetitions >= 3:
                raise AgentFailure(
                    "Loop detected: same action, target and value 3 times in a row. Recent: "
                    + "; ".join(recent)
                )
            await execution.publish(
                make_event(
                    run_id,
                    EventType.STEP_PROPOSED,
                    ProposedData(
                        stepId=step_id,
                        planStepId=action.plan_step_id,
                        action=action.action,
                        target=action.target.model_copy(
                            update={
                                "description": execution.safe_text(action.target.description)
                                if action.target.description is not None
                                else None
                            }
                        ),
                        value="[redacted]"
                        if action.action == "type" and action.value is not None
                        else execution.safe_text(action.value)
                        if action.value is not None
                        else None,
                        rationale=execution.safe_text(action.rationale)[:300],
                    ),
                )
            )
            verdict = await execution.call(
                steps.validate, validator, await store.get(run_id), action
            )
            if epoch != machine.resume_count:
                await execution.publish(
                    make_event(run_id, EventType.BUDGET_UPDATE, budget.event_data())
                )
                continue
            if verdict.verdict != "allow":
                result = ActionResult(ok=False, summary="Action denied: " + verdict.reason)
            elif action.action == "done" and not (action.value or "").strip():
                state.empty_done_attempts += 1
                if state.empty_done_attempts > 1:
                    raise AgentFailure("Done requires a nonempty final result (retried once).")
                result = ActionResult(ok=False, summary="Final result is empty; provide a result.")
            else:
                result = await execution.call(steps.act, driver, action)
            state.history.append(
                HistoryStep(
                    step_id=step_id,
                    action=action.action,
                    ref=action.target.ref,
                    ok=result.ok,
                    summary=execution.safe_text(result.summary)[:1000],
                )
            )
            if result.error_code in {"STALE_REF", "NOT_FOUND"}:
                state.stale_attempts += 1
            else:
                state.stale_attempts = 0
            budget.seconds_used = machine.elapsed(execution.started)
            await execution.publish(
                make_event(
                    run_id,
                    EventType.STEP_EXECUTED,
                    ExecutedData(
                        stepId=step_id,
                        ok=result.ok,
                        resultSummary=execution.safe_text(result.summary)[:1000],
                    ),
                ),
                make_event(run_id, EventType.BUDGET_UPDATE, budget.event_data()),
            )
            if state.stale_attempts >= 3:
                raise AgentFailure("Three consecutive stale/not-found references; cannot proceed.")
            if not result.ok and result.error_code not in {
                None,
                "STALE_REF",
                "NOT_FOUND",
                "PAUSED",
            }:
                raise AgentFailure("Browser action failed: " + str(result.error_code))
            if steps.check_done(action, result):
                await execution.call(driver.close)
                closed = True
                await execution.finish(execution.safe_text(action.value or ""))
                return
            if no_progress.record(observation, result.ok):
                raise AgentFailure(
                    "Loop detected: no page progress over 5 successful steps. Recent: "
                    + "; ".join(recent)
                )
    except asyncio.CancelledError:
        stopping = True
    except Exception as exc:
        error = (
            str(exc)
            if isinstance(exc, (BudgetExceeded, AgentFailure, BrowserFailure, LLMError))
            else (f"Unexpected {type(exc).__name__} during agent execution.")
        )
        logger.error("agent.failed", extra={"runId": run_id, "errorType": type(exc).__name__})
        if isinstance(exc, LLMError):
            budget.add_usage(exc.usage)
        budget.seconds_used = machine.elapsed(execution.started)
        if (await store.get(run_id)).status not in TERMINAL_STATES:
            await emitter.emit(
                run_id, make_event(run_id, EventType.BUDGET_UPDATE, budget.event_data())
            )
            await machine.transition(RunStatus.FAILED, error=execution.safe_text(error))
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
        try:
            async with asyncio.timeout(0.5):
                await llm.close()
        except Exception as exc:
            logger.error(
                "agent.llm_cleanup_failed",
                extra={
                    "runId": run_id,
                    "errorType": type(exc).__name__,
                },
            )
        if stopping and (await store.get(run_id)).status not in TERMINAL_STATES:
            await machine.transition(RunStatus.STOPPED)
