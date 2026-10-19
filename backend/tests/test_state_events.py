from datetime import datetime
from itertools import product
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.events import (
    EVENT_ADAPTER,
    Action,
    EventType,
    Plan,
    PlanStep,
    StartedData,
    make_event,
)
from app.core.state import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    InvalidTransition,
    RunRecord,
    RunStateMachine,
    RunStatus,
)


@pytest.mark.parametrize(("source", "target"), list(product(RunStatus, repeat=2)))
async def test_every_transition(source: RunStatus, target: RunStatus) -> None:
    store = AsyncMock()
    emitter = AsyncMock()
    store.get.return_value = RunRecord(runId="r", goal="test", mode="headless", status=source)
    machine = RunStateMachine("r", store, emitter)
    if target in ALLOWED_TRANSITIONS[source]:
        result = await machine.transition(target, plan=Plan(steps=[PlanStep(id=1, text="Test")]))
        assert result.status == target
        store.update.assert_awaited_once()
        emitter.emit.assert_awaited_once()
        event = emitter.emit.call_args.args[1]
        EVENT_ADAPTER.validate_json(event.model_dump_json())
        assert datetime.fromisoformat(event.ts.replace("Z", "+00:00")).utcoffset().total_seconds() == 0
        assert machine.cancelled.is_set() == (target == RunStatus.STOPPED)
    else:
        with pytest.raises(InvalidTransition, match=f"from {source} to {target}"):
            await machine.transition(target)
        emitter.emit.assert_not_awaited()
    if source in TERMINAL_STATES:
        assert not ALLOWED_TRANSITIONS[source]


def test_event_union_and_action_validation() -> None:
    event = make_event("r", EventType.RUN_STARTED, StartedData(goal="test", mode="headless"))
    assert event.seq == 1
    assert EVENT_ADAPTER.validate_json(event.model_dump_json()) == event
    for update in ({"type": "unknown"}, {"seq": 0}, {"ts": "yesterday"},
                   {"ts": "2026-01-01T00:00:00"}, {"data": {"goal": "test"}}):
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_python(event.model_dump() | update)
    with pytest.raises(ValidationError):
        Action(action="click", rationale="x" * 301)
    with pytest.raises(ValidationError):
        Action.model_validate({"action": "done", "rationale": "Done.", "chain_of_thought": "no"})
