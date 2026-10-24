from typing import Any

from app.agent.context import current_context, node
from app.agent.state import AgentState
from app.interfaces.validator import Verdict


@node
async def approval_gate_node(state: AgentState) -> dict[str, Any]:
    # TODO Phase 2 Task 3: replace this explicitly permissive stub with interrupt/Command.
    state.validator_verdict = Verdict(verdict="allow", reason="Approval gate skeleton approved.")
    return current_context.get().sync(state)
