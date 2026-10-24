from typing import Any

from app.agent.context import current_context, node
from app.agent.state import AgentState


@node
async def next_sub_goal_node(state: AgentState) -> dict[str, Any]:
    if state.current_sub_goal_idx + 1 < len(state.sub_goals):
        state.sub_goals[state.current_sub_goal_idx].status = "completed"
        state.current_sub_goal_idx += 1
        state.current_sub_goal_attempts = 0
        state.sub_goal_steps = 0
        state.candidate_result = None
        state.result = None
        state.planner_revision = None
        state.progress_count = 0
        state.progress_fingerprint = None
        state.previous_action_hash = None
        state.repetitions = 0
    state.status = "running"
    return current_context.get().sync(state)
