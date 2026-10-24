from typing import Any

from app.agent.context import current_context, node
from app.agent.state import AgentState


@node
async def revise_node(state: AgentState) -> dict[str, Any]:
    # TODO Phase 2 Task 3: real revision logic.
    state.current_sub_goal_attempts += 1
    goal = state.sub_goals[state.current_sub_goal_idx]
    if state.current_sub_goal_attempts > goal.max_attempts:
        goal.status = "failed"
        state.current_sub_goal_idx += 1
        state.current_sub_goal_attempts = 0
        state.planner_revision = None
        if state.current_sub_goal_idx >= len(state.sub_goals):
            state.error = "No remaining sub-goal could be completed."
    else:
        state.planner_revision = "Revise the remaining sub-goals after an unachieved outcome."
    return current_context.get().sync(state)
