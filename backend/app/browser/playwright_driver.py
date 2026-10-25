import asyncio
import math
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urljoin

from playwright.async_api import (
    Browser,
    BrowserContext,
    CDPSession,
    Dialog,
    Frame,
    Locator,
    Page,
    Playwright,
    Route,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeout,
)

from app.browser.input_privacy import InputPrivacy
from app.browser.network import NavigationMonitor
from app.browser.safety import BrowserFailure, display_available, validate_url
from app.config import Settings
from app.core.events import Action, Mode
from app.interfaces.browser import ActionResult, ErrorCode, Observation


class ViewportInfo(TypedDict):
    width: int
    height: int
    deviceScaleFactor: float


OBSERVE_SCRIPT = Path(__file__).with_name("observe.js").read_text()


def error_code(exc: Exception) -> ErrorCode:
    if isinstance(exc, BrowserFailure):
        return exc.code
    if isinstance(exc, PlaywrightTimeout):
        return "TIMEOUT"
    return "BROWSER_ERROR"


class PlaywrightDriver:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._manager = async_playwright()
        self._manager_started = False
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
        self._paused = False
        self.input_privacy = InputPrivacy()
        self._notices: list[str] = []
        self._navigation_count = 0
        self._closing = False
        self._callbacks: list[Callable[[Page], Awaitable[None] | None]] = []
        self._callback_tasks: set[asyncio.Future[None]] = set()
        self._network_sessions: dict[Page, CDPSession] = {}
        self._network_attach_lock = asyncio.Lock()
        self._blocked_count = 0
        self._navigation_tasks: set[asyncio.Future[None]] = set()
        self._monitor: NavigationMonitor | None = None
        self._on_block: Callable[[str, str], Awaitable[None]] | None = None
        self._navigation_guard: Callable[[str, bool], Awaitable[None]] | None = None

    def configure_navigation_monitor(
        self, monitor: NavigationMonitor, on_block: Callable[[str, str], Awaitable[None]]
    ) -> None:
        self._monitor, self._on_block = monitor, on_block

    async def _check_navigation(self, frame: Frame) -> None:
        if self._monitor is None or self._closing:
            return
        if not frame.url.startswith(("http://", "https://")):
            return
        url = frame.url
        warning = await self._monitor.warning(url, fresh=True)
        if warning:
            await self._block_navigation(frame, url, warning)

    async def _block_navigation(self, frame: Frame, url: str, warning: str) -> None:
        from app.agent.policy.domains import hostname

        self._blocked_count += 1
        # Abort the blocked loader before starting a replacement navigation. Without
        # this, a pending form loader can interrupt both about:blank attempts.
        page = getattr(frame, "page", None)
        session = self._network_sessions.get(page) if page is not None else None
        if session is not None:
            try:
                await session.send("Page.stopLoading")
            except PlaywrightError:
                pass

        for _ in range(2):
            try:
                await frame.wait_for_load_state("domcontentloaded", timeout=500)
            except PlaywrightError:
                pass
            try:
                await frame.goto("about:blank", timeout=1000)
                if frame.url == "about:blank":
                    break
            except PlaywrightError:
                await asyncio.sleep(0)
        if self._on_block is not None:
            await self._on_block(hostname(url), warning)

    async def _attach_network_interceptor(self, page: Page) -> None:
        if self._monitor is None or not self._monitor.enabled:
            return
        # Do not enable Fetch midway through a fulfilled initial popup response;
        # Chromium can otherwise leave later out-of-process iframe loads paused.
        await page.wait_for_load_state("domcontentloaded", timeout=self.settings.nav_timeout_ms)
        async with self._network_attach_lock:
            if page in self._network_sessions or self._closing or self._monitor is None:
                return
            session = await self.get_context().new_cdp_session(page)
            self._network_sessions[page] = session
            session.on(
                "Fetch.requestPaused",
                lambda event: self._track_navigation_task(
                    self._check_intercepted_request(page, session, event)
                ),
            )
            await session.send(
                "Fetch.enable",
                {"patterns": [{"resourceType": "Document", "requestStage": "Response"}]},
            )

    async def _check_intercepted_request(
        self, page: Page, session: CDPSession, event: dict[str, Any]
    ) -> None:
        request_id = event["requestId"]
        url = event["request"]["url"]
        if event.get("responseStatusCode") in {301, 302, 303, 307, 308}:
            location = next(
                (
                    h["value"]
                    for h in event.get("responseHeaders", [])
                    if h["name"].lower() == "location"
                ),
                "",
            )
            if location:
                url = urljoin(url, location)
        try:
            warning = await self._monitor.warning(url) if self._monitor else None
            if warning:
                await session.send(
                    "Fetch.failRequest", {"requestId": request_id, "errorReason": "BlockedByClient"}
                )
                await self._block_navigation(page.main_frame, url, warning)
            else:
                await session.send("Fetch.continueResponse", {"requestId": request_id})
        except PlaywrightError:
            # A closed/detached page cannot continue navigation. Never log payloads.
            return

    async def install_navigation_guard(
        self,
        guard: Callable[[str, bool], Awaitable[None]],
    ) -> None:
        # Context-wide interception covers redirects, popups, frames and subresources.
        # Contexts disable service workers so requests cannot escape this route.
        self._navigation_guard = guard
        if self._monitor is not None:
            for page in self.get_context().pages:
                await self._attach_network_interceptor(page)

        async def route_request(route: Route) -> None:
            try:
                if self._monitor is not None:
                    warning = await self._monitor.warning(route.request.url)
                    if warning:
                        await route.abort("blockedbyclient")
                        if route.request.is_navigation_request():
                            try:
                                frame = route.request.frame
                            except PlaywrightError:
                                frame = self.get_active_page().main_frame
                            self._track_navigation_task(
                                self._block_navigation(frame, route.request.url, warning)
                            )
                        return
                await guard(route.request.url, route.request.is_navigation_request())
            except Exception:
                await route.abort("blockedbyclient")
            else:
                if (
                    self._monitor is not None
                    and self._monitor.enabled
                    and route.request.is_navigation_request()
                ):
                    try:
                        _ = route.request.frame
                    except PlaywrightError:
                        # Initial popup requests may have no Page/Frame to attach CDP to yet.
                        # Fetch without following redirects; never let this gap contact a target.
                        response = await route.fetch(
                            max_redirects=0, timeout=self.settings.nav_timeout_ms
                        )
                        location = response.headers.get("location")
                        if response.status in {301, 302, 303, 307, 308} and location:
                            destination = urljoin(route.request.url, location)
                            warning = await self._monitor.warning(destination)
                            await route.abort("blockedbyclient")
                            self._track_navigation_task(
                                self._block_navigation(
                                    self.get_active_page().main_frame,
                                    destination,
                                    warning or "Unverified popup redirect blocked",
                                )
                            )
                        else:
                            await route.fulfill(response=response)
                        await response.dispose()
                        return
                await route.continue_()

        await self.get_context().route("**/*", route_request)

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
            self._manager_started = True
            self._playwright = await self._manager.start()
            self._browser = await self._playwright.chromium.launch(
                headless=mode == "headless",
                channel="chromium",
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
                service_workers="block",
                permissions=[],
            )
            # An empty override grants none and denies the remaining permission prompts.
            await self._context.grant_permissions([])
            self._context.set_default_timeout(self.settings.action_timeout_ms)
            self._context.set_default_navigation_timeout(self.settings.nav_timeout_ms)
            self._context.on("page", self._on_page)
            self._page = await self._context.new_page()
        except asyncio.CancelledError:
            if not self._paused:
                await self.close()
            raise
        except Exception:
            await self.close()
            message = (
                "Cannot open headed Chromium; check the display and browser installation."
                if mode == "headed"
                else "Cannot start Chromium; run playwright install chromium; check dependencies."
            )
            raise BrowserFailure("BROWSER_ERROR", message) from None

    async def _settle(self, page: Page) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=2000)
        except PlaywrightTimeout:
            pass

    async def navigate(self, url: str) -> None:
        validate_url(url)
        if self._navigation_guard is not None and url != "about:blank":
            await self._navigation_guard(url, True)
        try:
            page = self.get_active_page()
            await page.goto(
                url, wait_until="domcontentloaded", timeout=self.settings.nav_timeout_ms
            )
            await self._settle(page)
        except asyncio.CancelledError:
            if not self._paused:
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
        self._closing = True
        callbacks = list(self._callback_tasks)
        for task in callbacks:
            task.cancel()
        await asyncio.gather(*callbacks, return_exceptions=True)
        for session in self._network_sessions.values():
            try:
                await session.detach()
            except PlaywrightError:
                pass
        self._network_sessions.clear()
        self._refs.clear()
        self._typed_values.clear()
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
        elif self._manager_started:
            # start() can be cancelled before it returns the Playwright object.
            await attempt(self._manager.__aexit__)

    async def observe(self) -> Observation:
        async with self._operation_lock:
            try:
                page = self.get_active_page()
                await page.wait_for_load_state(
                    "domcontentloaded", timeout=self.settings.nav_timeout_ms
                )
                self.generation += 1
                raw = await page.evaluate(
                    OBSERVE_SCRIPT,
                    {
                        "generation": self.generation,
                        "firstRef": self._next_ref,
                        "maxElements": self.settings.max_observed_elements,
                        "maxText": self.settings.max_observed_text_chars,
                    },
                )
                observation = Observation.model_validate(raw)
                self._refs = {
                    element.ref: (
                        self.generation,
                        page,
                        page.locator(f'[data-agent-ref="{element.ref}"]'),
                    )
                    for element in observation.elements
                }
                self._next_ref += len(observation.elements)
                return self.input_privacy.observation(observation)
            except asyncio.CancelledError:
                if not self._paused:
                    await self.close()
                raise
            except PlaywrightError as exc:
                raise BrowserFailure(error_code(exc), "Browser observation failed.") from None

    async def get_text(self) -> str:
        try:
            text = await self.get_active_page().evaluate(
                OBSERVE_SCRIPT,
                {
                    "maxText": self.settings.max_observed_text_chars,
                    "textOnly": True,
                },
            )
            return self._clean(str(text))
        except asyncio.CancelledError:
            if not self._paused:
                await self.close()
            raise
        except PlaywrightError as exc:
            raise BrowserFailure(error_code(exc), "Browser text extraction failed.") from None

    def _clean(self, text: str) -> str:
        text = self.input_privacy.scrub(text)
        if not self._typed_values:
            return text
        pattern = "|".join(
            re.escape(value) for value in sorted(self._typed_values, key=len, reverse=True)
        )
        return re.sub(pattern, "[redacted]", text)

    def _result(
        self,
        summary: str,
        *,
        ok: bool = True,
        code: ErrorCode | None = None,
        navigated: bool = False,
    ) -> ActionResult:
        notices, self._notices = self._notices, []
        return ActionResult(
            ok=ok,
            summary=self._clean("; ".join([summary, *notices]))[
                : self.settings.max_observed_text_chars
            ],
            error_code=code,
            navigated=navigated,
        )

    async def _resolve(self, action: Action) -> Locator:
        ref = action.target.ref
        if not ref:
            raise BrowserFailure("INVALID_ACTION", "This action requires an observed element ref.")
        record = self._refs.get(ref)
        if record is None:
            issued = re.fullmatch(r"e([1-9][0-9]*)", ref)
            code: ErrorCode = (
                "STALE_REF" if issued and int(issued[1]) < self._next_ref else "NOT_FOUND"
            )
            raise BrowserFailure(code, "Element ref is stale or unknown; observe again.")
        generation, page, locator = record
        if generation != self.generation or page is not self.get_active_page():
            raise BrowserFailure("STALE_REF", "Element ref belongs to an older page observation.")
        if await locator.count() != 1:
            raise BrowserFailure("NOT_FOUND", "Observed element no longer exists.")
        visible = await locator.evaluate("""el => {
            const rect = el.getBoundingClientRect();
            if (!rect.width || !rect.height) return false;
            for (let p = el; p; p=p.parentElement) {
                const s = getComputedStyle(p);
                if (p.hidden || p.getAttribute('aria-hidden') === 'true' || s.display === 'none' ||
                    s.visibility === 'hidden' || Number(s.opacity) === 0) return false;
            }
            return true;
        }""")
        if not visible:
            raise BrowserFailure("NOT_VISIBLE", "Observed element is not visible.")
        return locator

    async def act(self, action: Action) -> ActionResult:
        try:
            async with self._operation_lock:
                if self._paused:
                    return self._result("Actions are paused.", ok=False, code="PAUSED")
                timeout = self.settings.action_timeout_ms / 1000
                if action.action == "navigate":
                    timeout = self.settings.nav_timeout_ms / 1000 + 3
                elif action.action == "wait":
                    timeout = 11
                async with asyncio.timeout(timeout):
                    before_block = self._blocked_count
                    try:
                        result = await self._perform(action)
                    except Exception:
                        if self._blocked_count == before_block:
                            raise
                        result = self._result("Navigation blocked.", ok=False, code="BLOCKED_URL")
                    if self._navigation_tasks:
                        await asyncio.gather(*list(self._navigation_tasks))
                    if self._blocked_count != before_block:
                        return self._result("Navigation blocked.", ok=False, code="BLOCKED_URL")
                    return result
        except asyncio.CancelledError:
            if not self._paused:
                await self.close()
            raise
        except BrowserFailure as exc:
            return self._result(str(exc), ok=False, code=exc.code)
        except (PlaywrightTimeout, TimeoutError):
            return self._result("Browser action timed out.", ok=False, code="TIMEOUT")
        except Exception:
            return self._result("Browser action failed.", ok=False, code="BROWSER_ERROR")

    async def _perform(self, action: Action) -> ActionResult:
        page = self.get_active_page()
        before_page, before_url = page, page.url
        before_navigation = self._navigation_count
        locator = await self._resolve(action) if action.target.ref else None
        timeout = self.settings.action_timeout_ms
        summary = "Action completed."
        if action.action == "click":
            locator = locator or await self._resolve(action)
            if await locator.evaluate("el => Boolean(el.disabled)"):
                raise BrowserFailure("INVALID_ACTION", "Element is disabled.")
            await locator.scroll_into_view_if_needed(timeout=timeout)
            await locator.click(timeout=timeout)
            await asyncio.sleep(0.05)
            summary = "Clicked element."
        elif action.action == "type":
            keys = {
                "Enter",
                "Tab",
                "Escape",
                "Backspace",
                "Delete",
                "ArrowUp",
                "ArrowDown",
                "ArrowLeft",
                "ArrowRight",
                "Home",
                "End",
                "PageUp",
                "PageDown",
                "Space",
            }
            if (
                not action.target.ref
                and not action.target.description
                and action.value is not None
                and action.value in keys
            ):
                await page.keyboard.press(action.value)
                summary = "Pressed keyboard key."
            else:
                locator = locator or await self._resolve(action)
                if action.value is None:
                    raise BrowserFailure("INVALID_ACTION", "Typing requires a value.")
                value = action.value
                if value:
                    self._typed_values.add(value)
                metadata = await locator.evaluate("""el => ({tag:el.tagName.toLowerCase(),
                    password:el.type === 'password', editable:el.isContentEditable})""")
                await locator.scroll_into_view_if_needed(timeout=timeout)
                await locator.focus(timeout=timeout)
                if metadata["tag"] == "select":
                    by_label = await locator.evaluate(
                        "(el, value) => [...el.options].some(option => option.label === value)",
                        value,
                    )
                    if by_label:
                        await locator.select_option(label=value, timeout=timeout)
                    else:
                        await locator.select_option(value=value, timeout=timeout)
                    summary = "Selected option."
                elif metadata["tag"] in {"input", "textarea"}:
                    await locator.fill(value, timeout=timeout)
                    summary = (
                        "typed into password field" if metadata["password"] else "Typed into field."
                    )
                elif metadata["editable"]:
                    await locator.press("ControlOrMeta+A", timeout=timeout)
                    await locator.press_sequentially(value, timeout=timeout)
                    summary = "Typed into editable field."
                else:
                    raise BrowserFailure("INVALID_ACTION", "Element does not accept text.")
        elif action.action == "navigate":
            if not action.value:
                raise BrowserFailure("INVALID_ACTION", "Navigation requires a URL.")
            await self.navigate(action.value)
            summary = "Navigated page."
        elif action.action == "scroll":
            direction = action.value or "down"
            if direction not in {"up", "down", "top", "bottom"}:
                raise BrowserFailure("INVALID_ACTION", "Unknown scroll direction.")
            moved = await page.evaluate(
                """direction => {
                const before = scrollY, delta = Math.round(innerHeight * 0.8);
                if (direction === 'top') scrollTo(0,0);
                else if (direction === 'bottom') scrollTo(0,document.documentElement.scrollHeight);
                else scrollBy(0,direction === 'up' ? -delta : delta);
                return before !== scrollY;
            }""",
                direction,
            )
            summary = "Page scrolled." if moved else "Page did not move."
        elif action.action == "wait":
            try:
                seconds = float(action.value or "0.5")
            except ValueError:
                raise BrowserFailure(
                    "INVALID_ACTION", "Wait requires seconds as a number."
                ) from None
            if not math.isfinite(seconds):
                raise BrowserFailure("INVALID_ACTION", "Wait requires finite seconds.")
            await asyncio.sleep(max(0.5, min(10, seconds)))
            summary = "Wait completed."
        elif action.action == "extract":
            if locator is not None:
                text = await page.evaluate(
                    OBSERVE_SCRIPT,
                    {
                        "textOnly": True,
                        "targetRef": action.target.ref,
                        "maxText": self.settings.max_observed_text_chars,
                    },
                )
            else:
                text = await self.get_text()
            summary = self._clean(str(text))[: self.settings.max_observed_text_chars]
        elif action.action == "done":
            summary = "Done."
        current = self.get_active_page()
        navigated = (
            current is not before_page
            or current.url != before_url
            or self._navigation_count != before_navigation
        )
        if navigated and action.action != "navigate":
            await current.wait_for_load_state(
                "domcontentloaded", timeout=self.settings.nav_timeout_ms
            )
            await self._settle(current)
        return self._result(summary, navigated=navigated)

    def _activate(self, page: Page | None) -> None:
        previous = self._page
        self._page = page
        if page is None or page is previous:
            return
        if previous is not None:
            self._notices.append("active page changed")
        for callback in self._callbacks:
            self._schedule_callback(callback, page)

    def _schedule_callback(
        self, callback: Callable[[Page], Awaitable[None] | None], page: Page
    ) -> None:
        async def invoke() -> None:
            try:
                result = callback(page)
                if result is not None:
                    await result
            except Exception:
                # Callback failures must not expose browser content or break browser lifecycle.
                pass

        task = asyncio.create_task(invoke())
        self._callback_tasks.add(task)
        task.add_done_callback(self._callback_tasks.discard)

    def _on_page(self, page: Page) -> None:
        if self._monitor is not None:
            self._track_navigation_task(self._attach_network_interceptor(page))
        if self._closing:
            return
        page.on("dialog", self._dismiss_dialog)
        page.on("close", self._on_page_closed)
        page.on("framenavigated", self._on_frame_navigated)
        self._activate(page)

    def _on_page_closed(self, page: Page) -> None:
        if self._closing or page is not self._page:
            return
        remaining = [
            candidate for candidate in self.get_context().pages if not candidate.is_closed()
        ]
        previous = self._page
        self._activate(remaining[-1] if remaining else None)
        if previous is not self._page and self._page is not None:
            self._notices.append("active page closed; using remaining page")

    def _track_navigation_task(self, operation: Awaitable[None]) -> None:
        task = asyncio.ensure_future(operation)
        self._callback_tasks.add(task)
        self._navigation_tasks.add(task)
        task.add_done_callback(self._callback_tasks.discard)
        task.add_done_callback(self._navigation_tasks.discard)

    def _on_frame_navigated(self, frame: Frame) -> None:
        if self._monitor is not None and not self._closing:
            self._track_navigation_task(self._check_navigation(frame))
        if frame.parent_frame is None and frame.page is self._page:
            self._navigation_count += 1

    async def _dismiss_dialog(self, dialog: Dialog) -> None:
        self._notices.append(f"dialog dismissed: {dialog.type}")
        try:
            await dialog.dismiss()
        except PlaywrightError:
            pass

    def on_active_page_changed(self, callback: Callable[[Page], Awaitable[None] | None]) -> None:
        self._callbacks.append(callback)
        if self._page is not None:
            self._schedule_callback(callback, self._page)

    def remove_active_page_changed(
        self, callback: Callable[[Page], Awaitable[None] | None]
    ) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def get_viewport(self) -> ViewportInfo:
        return {
            "width": self.settings.viewport_width,
            "height": self.settings.viewport_height,
            "deviceScaleFactor": self.settings.device_scale_factor,
        }

    @property
    def actions_paused(self) -> bool:
        return self._paused

    async def pause_actions(self) -> None:
        self._paused = True
        self.input_privacy.active = True

    async def resume_actions(self) -> None:
        self._paused = False
