from collections.abc import Callable
from typing import Any

import pytest

from app.agent import routing
from app.agent.state import AgentState, OutcomeVerdict
from app.interfaces.browser import ActionResult
from app.interfaces.validator import Verdict


@pytest.mark.parametrize("route,updates,expected", [
    (routing.after_planner, {}, "navigator"),
    (routing.after_planner, {"reroute": True}, "planner"),
    (routing.after_navigator, {}, "policy_check"),
    (routing.after_navigator, {"reroute": True}, "navigator"),
    (routing.after_navigator, {"error": "Failed"}, "finish"),
    (routing.after_policy, {}, "navigator"),
    (routing.after_policy, {"validator_verdict": Verdict(verdict="deny", reason="Denied")},
     "navigator"),
    (routing.after_policy, {"validator_verdict": Verdict(verdict="allow", reason="Allowed")},
     "executor"),
    (routing.after_policy, {"validator_verdict": Verdict(verdict="approval", reason="Approve")},
     "approval_gate"),
    (routing.after_policy, {"reroute": True}, "navigator"),
    (routing.after_approval, {}, "navigator"),
    (routing.after_approval, {"validator_verdict": Verdict(verdict="allow", reason="Approved")},
     "executor"),
    (routing.after_approval, {"validator_verdict": Verdict(verdict="deny", reason="Denied")},
     "navigator"),
    (routing.after_executor, {}, "outcome_check"),
    (routing.after_executor, {"reroute": True}, "navigator"),
    (routing.after_outcome, {}, "navigator"),
    (routing.after_outcome, {"error": "Failed"}, "finish"),
    (routing.after_outcome, {"result": "Complete"}, "finish"),
    (routing.after_outcome, {"last_action_result": ActionResult(ok=True, summary="Done"),
                           "outcome_verdict": OutcomeVerdict(achieved=True)}, "next_sub_goal"),
    (routing.after_outcome, {"last_action_result": ActionResult(ok=True, summary="Done"),
                           "outcome_verdict": OutcomeVerdict(achieved=False)}, "revise"),
    (routing.after_outcome, {"last_action_result": ActionResult(ok=False, summary="Retry")},
     "navigator"),
    (routing.after_revise, {}, "navigator"),
    (routing.after_revise, {"planner_revision": "Revise"}, "planner"),
    (routing.after_revise, {"error": "Failed"}, "finish"),
    (routing.after_next, {}, "navigator"),
    (routing.after_next, {"result": "Complete"}, "finish"),
    (routing.after_next, {"error": "Failed"}, "finish"),
    (routing.after_finish, {}, "__end__"),
    (routing.after_finish, {"reroute": True}, "navigator"),
])
def test_routes_are_pure(
    route: Callable[[AgentState], str], updates: dict[str, Any], expected: str,
) -> None:
    state = AgentState(goal="Local test").model_copy(update=updates)
    before = state.model_dump(mode="json")
    assert route(state) == expected
    assert state.model_dump(mode="json") == before
