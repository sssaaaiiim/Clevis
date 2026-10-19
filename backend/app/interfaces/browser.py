from collections.abc import Awaitable, Callable
from typing import Protocol

from app.core.events import Action, Mode, Model


class Observation(Model):
    summary: str
    url: str = "about:blank"


class ActionResult(Model):
    ok: bool
    summary: str


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
