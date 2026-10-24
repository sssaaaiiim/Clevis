import pytest
from playwright.async_api import Error as PlaywrightError

from app.agent.policy.validator import PolicyValidator
from app.agent.state import AgentState
from app.browser.playwright_driver import PlaywrightDriver
from app.core.events import Action
from tests.settings import PolicySettings


async def test_private_navigation_denied_by_policy_and_browser_boundary() -> None:
    settings = PolicySettings(block_private_network=True)
    validator = PolicyValidator(settings, resolver=lambda _: ["8.8.8.8"])
    action = Action(action="navigate", value="http://127.0.0.1:8765", rationale="Open page.")
    assert (await validator.validate(AgentState(goal="Test"), action)).tier == 3
    driver = PlaywrightDriver(settings)
    await driver.start("headless")
    try:
        await driver.install_navigation_guard(validator.guard_url)
        result = await driver.act(action)
        assert not result.ok and result.error_code == "BLOCKED_URL"
        assert driver.get_active_page().url == "about:blank"
        # Even direct page navigation cannot bypass context-wide policy interception.
        with pytest.raises(PlaywrightError, match="ERR_BLOCKED_BY_CLIENT"):
            await driver.get_active_page().goto("http://127.0.0.1:8765", timeout=1500)
        assert driver.get_active_page().url == "about:blank"
    finally:
        await driver.close()
