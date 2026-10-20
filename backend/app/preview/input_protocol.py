"""Untrusted input validation. Models/rejections must never be logged or serialized to events."""

import json
from time import monotonic
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.config import Settings


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    def __repr_args__(self) -> list[tuple[str, object]]:
        return [("type", getattr(self, "type", "input"))]

    def __str__(self) -> str:
        return "<private input>"


class Auth(InputModel):
    type: Literal["auth"]
    token: str = Field(max_length=256, repr=False)


class Mouse(InputModel):
    type: Literal["mouse"]
    action: Literal["move", "down", "up"]
    x: float = Field(allow_inf_nan=False, repr=False)
    y: float = Field(allow_inf_nan=False, repr=False)
    button: Literal["left", "middle", "right"] = "left"
    clickCount: int = Field(default=1, ge=1, le=3)
    modifiers: int = Field(default=0, ge=0, le=15)


class Wheel(InputModel):
    type: Literal["wheel"]
    x: float = Field(allow_inf_nan=False, repr=False)
    y: float = Field(allow_inf_nan=False, repr=False)
    dx: float = Field(ge=-10000, le=10000, allow_inf_nan=False, repr=False)
    dy: float = Field(ge=-10000, le=10000, allow_inf_nan=False, repr=False)


class Key(InputModel):
    type: Literal["key"]
    action: Literal["down", "up"]
    key: str = Field(min_length=1, max_length=32, repr=False)
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9]+$", repr=False)
    modifiers: int = Field(default=0, ge=0, le=15)


class Text(InputModel):
    type: Literal["text"]
    value: str = Field(min_length=1, repr=False)


class Ping(InputModel):
    type: Literal["ping"]


Input = Annotated[Auth | Mouse | Wheel | Key | Text | Ping, Field(discriminator="type")]
_ADAPTER: TypeAdapter[Input] = TypeAdapter(cast(Any, Input))


def parse_input(raw: str | bytes | None, settings: Settings) -> Input | None:
    if raw is None or len(raw) > settings.input_max_message_bytes:
        return None
    try:
        if isinstance(raw, bytes) or len(raw.encode("utf-8")) > settings.input_max_message_bytes:
            return None
        message = _ADAPTER.validate_python(json.loads(raw))
        if isinstance(message, Text) and len(message.value) > settings.input_max_text_length:
            return None
        return message
    except (ValueError, ValidationError, UnicodeError, RecursionError):
        return None  # Never stringify ValidationError: it contains the rejected input.


class RateLimit:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.started = monotonic()
        self.used = 0

    def allow(self, now: float | None = None) -> bool:
        now = monotonic() if now is None else now
        if now - self.started >= 1:
            self.started, self.used = now, 0
        self.used += 1
        return self.used <= self.maximum
