import asyncio

from playwright.async_api import Page

from app.browser.playwright_driver import PlaywrightDriver
from app.core.events import Action, Target
from tests.test_playwright_actions import element


async def test_popup_switch_callback_and_fallback(driver: PlaywrightDriver, testsite: str) -> None:
    await driver.navigate(testsite + "/popup.html")
    original = driver.get_active_page()
    changed = asyncio.Event()
    pages: list[Page] = []

    def callback(page: Page) -> None:
        pages.append(page)
        changed.set()

    driver.on_active_page_changed(callback)
    await changed.wait()
    changed.clear()
    ref = (await element(driver, "Open demo in new tab")).ref
    result = await driver.act(
        Action(action="click", target=Target(ref=ref), rationale="Open demo tab.")
    )
    assert result.ok and result.navigated and "active page changed" in result.summary
    assert driver.get_active_page() is not original
    assert (await driver.observe()).title == "Demo Search"
    await asyncio.wait_for(changed.wait(), 1)
    assert pages[-1] is driver.get_active_page()
    await driver.get_active_page().close()
    assert driver.get_active_page() is original
    result = await driver.act(Action(action="done", rationale="Finish."))
    assert "using remaining page" in result.summary


async def test_alert_is_dismissed_without_dialog_text(
    driver: PlaywrightDriver, testsite: str
) -> None:
    await driver.navigate(testsite + "/popup.html")
    ref = (await element(driver, "Show alert")).ref
    result = await driver.act(
        Action(action="click", target=Target(ref=ref), rationale="Test alert.")
    )
    assert result.ok and "dialog dismissed: alert" in result.summary
    assert "Fake dialog text" not in result.summary
    assert driver.get_active_page().url.endswith("popup.html")


async def test_new_page_and_pause_hooks(driver: PlaywrightDriver) -> None:
    first = driver.get_active_page()
    second = await driver.get_context().new_page()
    assert driver.get_active_page() is second
    await second.close()
    assert driver.get_active_page() is first
    assert driver.get_viewport() == {"width": 1280, "height": 720, "deviceScaleFactor": 1}
    await driver.pause_actions()
    result = await driver.act(
        Action(action="navigate", value="https://example.test", rationale="Try while paused.")
    )
    assert result.error_code == "PAUSED"
    assert first.url == "about:blank"
    await driver.resume_actions()
    assert (await driver.act(Action(action="done", rationale="Finish."))).ok


async def test_no_permissions_are_granted(driver: PlaywrightDriver, testsite: str) -> None:
    await driver.navigate(testsite + "/index.html")
    states = await driver.get_active_page().evaluate("""async () => {
      const names=['geolocation','notifications','camera','microphone'];
      return await Promise.all(names.map(async name =>
        (await navigator.permissions.query({name})).state));
    }""")
    assert states == ["denied"] * 4
