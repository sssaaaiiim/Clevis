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
        offset = datetime.fromisoformat(event.ts.replace("Z", "+00:00")).utcoffset()
        assert offset is not None and offset.total_seconds() == 0
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
    for update in (
        {"type": "unknown"},
        {"seq": 0},
        {"ts": "yesterday"},
        {"ts": "2026-01-01T00:00:00"},
        {"data": {"goal": "test"}},
    ):
        with pytest.raises(ValidationError):
            EVENT_ADAPTER.validate_python(event.model_dump() | update)
    with pytest.raises(ValidationError):
        Action(action="click", rationale="x" * 301)
    with pytest.raises(ValidationError):
        Action.model_validate({"action": "done", "rationale": "Done.", "chain_of_thought": "no"})


def test_transition_policy_is_explicit() -> None:
    expected = {
        "created": {"planning", "failed", "stopped"},
        "planning": {"running", "failed", "stopped"},
        "running": {"paused", "finished", "failed", "stopped"},
        "paused": {"running", "finished", "failed", "stopped"},
        "finished": set(),
        "failed": set(),
        "stopped": set(),
    }
    assert {
        state.value: {target.value for target in targets}
        for state, targets in ALLOWED_TRANSITIONS.items()
    } == expected


@pytest.mark.parametrize(
    ("kind", "data"),
    [
        ("run.started", {"goal": "test", "mode": "headless"}),
        ("plan.created", {"steps": [{"id": 1, "text": "Open the page."}]}),
        (
            "step.proposed",
            {
                "stepId": 1,
                "planStepId": None,
                "action": "done",
                "target": {"ref": None, "description": None},
                "value": None,
                "rationale": "The goal is complete.",
            },
        ),
        ("step.executed", {"stepId": 1, "ok": True, "resultSummary": "Done."}),
        ("observation.summary", {"stepId": 1, "summary": "A short page summary."}),
        (
            "budget.update",
            {
                "stepsUsed": 1,
                "maxSteps": 30,
                "secondsUsed": 0.1,
                "maxSeconds": 300,
                "tokensUsed": 10,
                "maxTokens": 200000,
            },
        ),
        ("run.paused", {"reason": "takeover"}),
        ("run.resumed", {"reason": "operator"}),
        ("run.finished", {"result": "Done."}),
        ("run.failed", {"error": "An error occurred."}),
        ("run.stopped", {}),
        ("step.validated", {"stepId": 1, "verdict": "allow", "reason": "Safe."}),
        (
            "approval.required",
            {
                "stepId": 1,
                "action": {"action": "click", "rationale": "Submit the requested form."},
                "risk": "submission",
            },
        ),
    ],
)
def test_all_event_variants(kind: str, data: dict[str, object]) -> None:
    event = EVENT_ADAPTER.validate_python({"runId": "r", "seq": 1, "type": kind, "data": data})
    assert event.type == kind
    assert event.model_dump()["data"] == data or kind in {"approval.required", "budget.update"}
