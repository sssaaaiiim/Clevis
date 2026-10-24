"""Per-run dependencies and transient private data; never part of a checkpoint."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, fields
from functools import wraps
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from app.agent.execution import AgentFailure, TurnInterrupted, _Execution
from app.agent.policy.dataflow import DataFlowLimit
from app.agent.state import AgentState, HistoryStep, StepRecord
from app.config import Settings
from app.core.budgets import Budget, BudgetExceeded
from app.core.emitter import EventEmitter
from app.core.events import Action, EventType, ExecutedData, make_event, utc_now
from app.core.state import RunStateMachine
from app.core.store import RunStore
from app.interfaces.browser import (
    ActionResult,
    BrowserDriver,
    BrowserFailure,
    Observation,
    PreviewChannel,
)
from app.interfaces.llm import LLMClient, LLMError, LLMOutputError
from app.interfaces.skills import SkillProvider
from app.interfaces.validator import ActionValidator


@dataclass
class RunContext:
    store: RunStore
    emitter: EventEmitter
    machine: RunStateMachine
    driver: BrowserDriver
    llm: LLMClient
    validator: ActionValidator
    skills: SkillProvider
    options: Settings
    external_budget: Budget
    execution: _Execution
    preview: PreviewChannel | None = None
    on_handoff: Callable[[str], Awaitable[None]] | None = None
    action: Action | None = None
    observation: Observation | None = None
    closed: bool = False
    goal: str = ""

    def sync(self, state: AgentState) -> dict[str, Any]:
        for item in fields(Budget):
            setattr(self.external_budget, item.name, getattr(state.budget, item.name))
        data = state.model_dump(mode="json")
        data["goal"] = self.execution.safe_text(state.goal)
        if data["plan"]:
            for step in data["plan"]["steps"]:
                step["text"] = self.execution.safe_text(step["text"])
        for goal in data["sub_goals"]:
            goal["description"] = self.execution.safe_text(goal["description"])
            goal["success_condition"] = self.execution.safe_text(goal["success_condition"])
        return data

    def safe_observation(self, observation: Observation) -> Observation:
        """Checkpoint only the redacted projection, never the raw page observation."""
        data = observation.model_dump(mode="json")

        def clean(value: Any) -> Any:
            if isinstance(value, str):
                return self.execution.safe_text(value)
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()}
            return value

        data = clean(data)
        data["url"] = safe_url(observation.url)
        for element in data["elements"]:
            if element["href"]:
                element["href"] = safe_url(element["href"])
            if element["form_action"]:
                element["form_action"] = safe_url(element["form_action"])
        return Observation.model_validate(data)


current_context: ContextVar[RunContext] = ContextVar("agent_run_context")


def safe_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))


def value_hash(value: str | None) -> str | None:
    return hashlib.sha256(value.encode()).hexdigest() if value is not None else None


def private_action(action: Action, context: RunContext) -> Action:
    data = action.model_dump()
    data["value"] = None
    data["rationale"] = context.execution.safe_text(action.rationale)[:300]
    data["target"]["ref"] = (
        context.execution.safe_text(action.target.ref) if action.target.ref else None
    )
    data["target"]["description"] = (
        context.execution.safe_text(action.target.description)
        if action.target.description
        else None
    )
    return Action.model_validate(data)


class Node(Protocol):
    def __call__(self, state: AgentState) -> Awaitable[dict[str, Any]]: ...


def sanitized_graph_error(exc: Exception, context: RunContext) -> AgentFailure:
    # MemorySaver also checkpoints error channels. Sanitize before LangGraph sees the error,
    # not only when the runner converts it to an SSE run.failed event.
    if isinstance(exc, LLMError):
        marker = str(exc).lower()
        if "invalid api key or no access" in marker:
            message = "OpenRouter: invalid API key or no access."
        elif marker.startswith("max_tokens"):
            message = "MAX_TOKENS exceeded during LLM requests."
        elif marker.startswith("max_cost_usd"):
            message = "MAX_COST_USD exceeded during LLM requests."
        elif isinstance(exc, LLMOutputError):
            message = "LLM output was invalid after retries."
        else:
            message = "LLM request failed; check provider access, timeouts and output validity."
    elif isinstance(exc, (AgentFailure, BrowserFailure, BudgetExceeded, DataFlowLimit)):
        message = context.execution.safe_text(str(exc))
    else:
        message = f"Unexpected {type(exc).__name__} during agent execution."
    return AgentFailure(message)


def node(operation: Node) -> Node:
    @wraps(operation)
    async def wrapped(state: AgentState) -> dict[str, Any]:
        context = current_context.get()
        context.execution.budget = state.budget
        try:
            await context.execution.checkpoint()
            state.status = (await context.store.get(state.run_id)).status.value
            return await operation(state)
        except TurnInterrupted:
            context.action = None
            context.observation = None
            state.reroute = True
            state.last_action = None
            return context.sync(state)
        except Exception as exc:
            if isinstance(exc, LLMError):
                state.budget.add_usage(exc.usage)
            context.sync(state)
            raise sanitized_graph_error(exc, context) from None

    return wrapped


async def record_result(state: AgentState, result: ActionResult) -> dict[str, Any]:
    context = current_context.get()
    execution = context.execution
    action, observation = context.action, context.observation
    assert action is not None and observation is not None
    step_id = state.budget.steps_used
    summary = execution.safe_text(result.summary)[:1000]
    target_name = execution.safe_text(
        next(
            (element.name for element in observation.elements if element.ref == action.target.ref),
            "",
        )
    )
    record = StepRecord(
        step_id=step_id,
        sub_goal_id=(state.sub_goals[state.current_sub_goal_idx].id if state.sub_goals else None),
        action=action.action,
        target_ref=execution.safe_text(action.target.ref) if action.target.ref else None,
        target_desc=target_name,
        value_hash=value_hash(action.value),
        result_summary=summary,
        ok=result.ok,
        ts=utc_now(),
    )
    limit = context.options.max_history_steps_in_prompt
    state.step_history = [*state.step_history, record][-limit:]
    state.history = [
        HistoryStep(
            step_id=item.step_id,
            action=item.action,
            ref=item.target_ref,
            target_name=item.target_desc,
            ok=item.ok,
            summary=item.result_summary,
        )
        for item in state.step_history
    ]
    state.last_action_result = result.model_copy(update={"summary": summary})
    state.stale_attempts = (
        state.stale_attempts + 1 if result.error_code in {"STALE_REF", "NOT_FOUND"} else 0
    )
    state.invalid_action_attempts = (
        state.invalid_action_attempts + 1
        if not result.ok and result.error_code == "INVALID_ACTION"
        else 0
    )
    state.budget.seconds_used = context.machine.elapsed(execution.started)
    context.sync(state)
    await execution.publish(
        make_event(
            state.run_id,
            EventType.STEP_EXECUTED,
            ExecutedData(
                stepId=step_id,
                ok=result.ok,
                resultSummary="Extracted visible text."
                if action.action == "extract" and result.ok
                else summary,
            ),
        ),
        make_event(state.run_id, EventType.BUDGET_UPDATE, state.budget.event_data()),
    )
    return context.sync(state)


def action_signature(action: Action) -> str:
    return hashlib.sha256(
        json.dumps(
            [
                action.action,
                action.target.ref,
                value_hash(action.value),
            ]
        ).encode()
    ).hexdigest()
