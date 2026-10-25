from time import monotonic
from typing import Any
from uuid import uuid4

import pytest

from app.core.events import Action, Target
from tests.eval.scenarios.base import EvalScenario
from tests.eval.scenarios.test_policy_eval import done, navigate
from tests.settings import IsolatedSettings


@pytest.mark.parametrize(
    "name",
    [
        "ApproveAndContinue",
        "DenyAndRepropose",
        "StaleApprovalId",
        "ApprovalTimeout",
        "ApprovalTokenMissing",
    ],
)
async def test_approval_scenarios(name: str, testsite: str, evaluate: Any) -> None:
    actions = [
        navigate(testsite + "/form.html"),
        Action(action="click", target=Target(description="Submit form"), rationale="Submit."),
    ]
    if name == "DenyAndRepropose":
        actions.append(
            Action(action="click", target=Target(description="Newsletter"), rationale="Select.")
        )
    actions.append(done())
    scenario = EvalScenario(
        goal="Submit the local form",
        expected_outcome="failed" if name == "ApprovalTimeout" else "finished",
        expected_events=["approval.required", "run.paused"],
    )
    run = await evaluate(
        actions, settings=IsolatedSettings(require_approval_for_submit=True, approval_timeout_s=1)
    )
    await run.start(scenario)
    approval_id = await run.pending()
    started = monotonic()
    if name == "StaleApprovalId":
        assert (await run.decide("approve", str(uuid4()))).status_code == 422
        assert (await run.app.state.service.store.get(run.run_id)).status == "paused"
    if name == "ApprovalTokenMissing":
        assert (await run.decide("approve", auth=False)).status_code == 401
    if name != "ApprovalTimeout":
        assert (
            await run.decide("deny" if name == "DenyAndRepropose" else "approve", approval_id)
        ).status_code == 200
    state = await run.finish(scenario)
    if name == "ApprovalTimeout":
        assert state.error == "Approval timed out" and monotonic() - started < 2
    else:
        events = await run.events()
        assert any(e.type == "run.resumed" for e in events)
        assert any(e.type == "step.executed" and e.data.ok for e in events)
