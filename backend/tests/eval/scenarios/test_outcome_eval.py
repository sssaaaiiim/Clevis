from typing import Any

import pytest

from tests.eval.scenarios.base import EvalScenario
from tests.eval.scenarios.test_policy_eval import done, navigate
from tests.scripted_browser_llm import form_script


@pytest.mark.parametrize(
    "name",
    [
        "OutcomeAchievedFirstTry",
        "OutcomeFailedThenAchieved",
        "OutcomeMaxAttempts",
        "VerifierBudget",
    ],
)
async def test_outcome_scenarios(name: str, testsite: str, evaluate: Any) -> None:
    answers = (
        [False, True]
        if name == "OutcomeFailedThenAchieved"
        else [False] * 3
        if name == "OutcomeMaxAttempts"
        else [True]
    )
    actions = (
        form_script(testsite)
        if name == "OutcomeAchievedFirstTry"
        else [navigate(testsite + "/form.html")] + [done() for _ in answers]
    )
    scenario = EvalScenario(
        goal="Complete the local contact form",
        expected_events=["run.started", "plan.created", "run.finished"],
    )
    run = await evaluate(actions, outcomes=answers)
    await run.start(scenario)
    state = await run.finish(scenario)
    if name == "OutcomeFailedThenAchieved":
        assert any(
            e.type == "step.proposed" and e.data.action == "revise" for e in await run.events()
        )
    if name == "OutcomeMaxAttempts":
        assert state.result and "Partial result" in state.result and "sub-goal 1" in state.result
    if name == "VerifierBudget":
        # Plan+2 actor calls =30; verifier contributes 7 more tokens.
        assert state.budget.tokens_used == 37
