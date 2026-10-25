from app.browser.network import NavigationMonitor
from tests.settings import PolicySettings


async def test_post_navigation_rechecks_dns() -> None:
    addresses = iter([["93.184.216.34"], ["10.0.0.1"]])
    monitor = NavigationMonitor(PolicySettings(), resolver=lambda _: next(addresses))
    assert await monitor.warning("https://rebound.test/") is None
    assert await monitor.warning("https://rebound.test/", fresh=True) == "SSRF redirect blocked"
