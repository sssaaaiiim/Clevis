import json

import httpx
import pytest

from app.agent.outcomes import OutcomeAnswer
from app.interfaces.llm import Message
from tests.test_openrouter import pool_for, response


@pytest.mark.parametrize(
    "configured,expected", [("", "primary"), ("cheap-verifier", "cheap-verifier")]
)
async def test_outcome_session_model_and_eighty_token_cap(configured: str, expected: str) -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return response('{"achieved":true,"reason":"Verified."}')

    pool = pool_for(handler, llm_outcome_model=configured)
    session = pool.outcome_session()
    try:
        verdict = await session.propose(
            [Message(role="user", content="Verify demo")], OutcomeAnswer
        )
        assert verdict.parsed.achieved
        assert bodies[0]["model"] == expected and bodies[0]["max_tokens"] == 80
        assert len(bodies) == 1
        await session.close()
        assert not pool.sdk.is_closed()
    finally:
        await pool.close()
