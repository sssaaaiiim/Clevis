"""Thin bridge from the existing run task into LangGraph; all clients remain injected."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, fields
from typing import Any, cast

from langgraph.errors import NodeCancelledError
from langgraph.types import Command
from langsmith import tracing_context

from app.agent.context import RunContext, current_context
from app.agent.execution import AgentFailure
from app.agent.execution import TurnInterrupted as TurnInterrupted
from app.agent.execution import _Execution as _Execution
from app.agent.graph import agent_graph
from app.agent.nodes.finish import finish_node
from app.agent.state import AgentState, BudgetState
from app.config import Settings
from app.core.budgets import Budget, BudgetExceeded
from app.core.emitter import EventEmitter
from app.core.events import EventType, make_event
from app.core.state import TERMINAL_STATES, RunStateMachine, RunStatus
from app.core.store import RunStore
from app.interfaces.browser import (
    BrowserDriver,
    BrowserFailure,
    GuardedBrowserDriver,
    PreviewChannel,
)
from app.interfaces.llm import LLMClient, LLMError
from app.interfaces.skills import SkillProvider
from app.interfaces.validator import ActionValidator, NetworkPolicy

logger = logging.getLogger("clevis")


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
    on_handoff: Callable[[str], Awaitable[None]] | None = None,
    outcome_llm: LLMClient | None = None,
) -> None:
    """Dependencies are injected; this module has no dependency on fake implementations."""
    # Standalone callers get static defaults; the service injects validated env settings.
    options = settings or Settings.model_construct()
    execution = _Execution(machine, budget, emitter, options.openrouter_api_key.get_secret_value())
    stopping = False
    context = RunContext(
        store,
        emitter,
        machine,
        driver,
        llm,
        validator,
        skills,
        options,
        budget,
        execution,
        preview,
        on_handoff,
    )
    token = current_context.set(context)
    context.outcome_llm = outcome_llm

    async def ignore_frame(frame: bytes) -> None:
        # Preview is independent; never put frame bytes on the agent timeline.
        return None

    try:
        run = await store.get(run_id)
        context.goal = (
            run.goal.replace(execution.api_key, "[redacted]") if execution.api_key else run.goal
        )
        state = AgentState(
            run_id=run_id,
            goal=execution.safe_text(run.goal),
            mode=run.mode,
            budget=BudgetState(**asdict(budget)),
            status="planning",
        )
        execution.budget = state.budget
        await machine.transition(RunStatus.PLANNING)
        await execution.call(driver.start, run.mode)
        if isinstance(driver, GuardedBrowserDriver) and isinstance(validator, NetworkPolicy):
            await execution.call(driver.install_navigation_guard, validator.guard_url)
        if preview is not None:
            await execution.call(preview.start_stream, ignore_frame)
        await execution.call(driver.navigate, "about:blank")
        await execution.call(skills.get_skills, run.goal, "about:blank")
        # A graph step is a node, not a browser action; allow enough graph transitions.
        # Disable automatic external tracing even if unrelated shell tracing vars are set.
        with tracing_context(enabled=False):
            graph_input: AgentState | Command[Any] = state
            while True:
                if isinstance(graph_input, Command):
                    await agent_graph.ainvoke(
                        graph_input,
                        config={
                            "configurable": {"thread_id": run_id},
                            "recursion_limit": budget.max_steps * 12 + 100,
                        },
                    )
                else:
                    async for _ in agent_graph.astream(
                        graph_input,
                        config={
                            "configurable": {"thread_id": run_id},
                            "recursion_limit": budget.max_steps * 12 + 100,
                        },
                    ):
                        pass
                snapshot = await agent_graph.aget_state({"configurable": {"thread_id": run_id}})
                if not snapshot.interrupts:
                    break
                # Resume in the original task/context; never create a second graph producer.
                try:
                    decision = await asyncio.wait_for(
                        machine.approval_decisions.get(),
                        timeout=options.approval_timeout_s or None,
                    )
                except TimeoutError:
                    raise AgentFailure("Approval timed out") from None
                graph_input = Command(
                    resume={
                        "decision": decision,
                        "reason": machine.approval_decision_reason,
                    }
                )
                machine.approval_decision_reason = ""
    except (asyncio.CancelledError, NodeCancelledError):
        stopping = True
    except Exception as exc:
        budget = execution.budget
        error = (
            str(exc)
            if isinstance(exc, (BudgetExceeded, AgentFailure, BrowserFailure, LLMError))
            else (f"Unexpected {type(exc).__name__} during agent execution.")
        )
        logger.error("agent.failed", extra={"runId": run_id, "errorType": type(exc).__name__})
        if isinstance(exc, LLMError):
            budget.add_usage(exc.usage)
        budget.seconds_used = machine.elapsed(execution.started)
        try:
            budget.check()
        except BudgetExceeded as limit:
            error = str(limit)
        if (await store.get(run_id)).status not in TERMINAL_STATES:
            await emitter.emit(
                run_id, make_event(run_id, EventType.BUDGET_UPDATE, budget.event_data())
            )
            await finish_node(
                AgentState(
                    run_id=run_id,
                    goal="",
                    budget=cast(BudgetState, budget),
                    status="failed",
                    error=execution.safe_text(error),
                )
            )
    finally:
        try:
            async with asyncio.timeout(1):
                try:
                    if preview is not None:
                        await preview.stop_stream()
                finally:
                    if not context.closed:
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
                try:
                    await llm.close()
                finally:
                    if outcome_llm is not None and outcome_llm is not llm:
                        await outcome_llm.close()
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

        record = await store.get(run_id)
        if record.status in {RunStatus.FAILED, RunStatus.STOPPED}:
            try:
                await agent_graph.aupdate_state(
                    {"configurable": {"thread_id": run_id}},
                    {
                        "run_id": run_id,
                        "goal": execution.safe_text(record.goal),
                        "mode": record.mode,
                        "status": record.status.value,
                        "error": record.error,
                        "reroute": False,
                        "budget": asdict(execution.budget),
                    },
                    as_node="finish",
                )
            except Exception as exc:
                logger.error(
                    "agent.checkpoint_cleanup_failed",
                    extra={
                        "runId": run_id,
                        "errorType": type(exc).__name__,
                    },
                )

        for item in fields(Budget):
            setattr(context.external_budget, item.name, getattr(execution.budget, item.name))
        context.action = None
        context.observation = None
        context.goal = ""
        current_context.reset(token)
