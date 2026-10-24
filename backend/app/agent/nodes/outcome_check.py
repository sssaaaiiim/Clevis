import hashlib
from typing import Any

from app.agent import steps
from app.agent.context import current_context, node
from app.agent.execution import AgentFailure
from app.agent.loops import fingerprint
from app.agent.outcomes import check_outcome
from app.agent.state import AgentState
from app.core.events import EventType, make_event


@node
async def outcome_node(state: AgentState) -> dict[str, Any]:
    context = current_context.get()
    state.outcome_verdict = None
    observation, result = context.observation, state.last_action_result
    if (
        observation is not None
        and result is not None
        and state.result is None
        and not state.reroute
    ):
        current = hashlib.sha256((observation.url + fingerprint(observation)).encode()).hexdigest()
        state.progress_count = (
            (state.progress_count + 1 if current == state.progress_fingerprint else 1)
            if result.ok
            else 0
        )
        state.progress_fingerprint = current
        if state.progress_count >= 5:
            raise AgentFailure(
                "Loop detected: no page progress over 5 successful steps. Recent: "
                + "; ".join(state.recent_actions)
            )
    if state.reroute or not state.sub_goals:
        return context.sync(state)
    goal = state.sub_goals[state.current_sub_goal_idx]
    completed = bool(
        context.action and context.action.action == "done" and result and result.ok and state.result
    )
    if not completed and state.sub_goal_steps < goal.max_steps:
        return context.sync(state)
    state.candidate_result = state.result
    state.result = None
    observation = context.machine.input_privacy.observation(
        await context.execution.call(steps.observe, context.driver)
    )
    context.observation = observation
    state.last_observation = context.safe_observation(observation)
    response = await context.execution.call(
        check_outcome,
        goal,
        state.last_observation,
        state.step_history,
        context.outcome_llm or context.llm,
    )
    state.budget.add_usage(response.usage, response.tokens_used)
    state.outcome_verdict = response.parsed.model_copy(
        update={
            "reason": context.execution.safe_text(response.parsed.reason)[:120],
        }
    )
    await context.execution.publish(
        make_event(
            state.run_id,
            EventType.BUDGET_UPDATE,
            state.budget.event_data(),
        )
    )
    if state.outcome_verdict.achieved:
        goal.status = "completed"
        if state.current_sub_goal_idx + 1 == len(state.sub_goals):
            state.result = state.candidate_result or "All sub-goals were verified as completed."
    elif state.current_sub_goal_attempts >= goal.max_attempts:
        goal.status = "failed"
        completed_count = sum(g.status == "completed" for g in state.sub_goals)
        state.result = (
            f"Partial result: {completed_count} sub-goals completed; sub-goal {goal.id} "
            "could not be verified after the retry limit."
        )
    return context.sync(state)
