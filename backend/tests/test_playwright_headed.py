import pytest

from app.browser.playwright_driver import PlaywrightDriver
from app.browser.safety import display_available
from app.core.events import Action, Target
from tests.settings import IsolatedSettings
from tests.test_browser_integration import run_form
from tests.test_playwright_actions import element, perform

pytestmark = [
    pytest.mark.headed,
    pytest.mark.skipif(
        not display_available(), reason="Headed Chromium requires an available display."
    ),
]


async def test_headed_visible_smoke(testsite: str) -> None:
    driver = PlaywrightDriver(IsolatedSettings(browser_headless=True))
    try:
        # Explicit headed run mode overrides the global headless preference.
        await driver.start("headed")
        browser = driver.get_context().browser
        await driver.navigate(testsite + "/login.html")
        await perform(driver, "type", "Username", "demo-user")
        await perform(driver, "type", "Password", "demo-pass-only")
        await perform(driver, "click", "Sign in")
        assert "Welcome, demo-user" in (await driver.observe()).text_excerpt
        await driver.navigate(testsite + "/popup.html")
        ref = (await element(driver, "Open demo in new tab")).ref
        result = await driver.act(
            Action(action="click", target=Target(ref=ref), rationale="Open tab.")
        )
        assert result.ok and result.navigated
        assert (await driver.observe()).title == "Demo Search"
        await driver.close()
        assert browser is not None and not browser.is_connected()
    finally:
        await driver.close()


async def test_headed_scripted_form_runner(testsite: str) -> None:
    await run_form(testsite, "headed")
