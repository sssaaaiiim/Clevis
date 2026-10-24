import json
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol, runtime_checkable

from pydantic import Field

from app.core.events import Action, Mode, Model


class ElementState(Model):
    disabled: bool | None = None
    checked: bool | None = None
    expanded: bool | None = None
    selected: bool | None = None
    required: bool | None = None


class Element(Model):
    ref: str
    role: str
    name: str = Field(max_length=80)
    tag: str
    type: str | None = None
    value: str | None = Field(default=None, max_length=100)
    href: str | None = None
    state: ElementState = Field(default_factory=ElementState)
    hidden: bool = False
    aria_hidden: bool = False
    form_action: str | None = None
    form_name: str | None = None
    download: bool = False


class Observation(Model):
    url: str = "about:blank"
    title: str = ""
    generation: int = 0
    elements: list[Element] = Field(default_factory=list)
    text_excerpt: str = ""
    truncated: bool = False
    # Compatibility for the fake driver and the existing short timeline event.
    summary: str = ""

    def to_prompt_text(self) -> str:
        header = f"Page {self.title[:160]!r} generation={self.generation}"
        lines = [header]
        for element in self.elements:
            line = f"[{element.ref}] {element.role} {json.dumps(element.name, ensure_ascii=False)}"
            if element.value is not None:
                line += f" value={json.dumps(element.value, ensure_ascii=False)}"
            flags = [name for name, value in element.state.model_dump().items() if value is True]
            if flags:
                line += " " + ",".join(flags)
            lines.append(line)
        if self.text_excerpt:
            lines.append("Text: " + self.text_excerpt)
        elif self.summary:
            lines.append(self.summary[:1000])
        if self.truncated:
            lines.append("[truncated]")
        return "\n".join(lines)


ErrorCode = Literal[
    "STALE_REF",
    "NOT_FOUND",
    "NOT_VISIBLE",
    "TIMEOUT",
    "BLOCKED_URL",
    "INVALID_ACTION",
    "BROWSER_ERROR",
    "PAUSED",
]


class BrowserFailure(RuntimeError):
    """A browser error with a safe, caller-visible message and a typed error code."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ErrorCode = code


class ActionResult(Model):
    ok: bool
    summary: str
    error_code: ErrorCode | None = None
    navigated: bool = False


class InputEvent(Model):
    kind: str
    x: float | None = None
    y: float | None = None
    key: str | None = None
    text: str | None = None


class BrowserDriver(Protocol):
    async def start(self, mode: Mode) -> None: ...
    async def navigate(self, url: str) -> None: ...
    async def observe(self) -> Observation: ...
    async def act(self, action: Action) -> ActionResult: ...
    async def get_text(self) -> str: ...
    async def close(self) -> None: ...


class PreviewChannel(Protocol):
    async def start_stream(self, on_frame: Callable[[bytes], Awaitable[None]]) -> None: ...
    async def stop_stream(self) -> None: ...
    async def input(self, event: InputEvent) -> None: ...


@runtime_checkable
class PausableDriver(Protocol):
    async def pause_actions(self) -> None: ...
    async def resume_actions(self) -> None: ...


@runtime_checkable
class GuardedBrowserDriver(Protocol):
    async def install_navigation_guard(
        self,
        guard: Callable[[str, bool], Awaitable[None]],
    ) -> None: ...
