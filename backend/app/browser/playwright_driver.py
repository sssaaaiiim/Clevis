import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from playwright.async_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeout,
)

from app.browser.safety import BrowserFailure, display_available, validate_url
from app.config import Settings
from app.core.events import Mode
from app.interfaces.browser import ErrorCode

T = TypeVar("T")


def error_code(exc: Exception) -> ErrorCode:
    if isinstance(exc, BrowserFailure):
        return exc.code
    if isinstance(exc, PlaywrightTimeout):
        return "TIMEOUT"
    return "BROWSER_ERROR"


class PlaywrightDriver:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._operation_lock = asyncio.Lock()
        self.generation = 0
        self._next_ref = 1
        self._refs: dict[str, tuple[int, Page, Locator]] = {}
        self._typed_values: set[str] = set()

    def get_active_page(self) -> Page:
        if self._page is None or self._page.is_closed():
            raise BrowserFailure("BROWSER_ERROR", "No active browser page.")
        return self._page

    def get_context(self) -> BrowserContext:
        if self._context is None:
            raise BrowserFailure("BROWSER_ERROR", "Browser context is not running.")
        return self._context

    async def start(self, mode: Mode) -> None:
        if self._playwright is not None or self._close_task is not None:
            raise BrowserFailure("BROWSER_ERROR", "Use a fresh driver for each run.")
        if mode == "headed" and not display_available():
            raise BrowserFailure(
                "BROWSER_ERROR", "Headed Chromium requires a display (DISPLAY or WAYLAND_DISPLAY)."
            )
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=mode == "headless",
                slow_mo=self.settings.slow_mo_ms,
                timeout=min(self.settings.nav_timeout_ms, 15_000),
            )
            self._context = await self._browser.new_context(
                viewport={
                    "width": self.settings.viewport_width,
                    "height": self.settings.viewport_height,
                },
                device_scale_factor=self.settings.device_scale_factor,
                accept_downloads=False,
                permissions=[],
            )
            # An empty override grants none and denies the remaining permission prompts.
            await self._context.grant_permissions([])
            self._context.set_default_timeout(self.settings.action_timeout_ms)
            self._context.set_default_navigation_timeout(self.settings.nav_timeout_ms)
            self._page = await self._context.new_page()
        except asyncio.CancelledError:
            await self.close()
            raise
        except Exception:
            await self.close()
            message = (
                "Cannot open headed Chromium; check the display and browser installation."
                if mode == "headed"
                else "Cannot start Chromium; run playwright install chromium; check host dependencies."
            )
            raise BrowserFailure("BROWSER_ERROR", message) from None

    async def _settle(self, page: Page) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=2000)
        except PlaywrightTimeout:
            pass

    async def navigate(self, url: str) -> None:
        validate_url(url)
        try:
            page = self.get_active_page()
            await page.goto(
                url, wait_until="domcontentloaded", timeout=self.settings.nav_timeout_ms
            )
            await self._settle(page)
        except asyncio.CancelledError:
            await self.close()
            raise
        except (PlaywrightError, BrowserFailure) as exc:
            raise BrowserFailure(error_code(exc), "Browser navigation failed.") from None

    async def close(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close_resources())
        try:
            await asyncio.shield(self._close_task)
        except asyncio.CancelledError:
            # Do not detach Chromium cleanup when a run or request is cancelled.
            await asyncio.shield(self._close_task)
            raise

    async def _close_resources(self) -> None:
        context, browser, playwright = self._context, self._browser, self._playwright
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

        async def attempt(operation: Callable[[], Awaitable[object]]) -> None:
            try:
                async with asyncio.timeout(2):
                    await operation()
            except (PlaywrightError, TimeoutError):
                pass

        if context is not None:
            for page in context.pages:
                await attempt(page.close)
            await attempt(context.close)
        if browser is not None:
            await attempt(browser.close)
        if playwright is not None:
            await attempt(playwright.stop)
