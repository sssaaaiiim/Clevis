from typing import Any

from app.agent import steps
from app.agent.context import current_context, node, record_result
from app.agent.state import AgentState
from app.core.events import EventType, ValidatedData, make_event
from app.interfaces.browser import ActionResult


@node
async def policy_node(state: AgentState) -> dict[str, Any]:
    context = current_context.get()
    if state.reroute:
        return context.sync(state)
    assert context.action is not None
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
        return await record_result(
            state,
            ActionResult(
                ok=False,
                summary="Action denied: " + verdict.reason,
            ),
        )
    return context.sync(state)
