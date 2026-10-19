"""OpenRouter chat completion client with reasoning continuity."""

import json
import logging
from typing import Any

import httpx

from app.config import OPENROUTER_MODEL, OPENROUTER_URL

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """Call OpenRouter and carry returned reasoning details into later turns."""

    def __init__(self, api_key: str, timeout: httpx.Timeout) -> None:
        self._http = httpx.AsyncClient(
            base_url=OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        self._messages: list[dict[str, object]] = []

    async def __aenter__(self) -> "OpenRouterClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self._http.aclose()

    async def complete_json(
        self,
        prompt: str,
        fallback: Any,
        usage: dict[str, int] | None = None,
    ) -> Any:
        """Request a JSON-formatted response and preserve reasoning for the next turn."""
        self._messages.append({"role": "user", "content": prompt})
        try:
            response = await self._http.post(
                "/chat/completions",
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": self._messages,
                    "reasoning": {"enabled": True},
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"OpenRouter API returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError("Could not connect to the OpenRouter API.") from exc

        try:
            data = response.json()
            message = data["choices"][0]["message"]
            if not isinstance(message, dict):
                raise ValueError("Assistant message is not an object")
            content = message.get("content")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("OpenRouter returned an invalid chat-completions response.") from exc

        assistant_turn: dict[str, object] = {
            "role": "assistant",
            "content": content,
        }
        if "reasoning_details" in message:
            assistant_turn["reasoning_details"] = message["reasoning_details"]
        self._messages.append(assistant_turn)

        if usage is not None:
            try:
                usage_data = data.get("usage") if isinstance(data, dict) else None
                token_count = usage_data.get("total_tokens") if isinstance(usage_data, dict) else None
                if isinstance(token_count, int) and not isinstance(token_count, bool) and token_count >= 0:
                    usage["tokens"] = usage.get("tokens", 0) + token_count
            except Exception:
                logger.warning("Unable to record OpenRouter token usage.", exc_info=True)

        if not isinstance(content, str) or not content.strip():
            return fallback

        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
            text = "\n".join(lines).strip()
        if not text:
            return fallback

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return fallback
