from typing import Any

from app.agent.context import current_context, node
from app.agent.revisions import build_revision_message, outcome_feedback
from app.agent.state import AgentState, HistoryStep, StepRecord
from app.core.events import EventType, ProposedData, Target, make_event, utc_now


@node
async def revise_node(state: AgentState) -> dict[str, Any]:
    context = current_context.get()
    state.current_sub_goal_attempts += 1
    goal = state.sub_goals[state.current_sub_goal_idx]
    state.planner_revision = build_revision_message(
        goal,
        state.outcome_verdict.reason if state.outcome_verdict else "Not verified",
        state.step_history[-3:],
        state.current_sub_goal_attempts,
    )
    state.sub_goal_steps = 0
    state.last_observation = None
    state.result = None
    state.candidate_result = None
    state.progress_count = 0
    state.progress_fingerprint = None
    state.previous_action_hash = None
    state.repetitions = 0
    context.observation = None
    state.step_history = [
        *state.step_history,
        StepRecord(
            step_id=max(1, state.budget.steps_used),
            sub_goal_id=goal.id,
            action="revise",
            result_summary=state.planner_revision,
            ok=False,
            ts=utc_now(),
        ),
    ][-context.options.max_history_steps_in_prompt :]
    state.history = [
        *state.history,
        HistoryStep(
            step_id=max(1, state.budget.steps_used),
            action="revise",
            ok=False,
            summary=state.planner_revision,
        ),
    ][-context.options.max_history_steps_in_prompt :]
    await context.execution.publish(
        make_event(
            state.run_id,
            EventType.STEP_PROPOSED,
            ProposedData(
                stepId=max(1, state.budget.steps_used),
                planStepId=goal.id,
                action="revise",
                target=Target(),
                value=None,
                rationale=(
                    f"Sub-goal {goal.id} failed. "
                    + outcome_feedback(
                        state.outcome_verdict.reason if state.outcome_verdict else "Not verified"
                    )
                    + " Trying again."
                )[:300],
            ),
        )
    )
    return context.sync(state)
