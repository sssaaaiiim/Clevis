import asyncio

import pytest

from app.agent.policy.validator import PolicyValidator
from app.browser.network import NavigationMonitor
from app.browser.playwright_driver import PlaywrightDriver
from tests.settings import PolicySettings


@pytest.mark.parametrize(
    "mode,domain", [("js", "127.0.0.1"), ("meta", "192.168.1.1"), ("form", "10.0.0.1")]
)
async def test_browser_blocks_page_driven_navigation(testsite: str, mode: str, domain: str) -> None:
    driver = PlaywrightDriver(PolicySettings())
    blocks: list[tuple[str, str]] = []
    ready = asyncio.Event()

    async def blocked(host: str, warning: str) -> None:
        blocks.append((host, warning))
        ready.set()

    await driver.start("headless")
    try:
        # Allow only the dedicated fixture's origin; no external DNS/network is used.
        monitor = NavigationMonitor(PolicySettings(), resolver=lambda _: ["93.184.216.34"])
        original = monitor.warning

        async def fixture_warning(url: str, *, fresh: bool = False) -> str | None:
            return None if url.startswith(testsite + "/") else await original(url, fresh=fresh)

        monitor.warning = fixture_warning  # type: ignore[method-assign]
        driver.configure_navigation_monitor(monitor, blocked)

        async def policy(url: str, navigation: bool) -> None:
            return None

        await driver.install_navigation_guard(policy)
        await driver.navigate(testsite + "/ssrf-redirect.html")
        page = driver.get_active_page()
        if mode == "form":
            await page.locator('button[type="submit"]').click()
        else:
            await page.locator("#" + mode).click()
        await asyncio.wait_for(ready.wait(), 2)
        assert (domain, "SSRF redirect blocked") in blocks
        assert page.url == "about:blank"
    finally:
        await driver.close()


async def test_browser_guard_is_independent_from_policy() -> None:
    settings = PolicySettings()
    monitor = NavigationMonitor(settings, resolver=lambda _: ["10.0.0.1"])
    policy = PolicyValidator(settings, resolver=lambda _: ["93.184.216.34"])
    assert (await policy._destination("https://public.test/")).tier == 0
    assert await monitor.warning("https://public.test/") == "SSRF redirect blocked"


async def test_pinchtab_action_keeps_playwright_navigation_hook(testsite: str) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.browser.pinchtab_driver import PinchtabDriver
    from app.core.events import Action

    driver = PinchtabDriver(PolicySettings())
    await PlaywrightDriver.start(driver, "headless")
    ready = asyncio.Event()

    async def blocked(host: str, warning: str) -> None:
        assert host == "127.0.0.1" and warning == "SSRF redirect blocked"
        ready.set()

    monitor = NavigationMonitor(PolicySettings(), resolver=lambda _: ["93.184.216.34"])
    original = monitor.warning

    async def fixture_warning(url: str, *, fresh: bool = False) -> str | None:
        return None if url.startswith(testsite + "/") else await original(url, fresh=fresh)

    monitor.warning = fixture_warning  # type: ignore[method-assign]
    driver.configure_navigation_monitor(monitor, blocked)

    async def policy(url: str, navigation: bool) -> None:
        return None

    await driver.install_navigation_guard(policy)
    page = driver.get_active_page()

    async def api_navigate(tab: str, url: str) -> None:
        await page.goto(url)

    driver.api = SimpleNamespace(  # type: ignore[assignment]
        navigate=api_navigate,
        close=AsyncMock(),
        stop=AsyncMock(),
        client=SimpleNamespace(is_closed=False),
    )
    driver._tab = AsyncMock(return_value="local-tab")  # type: ignore[method-assign]
    try:
        result = await driver.act(
            Action(
                action="navigate",
                value=testsite + "/ssrf-redirect.html?mode=js",
                rationale="Open fixture.",
            )
        )
        assert result.ok
        await asyncio.wait_for(ready.wait(), 2)
        assert page.url == "about:blank"
    finally:
        await driver.close()
