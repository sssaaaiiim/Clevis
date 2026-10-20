from dataclasses import dataclass, field
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel, Field

from app.core.events import Model

T = TypeVar("T", bound=BaseModel)


class Message(Model):
    role: Literal["system", "user", "assistant"]
    content: str


class Usage(Model):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    cost_estimated: bool = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def plus(self, other: "Usage") -> "Usage":
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
            cost_estimated=self.cost_estimated or other.cost_estimated,
        )


@dataclass(frozen=True)
class LLMResponse(Generic[T]):
    parsed: T
    tokens_used: int = 0
    usage: Usage = field(default_factory=Usage)


class LLMError(RuntimeError):
    def __init__(self, message: str, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage or Usage()


class LLMOutputError(LLMError):
    pass


class LLMClient(Protocol):
    async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]: ...

    async def close(self) -> None: ...
