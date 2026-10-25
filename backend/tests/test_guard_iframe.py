from app.agent.policy.validator import PolicyValidator
from app.browser.network import NavigationMonitor
from app.browser.playwright_driver import PlaywrightDriver
from tests.settings import IsolatedSettings


async def test_security_guard_preserves_cross_origin_iframe_loading(testsite: str) -> None:
    options = IsolatedSettings()
    driver = PlaywrightDriver(options)
    policy = PolicyValidator(options)

    async def blocked(domain: str, warning: str) -> None:
        raise AssertionError("Allowed iframe was blocked")

    await driver.start("headless")
    try:
        driver.configure_navigation_monitor(NavigationMonitor(options), blocked)
        await driver.install_navigation_guard(policy.guard_url)
        await driver.navigate(testsite + "/index.html")
        page = driver.get_active_page()
        await page.evaluate(
            """url => { const el = document.createElement('iframe');
                el.id='child'; el.src=url; document.body.append(el); }""",
            testsite.replace("127.0.0.1", "localhost") + "/form.html",
        )
        await page.frame_locator("#child").get_by_label("Newsletter").wait_for(timeout=3000)
    finally:
        await driver.close()


async def test_guard_preserves_popup_preview_pause_and_iframe(testsite: str) -> None:

    from app.preview.cdp import CdpScreencastChannel
    from app.preview.hub import PreviewHub

    options = IsolatedSettings()
    driver = PlaywrightDriver(options)
    hub = PreviewHub(options)
    preview = CdpScreencastChannel(driver, hub, options)
    blocks: list[str] = []

    async def blocked(domain: str, warning: str) -> None:
        blocks.append(warning)

    async def frame(data: bytes) -> None:
        pass

    await driver.start("headless")
    try:
        driver.configure_navigation_monitor(NavigationMonitor(options), blocked)
        await driver.install_navigation_guard(PolicyValidator(options).guard_url)
        await preview.start_stream(frame)
        await driver.navigate(testsite + "/popup.html")
        page = driver.get_active_page()
        async with page.expect_popup() as pending:
            await page.locator('a[target="_blank"]').click()
        popup = await pending.value
        await popup.wait_for_load_state("domcontentloaded")
        await popup.locator("#search").wait_for(timeout=3000)
        await driver.pause_actions()
        await popup.evaluate(
            """url => {const child=document.createElement('iframe');
            child.id='guard-child'; child.src=url; document.body.append(child);}""",
            testsite.replace("127.0.0.1", "localhost") + "/form.html",
        )
        await popup.frame_locator("#guard-child").get_by_label("Newsletter").wait_for(timeout=3000)
        assert not blocks
    finally:
        await preview.stop_stream()
        await driver.close()
        await hub.close()
