from typing import Any

from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt

from app.agent.context import current_context, record_result, sanitized_graph_error
from app.agent.execution import AgentFailure
from app.agent.state import AgentState
from app.core.state import RunStatus
from app.interfaces.browser import ActionResult
from app.interfaces.validator import NetworkPolicy, Verdict


async def approval_gate_node(state: AgentState) -> dict[str, Any]:
    try:
        return await _approval_gate(state)
    except GraphInterrupt:
        raise
    except Exception as exc:
        raise sanitized_graph_error(exc, current_context.get()) from None


async def _approval_gate(state: AgentState) -> dict[str, Any]:
    # This node deliberately does not use @node: its resume must enter while paused,
    # and GraphInterrupt must reach LangGraph without being sanitized as an error.
    context = current_context.get()
    request = state.pending_approval
    if request is None:
        raise AgentFailure("Approval request is missing.")
    run = await context.store.get(state.run_id)
    if run.status != RunStatus.PAUSED:
        await context.execution.checkpoint()
        await context.machine.transition(RunStatus.PAUSED, reason="approval", approval=request)
    elif context.machine.pause_reason != "approval":
        raise AgentFailure("Approval cannot resume a browser takeover pause.")
    answer = interrupt(request.model_dump(mode="json"))
    if not isinstance(answer, dict) or answer.get("decision") not in {"approved", "denied"}:
        raise AgentFailure("Invalid approval decision.")
    approved = answer["decision"] == "approved"
    if approved and isinstance(context.validator, NetworkPolicy) and context.action:
        context.validator.authorize_destination(state, context.action)
    await context.machine.transition(RunStatus.RUNNING, reason="approval")
    state.turn_epoch = context.machine.resume_count
    state.status = "running"
    state.pending_approval = None
    state.validator_verdict = Verdict(
        verdict="allow" if approved else "deny",
        tier=2,
        reason="Human approved the action." if approved else "Human denied the action.",
    )
    if not approved:
        await record_result(state, ActionResult(ok=False, summary="Human denied the action."))
    return context.sync(state)
