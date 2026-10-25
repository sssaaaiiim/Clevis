from app.browser.network import NavigationMonitor
from tests.settings import PolicySettings


async def test_post_navigation_rechecks_dns() -> None:
    addresses = iter([["93.184.216.34"], ["10.0.0.1"]])
    monitor = NavigationMonitor(PolicySettings(), resolver=lambda _: next(addresses))
    assert await monitor.warning("https://rebound.test/") is None
    assert await monitor.warning("https://rebound.test/", fresh=True) == "SSRF redirect blocked"


async def test_frame_navigation_hook_performs_fresh_dns_check() -> None:
    from types import SimpleNamespace
    from typing import cast
    from unittest.mock import AsyncMock

    from playwright.async_api import Frame

    from app.browser.playwright_driver import PlaywrightDriver

    addresses = iter([["93.184.216.34"], ["192.168.1.1"]])
    monitor = NavigationMonitor(PolicySettings(), resolver=lambda _: next(addresses))
    driver = PlaywrightDriver(PolicySettings())
    callback = AsyncMock()
    driver.configure_navigation_monitor(monitor, callback)
    frame = SimpleNamespace(
        url="https://rebound.test/private?not-recorded=yes", wait_for_load_state=AsyncMock()
    )

    async def goto(url: str, **kwargs: object) -> None:
        frame.url = url

    frame.goto = AsyncMock(side_effect=goto)
    assert await monitor.warning(frame.url) is None
    await driver._check_navigation(cast(Frame, frame))
    callback.assert_awaited_once_with("rebound.test", "SSRF redirect blocked")
    assert frame.url == "about:blank"
