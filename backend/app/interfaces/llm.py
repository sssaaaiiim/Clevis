from dataclasses import dataclass
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel

from app.core.events import Model

T = TypeVar("T", bound=BaseModel)


class Message(Model):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMResponse(Generic[T]):
    parsed: T
    tokens_used: int


class LLMClient(Protocol):
    async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]: ...
