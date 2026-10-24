import pytest
from pydantic import ValidationError

from app.agent.policy.tiers import classify_action
from app.core.events import Action, Target
from app.interfaces.browser import Element, Observation
from tests.settings import PolicySettings


@pytest.mark.parametrize(
    "action,value,element,path,title,goal,tier",
    [
        ("navigate", "https://public.example/", {}, "/", "", "", 0),
        ("navigate", "javascript:alert(1)", {}, "/", "", "", 3),
        ("scroll", "down", {}, "/", "", "", 0),
        ("wait", "1", {}, "/", "", "", 0),
        ("extract", None, {}, "/", "", "", 0),
        ("click", None, {"role": "link"}, "/", "", "", 1),
        ("type", "hello", {"role": "textbox"}, "/", "", "", 1),
        ("click", None, {"type": "checkbox"}, "/", "", "", 1),
        ("type", "Option", {"tag": "select"}, "/", "", "", 1),
        ("click", None, {"type": "submit"}, "/", "", "", 2),
        ("type", "go", {"type": "submit"}, "/", "", "", 2),
        ("click", None, {"tag": "button", "form_action": "/form"}, "/", "", "", 2),
        ("click", None, {"role": "button", "name": "Submit"}, "/", "", "", 2),
        ("click", None, {"name": "Download report"}, "/", "", "", 2),
        ("click", None, {"download": True}, "/", "", "", 2),
        ("type", "ignored", {"type": "file"}, "/", "", "", 2),
        ("click", None, {"name": "Attach file"}, "/", "", "", 2),
        ("click", None, {"name": "Send", "form_name": "chat"}, "/", "", "", 2),
        ("scroll", "down", {}, "/checkout", "", "", 2),
        ("click", None, {}, "/", "Payment", "", 2),
        ("click", None, {}, "/bank/confirm", "", "", 3),
        ("click", None, {}, "/", "Confirm payment", "", 3),
        ("click", None, {"hidden": True}, "/checkout", "", "", 3),
        ("click", None, {"aria_hidden": True}, "/", "", "", 3),
        ("type", "generated", {"type": "password"}, "/", "", "", 3),
        ("type", "supplied", {"type": "password"}, "/", "", "Use supplied", 1),
        ("done", "Partial result", {}, "/bank/confirm", "", "", 0),
        ("handoff", "Please sign in", {}, "/checkout", "", "", 0),
    ],
)
def test_ordered_tier_rules(
    action: str,
    value: str | None,
    element: dict[str, object],
    path: str,
    title: str,
    goal: str,
    tier: int,
) -> None:
    data: dict[str, object] = {"ref": "e1", "name": "", "role": "button", "tag": "div", **element}
    observation = Observation(
        url="https://public.example" + path,
        title=title,
        elements=[Element.model_validate(data)],
    )
    proposed = Action.model_validate(
        {
            "action": action,
            "value": value,
            "target": {"ref": "e1"},
            "rationale": "Act.",
        }
    )
    assert (
        classify_action(
            proposed,
            observation,
            observation.url,
            PolicySettings(),
            user_goal=goal,
        ).tier
        == tier
    )


def test_keyboard_submit_and_independent_switches() -> None:
    action = Action(action="type", value="Enter", rationale="Submit.")
    assert classify_action(action, None, "https://example.com", PolicySettings()).tier == 2
    assert (
        classify_action(
            action,
            None,
            "https://example.com",
            PolicySettings(require_approval_for_submit=False),
        ).tier
        == 1
    )
    action = Action(action="click", target=Target(ref="e1"), rationale="Submit.")
    observation = Observation(
        elements=[Element(ref="e1", role="button", tag="button", name="Send")]
    )
    settings = PolicySettings(require_approval_for_submit=False)
    assert classify_action(action, observation, "https://example.com", settings).tier == 2


@pytest.mark.parametrize(
    "entry", ["https://example.com", "*.example.com", "bad host", "a..b", "-bad.com"]
)
def test_bad_domain_configuration_fails(entry: str) -> None:
    with pytest.raises(ValidationError):
        PolicySettings(allowed_domains=entry)
