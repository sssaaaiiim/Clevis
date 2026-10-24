import logging
from typing import Any
from uuid import uuid4

from app.agent import steps
from app.agent.context import current_context, node, record_result
from app.agent.state import AgentState
from app.core.events import ApprovalData, EventType, ValidatedData, make_event
from app.interfaces.browser import ActionResult
from app.interfaces.validator import ApprovalRequest, StateActionValidator

logger = logging.getLogger("clevis")


@node
async def policy_node(state: AgentState) -> dict[str, Any]:
    context = current_context.get()
    if state.reroute:
        return context.sync(state)
    assert context.action is not None
    if isinstance(context.validator, StateActionValidator):
        policy_state = state.model_copy(
            update={
                "goal": context.goal,
                "last_observation": context.observation,
            }
        )
        verdict = await context.execution.call(
            context.validator.validate_agent,
            policy_state,
            context.action,
        )
    else:
        verdict = await context.execution.call(
            steps.validate,
            context.validator,
            await context.store.get(state.run_id),
            context.action,
        )
    if state.turn_epoch != context.machine.resume_count:
        state.reroute = True
        return context.sync(state)
    state.validator_verdict = verdict.model_copy(
        update={
            "reason": context.execution.safe_text(verdict.reason),
        }
    )
    if context.options.policy_log_verdicts:
        logger.info(
            "policy.verdict",
            extra={
                "runId": state.run_id,
                "tier": verdict.tier,
                "action": context.action.action,
            },
        )
    await context.execution.publish(
        make_event(
            state.run_id,
            EventType.STEP_VALIDATED,
            ValidatedData(
                stepId=state.budget.steps_used,
                verdict=verdict.verdict,
                reason=state.validator_verdict.reason,
            ),
        )
    )
    if verdict.verdict == "deny":
        if state.denial_sub_goal != state.current_sub_goal_idx:
            state.consecutive_denials = 0
        state.denial_sub_goal = state.current_sub_goal_idx
        state.consecutive_denials += 1
        if state.consecutive_denials >= 3:
            state.error = (
                "Policy denied three consecutive actions on this sub-goal: "
                + state.validator_verdict.reason
            )
        return await record_result(
            state,
            ActionResult(
                ok=False,
                summary="Action denied: " + verdict.reason,
            ),
        )
    state.consecutive_denials = 0
    if verdict.verdict == "approval":
        state.status = "paused"
        state.pending_approval_id = str(uuid4())
        context.machine.pending_approval_id = state.pending_approval_id
        state.pending_approval = verdict.display or ApprovalRequest(
            action_summary="Approve the proposed browser action.",
            risk="medium",
            page_url="",
        )
        assert state.last_action is not None
        await context.execution.publish(
            make_event(
                state.run_id,
                EventType.APPROVAL_REQUIRED,
                ApprovalData(
                    stepId=state.budget.steps_used,
                    action=state.last_action,
                    risk=state.pending_approval.risk,
                    approval_id=state.pending_approval_id,
                    action_summary=state.pending_approval.action_summary,
                    page_domain=state.pending_approval.page_url,
                    tier=verdict.tier,
                ),
            )
        )
    return context.sync(state)
