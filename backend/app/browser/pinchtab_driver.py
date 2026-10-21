"""Optional fixed hybrid: Playwright owns lifetime/privacy/preview/input; PinchTab refs/actions."""

import asyncio
import math
import socket
from collections import Counter
from contextlib import suppress

from app.browser.pinchtab_api import PinchSnapshot, PinchtabAPI, execute
from app.browser.playwright_driver import PlaywrightDriver
from app.browser.safety import display_available, validate_url
from app.config import Settings
from app.core.events import Action, Mode
from app.interfaces.browser import ActionResult, BrowserFailure, Observation


def reconcile(snapshot: PinchSnapshot, baseline: Observation) -> tuple[Observation, dict[str, str]]:
    """Never trust PinchTab values/hidden claims: expose only uniquely matched safe DOM elements."""
    safe_counts = Counter((e.role, e.name) for e in baseline.elements)
    pinch_counts = Counter((n.role, n.name) for n in snapshot.nodes)
    lookup = {(n.role, n.name): n.ref for n in snapshot.nodes}
    elements = []
    refs = {}
    for element in baseline.elements:
        signature = (element.role, element.name)
        if safe_counts[signature] == 1 and pinch_counts[signature] == 1:
            elements.append(element)
            refs[element.ref] = lookup[signature]
    return baseline.model_copy(update={"elements": elements}), refs


class PinchtabDriver(PlaywrightDriver):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.api: PinchtabAPI | None = None
        self.instance: str | None = None
        self._pinch_refs: dict[str, str] = {}
        self._observation: Observation | None = None
        self._epoch: tuple[object, str, int] | None = None
        self._tab_id: str | None = None

    async def start(self, mode: Mode) -> None:
        if mode == "headed" and not display_available():
            raise BrowserFailure("BROWSER_ERROR", "Headed Chromium requires a display.")
        try:
            self.api = PinchtabAPI(self.settings)
            task = asyncio.current_task()
            name = task.get_name() if task else ""
            await self.api.health(
                name.removeprefix("run:") if name.startswith("run:") else "unassigned"
            )
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            self._manager_started = True
            self._playwright = await self._manager.start()
            self._browser = await self._playwright.chromium.launch(
                channel="chromium",
                headless=mode == "headless",
                slow_mo=self.settings.slow_mo_ms,
                args=["--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}"],
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
            await self._context.grant_permissions([])
            self._context.set_default_timeout(self.settings.action_timeout_ms)
            self._context.set_default_navigation_timeout(self.settings.nav_timeout_ms)
            self._context.on("page", self._on_page)
            self._page = await self._context.new_page()
            self.instance = await self.api.attach(port)
        except BaseException:
            await self.close()
            raise

    async def _tab(self) -> str:
        if self.api is None or self.instance is None:
            raise BrowserFailure("BROWSER_ERROR", "PinchTab has not attached to this run.")
        page = self.get_active_page()
        session = await self.get_context().new_cdp_session(page)
        try:
            target = (await session.send("Target.getTargetInfo"))["targetInfo"]["targetId"]
        finally:
            await session.detach()
        return await self.api.tab(self.instance, str(target), page.url)

    async def observe(self) -> Observation:
        if self._paused:
            raise BrowserFailure("PAUSED", "Actions are paused.")
        baseline = await super().observe()
        assert self.api
        tab = await self._tab()
        if baseline.url == "about:blank":
            # PinchTab filters bootstrap blank tabs; no webpage observation exists yet.
            await self.api.health()
            self._pinch_refs.clear()
            self._observation = baseline
            return baseline
        snapshot = await self.api.snapshot(tab)
        # Apply input fingerprints before matching; raw upstream values never survive.
        for node in snapshot.nodes:
            node.name = self.input_privacy.scrub(node.name)[:80]
        observation, self._pinch_refs = reconcile(snapshot, baseline)
        self._observation = observation
        self._tab_id = tab
        self._epoch = (self.get_active_page(), baseline.url, self._navigation_count)
        return observation

    async def act(self, action: Action) -> ActionResult:
        if self._paused:
            return self._result("Actions are paused.", ok=False, code="PAUSED")
        try:
            assert self.api
            tab = await self._tab()
            page = self.get_active_page()
            if action.target.ref and (
                self._epoch != (page, page.url, self._navigation_count)
                or action.target.ref not in self._pinch_refs
            ):
                return self._result(
                    "Reference is stale; observe again.", ok=False, code="STALE_REF"
                )
            if action.action == "navigate" and page.url == "about:blank":
                if not action.value:
                    raise BrowserFailure("INVALID_ACTION", "Navigation needs a URL.")
                validate_url(action.value)
                await self.api.navigate(tab, action.value)
                await page.wait_for_load_state("domcontentloaded")
                return self._result("Navigated page.", navigated=True)
            fresh = await self.api.snapshot(tab)  # Always verify current server refs before acting.
            ref = self._pinch_refs.get(action.target.ref or "")
            element = (
                next((e for e in self._observation.elements if e.ref == action.target.ref), None)
                if self._observation
                else None
            )
            if ref:
                await self._resolve(
                    action
                )  # Same visibility/staleness checks as the default driver.
                if (
                    not any(
                        n.ref == ref
                        and n.role == element.role
                        and self.input_privacy.scrub(n.name)[:80] == element.name
                        for n in fresh.nodes
                    )
                    if element
                    else True
                ):
                    return self._result(
                        "Reference is stale; observe again.", ok=False, code="STALE_REF"
                    )
            if self._paused:
                return self._result("Actions are paused.", ok=False, code="PAUSED")
            if action.action == "navigate":
                if not action.value:
                    raise BrowserFailure("INVALID_ACTION", "Navigation needs a URL.")
                validate_url(action.value)
                await self.api.navigate(tab, action.value)
                await page.wait_for_load_state("domcontentloaded")
                return self._result("Navigated page.", navigated=True)
            if action.action == "extract":
                # Never expose unfiltered upstream text or password echoes.
                return self._result(
                    (self._observation.text_excerpt if self._observation else "")[
                        : self.settings.max_observed_text_chars
                    ]
                )
            if action.action == "wait":
                seconds = float(action.value or ".5")
                if not math.isfinite(seconds):
                    raise ValueError
                await asyncio.sleep(max(0.5, min(10, seconds)))
            elif action.action == "done":
                pass
            else:
                if action.action == "type" and action.value:
                    self._typed_values.add(action.value)
                await execute(
                    self.api,
                    tab,
                    action,
                    ref,
                    element.tag if element else "",
                    self.settings.viewport_height,
                )
            return self._result(
                "typed into password field"
                if element and element.type == "password" and action.action == "type"
                else "PinchTab action completed."
            )
        except asyncio.CancelledError:
            if not self._paused:
                await self.close()
            raise
        except BrowserFailure as exc:
            return self._result(str(exc), ok=False, code=exc.code)
        except ValueError:
            return self._result("Invalid action value.", ok=False, code="INVALID_ACTION")
        except Exception:
            return self._result("PinchTab browser action failed.", ok=False, code="BROWSER_ERROR")

    async def pause_actions(self) -> None:
        await super().pause_actions()

    async def resume_actions(self) -> None:
        self._epoch = None
        self._pinch_refs.clear()
        await super().resume_actions()

    async def close(self) -> None:
        api, self.api = self.api, None
        try:
            if api:
                cleanup = PinchtabAPI(self.settings) if api.client.is_closed else api
                with suppress(Exception):
                    async with asyncio.timeout(0.3):
                        if self.instance:
                            await cleanup.stop(self.instance)
                await cleanup.close()
                if cleanup is not api:
                    await api.close()
        finally:
            self.instance = None
            self._pinch_refs.clear()
            self._observation = None
            await super().close()
