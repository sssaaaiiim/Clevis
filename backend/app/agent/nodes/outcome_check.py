import hashlib
from typing import Any

from app.agent.context import current_context, node
from app.agent.execution import AgentFailure
from app.agent.loops import fingerprint
from app.agent.state import AgentState, OutcomeVerdict


@node
async def outcome_node(state: AgentState) -> dict[str, Any]:
    context = current_context.get()
    # TODO Phase 2 Task 3: real outcome verification.
    state.outcome_verdict = OutcomeVerdict(achieved=True)
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
    return context.sync(state)
