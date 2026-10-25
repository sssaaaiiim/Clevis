import json
import re

import pytest

from app.agent.outcomes import check_outcome, verifier_messages
from app.agent.state import StepRecord, SubGoal
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import Element, Observation
from app.interfaces.llm import LLMOutputError, LLMResponse, Message, T, Usage


class VerifierFake(FakeLLMClient):
    def __init__(self, invalid: int = 0) -> None:
        super().__init__(delay=0)
        self.invalid = invalid
        self.calls = 0

    async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
        self.calls += 1
        usage = Usage(prompt_tokens=5, completion_tokens=2)
        if self.calls <= self.invalid:
            raise LLMOutputError("Invalid JSON", usage)
        return LLMResponse(
            parsed=schema.model_validate({"achieved": True, "reason": "Confirmation is present."}),
            usage=usage,
            tokens_used=7,
        )


def test_verifier_caps_and_untrusted_boundary() -> None:
    goal = SubGoal(id=1, description="Submit contact", success_condition="Confirmation visible")
    observation = Observation(
        url="https://example.com/private?secret=hidden",
        title="UNTRUSTED-TITLE",
        text_excerpt="X" * 700,
        elements=[
            Element(
                ref=f"e{i}", name=f"UNTRUSTED-{i}", tag="button", role="button", value="DO-NOT-SEND"
            )
            for i in range(60)
        ],
    )
    history = [
        StepRecord(step_id=i, action="click", ok=True, result_summary=f"SUMMARY-{i}", ts="test")
        for i in range(6)
    ]
    messages = verifier_messages(goal, observation, history)
    assert "UNTRUSTED-TITLE" not in messages[0].content
    user = messages[1].content
    start = re.search(r"<<<PAGE_CONTENT id=([0-9a-f]{8}) UNTRUSTED>>>\n", user)
    assert start
    data = json.loads(user[start.end() : user.index("\n<<<END_PAGE_CONTENT")])
    assert len(data["elements"]) == 50 and len(data["last_steps"]) == 3
    assert data["elements"][-1]["ref"] == "e49"
    assert data["domain"] == "example.com"
    assert len(data["text_excerpt"]) == 500
    assert "DO-NOT-SEND" not in user and "?secret" not in user
    assert "Submit contact" in user and "Confirmation visible" in user
    assert user != verifier_messages(goal, observation, history)[1].content


@pytest.mark.parametrize(
    "invalid,truncated,achieved,confidence,tokens",
    [
        (0, False, True, "high", 7),
        (1, False, True, "low", 14),
        (2, False, False, "low", 14),
        (0, True, True, "low", 7),
    ],
)
async def test_outcome_validation_retry_and_usage(
    invalid: int,
    truncated: bool,
    achieved: bool,
    confidence: str,
    tokens: int,
) -> None:
    llm = VerifierFake(invalid)
    result = await check_outcome(
        SubGoal(id=1, description="Read", success_condition="Read"),
        Observation(truncated=truncated),
        [],
        llm,
    )
    assert result.parsed.achieved is achieved and result.parsed.confidence == confidence
    assert result.usage.total_tokens == result.tokens_used == tokens
    assert llm.calls == min(2, invalid + 1)
    if invalid == 2:
        assert result.parsed.reason == "Verifier failed to respond"


async def test_projection_truncation_lowers_verifier_confidence() -> None:
    observation = Observation(
        elements=[
            Element(ref=f"e{i}", name="Button", role="button", tag="button") for i in range(51)
        ]
    )
    verdict = await check_outcome(
        SubGoal(id=1, description="Read", success_condition="Read"), observation, [], VerifierFake()
    )
    assert verdict.parsed.confidence == "low"
