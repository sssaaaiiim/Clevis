import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import SecretStr

from app.core.events import Action
from app.interfaces.llm import LLMError, LLMOutputError, Message
from app.llm.openrouter_client import OpenRouterPool, retry_delay
from tests.settings import IsolatedSettings

KEY = "test-only-api-key-never-echo"
ACTION = {"action": "done", "value": "Result", "rationale": "Finished."}


def response(content: str, cost: float | None = 0.01) -> httpx.Response:
    usage: dict[str, Any] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    if cost is not None:
        usage["cost"] = cost
    return httpx.Response(
        200,
        json={
            "id": "test",
            "object": "chat.completion",
            "created": 1,
            "model": "primary",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": usage,
        },
    )


def pool_for(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    structured: bool = True,
    **overrides: Any,
) -> OpenRouterPool:
    def dispatch(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": model,
                            "object": "model",
                            "created": 1,
                            "owned_by": "test",
                            "supported_parameters": ["structured_outputs"] if structured else [],
                            "pricing": {"prompt": "0.001", "completion": "0.002"},
                        }
                        for model in ["primary", "fallback"]
                    ]
                },
            )
        return handler(request)

    settings = IsolatedSettings(
        llm_provider="openrouter",
        openrouter_api_key=SecretStr(KEY),
        llm_model_primary="primary",
        **overrides,
    )
    sdk = AsyncOpenAI(
        api_key=KEY,
        base_url="https://mock.invalid/api/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(dispatch)),
    )
    return OpenRouterPool(settings, sdk)


@pytest.mark.parametrize("structured", [True, False])
async def test_formats_and_usage(structured: bool) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return response("```json\n" + json.dumps(ACTION) + "\n```", cost=None)

    pool = pool_for(handler, structured=structured)
    try:
        result = await pool.session().propose([Message(role="user", content="Goal")], Action)
        body = requests[0]
        assert ("response_format" in body) is structured
        assert body["provider"]["require_parameters"] is True
        assert result.parsed.value == "Result"
        assert result.usage.total_tokens == 15
        assert result.usage.cost_usd == 0.02
        assert result.usage.cost_estimated
    finally:
        await pool.close()


async def test_invalid_then_valid_counts_every_attempt() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return response("private page garbage" if len(calls) == 1 else json.dumps(ACTION))

    pool = pool_for(handler)
    try:
        result = await pool.session().propose([], Action)
        assert result.tokens_used == 30
        assert result.usage.cost_usd == 0.02
        assert "private page garbage" not in json.dumps(calls[-1])
    finally:
        await pool.close()


@pytest.mark.parametrize("status", [429, 500])
async def test_fallback_and_retry_after(status: int, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("app.llm.openrouter_client.asyncio.sleep", sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        calls.append(model)
        return (
            httpx.Response(status, headers={"Retry-After": "2"}, json={"error": {}})
            if model == "primary"
            else response(json.dumps(ACTION))
        )

    pool = pool_for(handler, llm_model_fallback="fallback")
    try:
        await pool.session().propose([], Action)
        assert calls == ["primary", "fallback"]
        assert sleeps[0] >= 2
    finally:
        await pool.close()


async def test_invalid_output_falls_back_once() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        calls.append(model)
        return response("invalid" if model == "primary" else json.dumps(ACTION))

    pool = pool_for(handler, llm_model_fallback="fallback", llm_max_retries=2)
    try:
        result = await pool.session().propose([], Action)
        assert calls == ["primary"] * 3 + ["fallback"]
        assert result.tokens_used == 60
    finally:
        await pool.close()


@pytest.mark.parametrize("status", [401, 403, 402, 400])
async def test_no_retry_or_secret_in_errors(status: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, json={"error": {"message": KEY}})

    pool = pool_for(handler, llm_model_fallback="fallback")
    try:
        with pytest.raises(LLMError) as error:
            await pool.session().propose([], Action)
        assert KEY not in str(error.value)
        assert calls == 1
    finally:
        await pool.close()


async def test_invalid_final_error_keeps_usage() -> None:
    pool = pool_for(lambda _: response("invalid " + KEY), llm_max_retries=1)
    try:
        with pytest.raises(LLMOutputError) as error:
            await pool.session().propose([], Action)
        assert error.value.usage.total_tokens == 30
        assert KEY not in str(error.value)
    finally:
        await pool.close()


async def test_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(KEY, request=request)

    pool = pool_for(handler, llm_max_retries=0)
    try:
        with pytest.raises(LLMError, match="timed out"):
            await pool.session().propose([], Action)
    finally:
        await pool.close()


async def test_cancellation_aborts_inflight_request() -> None:
    started, aborted = asyncio.Event(), asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            aborted.set()
        return response(json.dumps(ACTION))

    pool = pool_for(lambda _: response(json.dumps(ACTION)))
    pool.loaded = True
    old = pool.sdk
    pool.sdk = AsyncOpenAI(
        api_key=KEY,
        base_url="https://mock.invalid",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        task = asyncio.create_task(pool.session().propose([], Action))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert aborted.is_set()
    finally:
        await old.close()
        await pool.close()


def test_retry_after_http_date_and_malformed() -> None:
    assert retry_delay("Thu, 01 Jan 2099 00:00:00 GMT", 0) > 100
    assert 0.5 <= retry_delay("invalid", 1) < 0.7


@pytest.mark.parametrize("limit", ["tokens", "cost"])
async def test_budget_blocks_additional_invalid_output_retries(limit: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response("invalid")

    kwargs: dict[str, Any] = {"max_tokens": 10} if limit == "tokens" else {"max_cost_usd": 0.001}
    pool = pool_for(handler, **kwargs)
    try:
        with pytest.raises(LLMError, match="MAX_TOKENS" if limit == "tokens" else "MAX_COST_USD"):
            await pool.session().propose([], Action)
        assert calls == 1
    finally:
        await pool.close()


async def test_budget_accumulates_across_planner_and_actor_calls() -> None:
    pool = pool_for(lambda _: response(json.dumps(ACTION)), max_tokens=20)
    try:
        session = pool.session()
        await session.propose([], Action)
        with pytest.raises(LLMError, match="MAX_TOKENS"):
            await session.propose([], Action)
    finally:
        await pool.close()


async def test_catalog_auth_failure_never_attempts_completion() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(401, json={"error": {"message": KEY}})

    pool = pool_for(lambda _: response(json.dumps(ACTION)))
    old = pool.sdk
    pool.sdk = AsyncOpenAI(
        api_key=KEY,
        base_url="https://mock.invalid",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(LLMError, match="invalid API key") as error:
            await pool.session().propose([], Action)
        assert calls == ["/models"]
        assert KEY not in str(error.value)
    finally:
        await old.close()
        await pool.close()
