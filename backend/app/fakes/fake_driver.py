import asyncio
from typing import Literal

from app.core.events import Action, Mode
from app.interfaces.browser import ActionResult, Observation


class FakeBrowserDriver:
    def __init__(
        self,
        *,
        delay: float = 0.05,
        fail_on: Literal["start", "navigate", "observe", "act", "get_text", "close"] | None = None,
    ) -> None:
        self.delay = delay
        self.fail_on = fail_on
        self.url = "about:blank"
        self.closed = False
        self.started = False
        self.actions: list[Action] = []

    async def _operation(self, name: str) -> None:
        await asyncio.sleep(self.delay)
        if name == self.fail_on:
            raise RuntimeError("Injected fake browser failure.")

    async def start(self, mode: Mode) -> None:
        await self._operation("start")
        self.started = True

    async def navigate(self, url: str) -> None:
        await self._operation("navigate")
        self.url = url

    async def observe(self) -> Observation:
        await self._operation("observe")
        return Observation(
            summary="Sample page with a search field and matching result.", url=self.url
        )

    async def act(self, action: Action) -> ActionResult:
        await self._operation("act")
        self.actions.append(action.model_copy(deep=True))
        if action.action == "navigate" and action.value:
            self.url = action.value
        summary = (
            await self.get_text()
            if action.action == "extract"
            else f"Fake {action.action} completed."
        )
        return ActionResult(ok=True, summary=summary)

    async def get_text(self) -> str:
        await self._operation("get_text")
        return "Sample result: Travel Mug, $12.00."

    async def close(self) -> None:
        self.closed = True
        await self._operation("close")
