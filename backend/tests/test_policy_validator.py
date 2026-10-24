import json

import pytest

from app.agent.policy.dataflow import DataFlowTracker, content_hash
from app.agent.policy.validator import PolicyValidator
from app.agent.state import AgentState
from app.core.events import Action, Target
from app.interfaces.browser import Element, Observation
from app.interfaces.validator import Verdict
from tests.settings import IsolatedSettings


@pytest.mark.parametrize(
    "url,updates,decision,tier",
    [
        ("https://example.com", {}, "allow", 0),
        ("https://example.com", {"blocked_domains": "example.com"}, "deny", 3),
        ("https://example.com", {"allowed_domains": "other.example"}, "approve", 2),
        ("http://127.0.0.1", {}, "deny", 3),
        ("file:///etc/passwd", {}, "deny", 3),
        ("https://mixed.example", {}, "deny", 3),
    ],
)
async def test_domain_override(url: str, updates: dict[str, str], decision: str, tier: int) -> None:
    settings = IsolatedSettings.model_validate(updates)
    validator = PolicyValidator(
        settings,
        resolver=lambda host: (
            [
                "8.8.8.8",
                "10.0.0.1",
            ]
            if host == "mixed.example"
            else ["8.8.8.8"]
        ),
    )
    verdict = await validator.validate(
        AgentState(goal="Test"),
        Action(action="navigate", value=url, rationale="Open page."),
    )
    assert verdict.decision == decision and verdict.tier == tier
    if tier == 2:
        assert verdict.display and verdict.display.page_url == "example.com"


async def test_submit_cross_domain_and_sanitized_display() -> None:
    secret = "a sufficiently long fictional confidential value"
    observation = Observation(
        url="https://destination.example/path?secret=hidden",
        title="Page",
        elements=[Element(ref="e1", name="CANARY", role="button", tag="button", type="submit")],
    )
    state = AgentState(goal="Test", last_observation=observation)
    tracker = DataFlowTracker(state.data_flow)
    tracker.record_extraction("source.example", content_hash(secret), len(secret))
    validator = PolicyValidator(IsolatedSettings(), resolver=lambda _: ["8.8.8.8"])
    for action in [
        Action(action="click", target=Target(ref="e1"), rationale="Click."),
        Action(action="type", value=secret, rationale="Fill."),
    ]:
        verdict = await validator.validate(state, action)
        assert verdict.decision == "approve" and verdict.tier == 2
        serialized = verdict.model_dump_json()
        assert secret not in serialized and "CANARY" not in serialized and "?" not in serialized
        assert verdict.display and verdict.display.page_url == "destination.example"
    assert secret not in json.dumps(state.data_flow, default=str)


async def test_blocked_link_and_denied_current_page() -> None:
    validator = PolicyValidator(
        IsolatedSettings(blocked_domains="blocked.example"),
        resolver=lambda _: ["8.8.8.8"],
    )
    state = AgentState(
        goal="Test",
        last_observation=Observation(
            url="https://example.com",
            elements=[
                Element(
                    ref="e1",
                    name="Link",
                    tag="a",
                    role="link",
                    href="https://blocked.example",
                )
            ],
        ),
    )
    assert (
        await validator.validate(
            state,
            Action(
                action="click",
                target=Target(ref="e1"),
                rationale="Click.",
            ),
        )
    ).tier == 3
    state.last_observation = Observation(url="https://blocked.example")
    assert (await validator.validate(state, Action(action="extract", rationale="Read."))).tier == 3


def test_decision_alias_preserves_existing_verdict_wire_shape() -> None:
    verdict = Verdict.model_validate({"decision": "approve", "reason": "Approve", "tier": 2})
    assert verdict.verdict == "approval" and verdict.decision == "approve"


def test_policy_log_formatter_exposes_only_safe_metadata() -> None:
    import logging

    from app.logging import JsonFormatter

    record = logging.LogRecord("clevis", logging.INFO, "", 1, "policy.verdict", (), None)
    record.runId = "run-test"
    record.tier = 2
    record.action = "type"
    record.value = "CANARY-NEVER-LOG-THIS"
    serialized = JsonFormatter().format(record)
    data = json.loads(serialized)
    assert data["tier"] == 2 and data["action"] == "type" and data["runId"] == "run-test"
    assert "CANARY" not in serialized and "value" not in data
