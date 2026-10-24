from typing import Any

from app.agent import steps
from app.agent.context import current_context, node, record_result
from app.agent.execution import AgentFailure
from app.agent.state import AgentState
from app.core.state import RunStatus
from app.interfaces.browser import ActionResult, PausableDriver


@node
async def executor_node(state: AgentState) -> dict[str, Any]:
    context = current_context.get()
    execution = context.execution
    action = context.action
    if state.reroute or state.turn_epoch != context.machine.resume_count:
        state.reroute = True
        return context.sync(state)
    assert action is not None
    if action.action == "handoff":
        state.budget.handoffs_used += 1
        if state.budget.handoffs_used > context.options.max_handoffs:
            raise AgentFailure("MAX_HANDOFFS exceeded: too many human hand-offs.")
        message = execution.safe_text(
            action.value or "Please complete the task, then click Resume."
        )[:300]
        await record_result(state, ActionResult(ok=True, summary="Human hand-off requested."))
        if context.on_handoff is not None:
            await context.on_handoff(message)
        else:
            if isinstance(context.driver, PausableDriver):
                await context.driver.pause_actions()
            await context.machine.transition(RunStatus.PAUSED, reason="handoff", message=message)
        state.progress_fingerprint = None
        state.progress_count = 0
        state.status = "paused"
        state.reroute = True
        return context.sync(state)
    if action.action == "done" and not (action.value or "").strip():
        state.empty_done_attempts += 1
        if state.empty_done_attempts > 1:
            raise AgentFailure("Done requires a nonempty final result (retried once).")
        result = ActionResult(ok=False, summary="Final result is empty; provide a result.")
    else:
        result = await execution.call(steps.act, context.driver, action)
    if action.action == "type" and action.value and "password field" in result.summary:
        execution.secret_values.add(action.value)
    await record_result(state, result)
    if state.stale_attempts >= 3:
        raise AgentFailure("Three consecutive stale/not-found references; cannot proceed.")
    if state.invalid_action_attempts >= 3:
        raise AgentFailure(
            "Three consecutive invalid browser actions; could not correct the action."
        )
    if not result.ok and result.error_code not in {
        None,
        "STALE_REF",
        "NOT_FOUND",
        "PAUSED",
        "INVALID_ACTION",
    }:
        raise AgentFailure(
            "Browser action failed: "
            + str(result.error_code)
            + " during "
            + action.action
            + ". See the preceding Browser update."
        )
    if steps.check_done(action, result):
        state.result = execution.safe_text(action.value or "", public_result=True)
    return context.sync(state)
