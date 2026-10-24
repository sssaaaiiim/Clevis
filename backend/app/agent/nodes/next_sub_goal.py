from typing import Any

from app.agent.context import current_context, node
from app.agent.state import AgentState


@node
async def next_sub_goal_node(state: AgentState) -> dict[str, Any]:
    # The always-achieved stub cannot establish task completion. Keep the final sub-goal
    # active until a valid done action, preserving Phase 1's external completion behavior.
    if state.current_sub_goal_idx + 1 < len(state.sub_goals):
        state.sub_goals[state.current_sub_goal_idx].status = "completed"
        state.current_sub_goal_idx += 1
        state.current_sub_goal_attempts = 0
        state.sub_goal_steps = 0
    state.status = "running"
    return current_context.get().sync(state)
