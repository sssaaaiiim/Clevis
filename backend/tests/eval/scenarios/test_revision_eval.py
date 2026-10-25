from typing import Any

import pytest

from app.agent.revisions import build_revision_message
from app.agent.state import SubGoal
from tests.eval.scenarios.base import EvalScenario
from tests.eval.scenarios.test_policy_eval import done, navigate
from tests.settings import IsolatedSettings


@pytest.mark.parametrize(
    "name", ["RevisionMessageFormat", "PlannerReentrySkipsCompleted", "MaxRevisionsFailsCleanly"]
)
async def test_revision_scenarios(name: str, testsite: str, evaluate: Any) -> None:
    if name == "RevisionMessageFormat":
        message = build_revision_message(
            SubGoal(id=2, description="Read", success_condition="Read"),
            "Expected confirmation missing",
            [],
            1,
        )
        assert len(message) <= 300 and "Sub-goal 2" in message and "confirmation" in message
    actions = [navigate(testsite + "/form.html"), done(), done()]
    scenario = EvalScenario(
        goal="Verify local confirmation", expected_events=["step.proposed", "run.finished"]
    )
    run = await evaluate(
        actions, outcomes=[False, False], settings=IsolatedSettings(subgoal_max_attempts=1)
    )
    await run.start(scenario)
    state = await run.finish(scenario)
    assert state.result and "Partial result" in state.result and "sub-goal 1" in state.result
    if name == "PlannerReentrySkipsCompleted":
        from app.core.events import Plan, PlanStep

        plan = Plan(
            steps=[
                PlanStep(id=1, text="Read first page"),
                PlanStep(id=2, text="Read remaining page"),
            ]
        )
        actions = [navigate(testsite + "/form.html"), *[done() for _ in range(5)]]
        run = await evaluate(actions, outcomes=[True, False, False, True, True], plan=plan)
        await run.start(scenario)
        state = await run.finish(scenario)
        assert state.sub_goals[0].id == 1 and state.sub_goals[0].status == "completed"
        assert all(goal.status == "completed" for goal in state.sub_goals)
        plans = [event for event in await run.events() if event.type == "plan.created"]
        assert len(plans) == 2 and plans[1].data.steps[0].text == "Read first page"
