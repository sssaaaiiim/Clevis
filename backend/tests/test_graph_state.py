import json

from app.agent.context import value_hash
from app.agent.state import AgentState, StepRecord, SubGoal
from app.core.events import utc_now


def test_graph_state_is_json_serializable_and_hashes_values() -> None:
    secret = "CANARY-PASSWORD-9137"
    state = AgentState(
        goal="Read a page",
        sub_goals=[
            SubGoal(
                id=1,
                description="Read",
                success_condition="Page read",
            )
        ],
        step_history=[
            StepRecord(
                step_id=1,
                action="type",
                value_hash=value_hash(secret),
                result_summary="Typed.",
                ok=True,
                ts=utc_now(),
            )
        ],
    )
    data = json.dumps(state.model_dump(mode="json"))
    assert secret not in data
    assert "value" not in state.step_history[0].model_dump()
    assert state.step_history[0].value_hash == value_hash(secret)
    restored = AgentState.model_validate_json(data)
    assert restored == state
    assert restored.budget.handoffs_used == 0
