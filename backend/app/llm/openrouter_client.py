"""OpenRouter adapter. Network lifetime is owned by the application, sessions by runs."""

import asyncio
import json
import logging
import math
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, cast

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.completion_create_params import ResponseFormat
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.interfaces.llm import LLMError, LLMOutputError, LLMResponse, Message, T, Usage


class ModelInfo:
    def __init__(self, data: dict[str, Any]) -> None:
        self.structured = "structured_outputs" in data.get("supported_parameters", [])
        pricing = data.get("pricing") or {}
        # A deliberately conservative estimate when catalog pricing is unavailable ($100/M).
        self.prompt_rate = self.rate(pricing.get("prompt"))
        self.completion_rate = self.rate(pricing.get("completion"))

    @staticmethod
    def rate(value: object) -> float:
        try:
            rate = float(str(value))
            return rate if math.isfinite(rate) and rate >= 0 else 0.0001
        except (TypeError, ValueError):
            return 0.0001


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            node.pop("default", None)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema


def parse_object(content: str) -> dict[str, Any]:
    """Accept fenced JSON and explanatory prefixes without executing model output."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(content[:1_000_000]):
        if char == "{":
            try:
                obj, _ = decoder.raw_decode(content[index:])
                if isinstance(obj, dict):
                    return cast(dict[str, Any], obj)
            except ValueError:
                continue
    raise LLMOutputError("LLM returned invalid JSON.")


def retry_delay(header: str | None, attempt: int) -> float:
    delay = min(8, 0.25 * 2**attempt) + random.uniform(0, 0.1)
    if header:
        try:
            seconds = float(header)
        except ValueError:
            try:
                seconds = (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                seconds = 0
        if math.isfinite(seconds):
            delay = max(delay, seconds)
    return float(delay)


class OpenRouterPool:
    """One AsyncOpenAI per application lifespan; metadata is cached across runs."""

    def __init__(self, settings: Settings, sdk: AsyncOpenAI | None = None) -> None:
        settings.validate_llm()
        self.settings = settings
        # SDK request debugging can include headers/bodies; this adapter never enables it.
        for name in ("openai", "httpx", "httpcore"):
            logging.getLogger(name).setLevel(logging.WARNING)
        self.sdk = sdk or AsyncOpenAI(
            api_key=settings.openrouter_api_key.get_secret_value(),
            base_url=settings.openrouter_base_url,
            timeout=settings.llm_request_timeout_s,
            max_retries=0,
        )
        self.models: dict[str, ModelInfo] = {}
        self.loaded = False
        self.lock = asyncio.Lock()

    async def info(self, model: str) -> ModelInfo:
        async with self.lock:
            if not self.loaded:
                try:
                    async with asyncio.timeout(self.settings.llm_request_timeout_s):
                        page = await self.sdk.models.list()
                    self.models = {item.id: ModelInfo(item.model_dump()) for item in page.data}
                except APIStatusError as exc:
                    if exc.status_code in {401, 403}:
                        raise LLMError("OpenRouter: invalid API key or no access.") from None
                except (APIConnectionError, TimeoutError, ValueError):
                    # Unknown capability must never result in sending response_format.
                    pass
                self.loaded = True
        return self.models.get(model, ModelInfo({}))

    def session(self) -> "OpenRouterLLMClient":
        return OpenRouterLLMClient(self)

    async def close(self) -> None:
        await self.sdk.close()


class OpenRouterLLMClient:
    def __init__(self, pool: OpenRouterPool) -> None:
        self.pool = pool
        self.closed = False
        self.total_usage = Usage()

    async def close(self) -> None:
        # A run releases its session; only the lifespan closes the shared SDK connection pool.
        self.closed = True

    async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
        if self.closed:
            raise LLMError("LLM session is closed.")
        settings = self.pool.settings
        models = [settings.llm_model_primary]
        if settings.llm_model_fallback and settings.llm_model_fallback != models[0]:
            models.append(settings.llm_model_fallback)
        total = Usage()
        last_error = "LLM request failed."
        for model_index, model in enumerate(models):
            info = await self.pool.info(model)
            conversation = [message.model_copy() for message in messages]
            # Only schema instructions are added, never raw rejected responses or page content.
            if not info.structured:
                conversation.append(
                    Message(
                        role="user",
                        content="Respond with JSON only matching this schema: "
                        + json.dumps(schema.model_json_schema()),
                    )
                )
            attempts = settings.llm_max_retries + 1 if model_index == 0 else 1
            for attempt in range(attempts):
                retry_after: str | None = None
                transient = False
                try:
                    format_: ResponseFormat | Any = (
                        {
                            "type": "json_schema",
                            "json_schema": {
                                "name": schema.__name__,
                                "strict": True,
                                "schema": strict_schema(schema),
                            },
                        }
                        if info.structured
                        else None
                    )
                    kwargs: dict[str, Any] = {}
                    if format_ is not None:
                        kwargs["response_format"] = format_
                    async with asyncio.timeout(settings.llm_request_timeout_s):
                        completion = await self.pool.sdk.chat.completions.create(
                            model=model,
                            messages=[
                                cast(ChatCompletionMessageParam, m.model_dump())
                                for m in conversation
                            ],
                            temperature=settings.llm_temperature,
                            max_tokens=settings.llm_max_output_tokens,
                            timeout=settings.llm_request_timeout_s,
                            extra_body={"provider": {"require_parameters": True}},
                            **kwargs,
                        )
                    usage = completion.usage
                    raw_cost = (usage.model_extra or {}).get("cost") if usage else None
                    prompt = (
                        usage.prompt_tokens
                        if usage
                        else max(1, sum(len(m.content) for m in conversation) // 4)
                    )
                    content = completion.choices[0].message.content if completion.choices else None
                    output = usage.completion_tokens if usage else len(content or "") // 4
                    reported = isinstance(raw_cost, (int, float)) and math.isfinite(raw_cost)
                    reported_cost = float(raw_cost) if isinstance(raw_cost, (int, float)) else -1.0
                    reported = reported and reported_cost >= 0
                    attempt_usage = Usage(
                        prompt_tokens=prompt,
                        completion_tokens=output,
                        cost_usd=reported_cost
                        if reported
                        else (prompt * info.prompt_rate + output * info.completion_rate),
                        cost_estimated=not reported,
                    )
                    total = total.plus(attempt_usage)
                    self.total_usage = self.total_usage.plus(attempt_usage)
                    if self.total_usage.total_tokens > settings.max_tokens:
                        raise LLMError("MAX_TOKENS exceeded during LLM requests.", total)
                    if settings.max_cost_usd and self.total_usage.cost_usd > settings.max_cost_usd:
                        raise LLMError("MAX_COST_USD exceeded during LLM requests.", total)
                    payload = parse_object(content or "")
                    # The public Action contract remains capped at 300 characters.
                    if isinstance(payload.get("rationale"), str):
                        payload["rationale"] = payload["rationale"][:300]
                    key = settings.openrouter_api_key.get_secret_value()
                    if key:
                        payload = json.loads(json.dumps(payload).replace(key, "[redacted]"))
                    parsed = schema.model_validate(payload)
                    return LLMResponse(parsed=parsed, tokens_used=total.total_tokens, usage=total)
                except (ValidationError, LLMOutputError) as exc:
                    last_error = "LLM output did not match the required JSON schema."
                    # Validation paths/types are safe; validation inputs and raw responses are not.
                    fields = (
                        ", ".join(error["type"] for error in exc.errors(include_input=False)[:4])
                        if isinstance(exc, ValidationError)
                        else "invalid JSON object"
                    )
                    conversation.append(
                        Message(
                            role="user", content="Correct the JSON schema errors: " + fields + "."
                        )
                    )
                except APIStatusError as exc:
                    if exc.status_code in {401, 403}:
                        raise LLMError("OpenRouter: invalid API key or no access.", total) from None
                    if exc.status_code == 402:
                        raise LLMError(
                            "OpenRouter account has insufficient credits.", total
                        ) from None
                    transient = exc.status_code == 429 or exc.status_code >= 500
                    if not transient:
                        raise LLMError(
                            "OpenRouter rejected the request parameters.", total
                        ) from None
                    retry_after = exc.response.headers.get("Retry-After")
                    last_error = "OpenRouter rate limit or provider unavailable."
                except (APIConnectionError, APITimeoutError, TimeoutError):
                    transient = True
                    last_error = "OpenRouter request timed out or connection failed."
                if transient:
                    has_next = model_index + 1 < len(models) or attempt + 1 < attempts
                    if has_next:
                        await asyncio.sleep(retry_delay(retry_after, attempt))
                    if len(models) > 1:
                        break  # One controlled fallback, with its own capability check.
            # Exhausted invalid-output retries or transport failures: try the configured fallback.
        if "JSON" in last_error:
            raise LLMOutputError(last_error, total) from None
        raise LLMError(last_error, total) from None
