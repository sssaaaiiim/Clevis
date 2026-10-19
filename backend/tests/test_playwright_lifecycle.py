from typing import cast

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from app.browser.playwright_driver import PlaywrightDriver, error_code
from app.browser.safety import BrowserFailure
from tests.settings import IsolatedSettings


async def test_isolated_contexts_and_idempotent_close() -> None:
    first, second = PlaywrightDriver(IsolatedSettings()), PlaywrightDriver(IsolatedSettings())
    try:
        await first.start("headless")
        await second.start("headless")
        a, b = first.get_context(), second.get_context()
        assert a is not b
        await a.add_cookies([{"name": "demo", "value": "fake", "url": "http://localhost"}])
        assert not await b.cookies()
        page = first.get_active_page()
        assert page.viewport_size == {"width": 1280, "height": 720}
        assert await page.evaluate("devicePixelRatio") == 1
        browser = a.browser
        await first.close()
        await first.close()
        assert browser is not None and not browser.is_connected()
        with pytest.raises(BrowserFailure):
            first.get_active_page()
    finally:
        await first.close()
        await second.close()


async def test_blank_navigation() -> None:
    driver = PlaywrightDriver(IsolatedSettings())
    try:
        await driver.start("headless")
        await driver.navigate("about:blank")
        assert driver.get_active_page().url == "about:blank"
        with pytest.raises(BrowserFailure) as exc:
            await driver.navigate("file:///etc/passwd")
        assert exc.value.code == "BLOCKED_URL"
    finally:
        await driver.close()


async def test_no_display_is_clear_and_does_not_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr("app.browser.safety.sys.platform", "linux")
    driver = PlaywrightDriver(IsolatedSettings())
    with pytest.raises(BrowserFailure, match="requires a display"):
        await driver.start("headed")
    await driver.close()


def test_sanitized_error_mapping() -> None:
    assert error_code(PlaywrightTimeout("secret raw diagnostics")) == "TIMEOUT"
    assert error_code(PlaywrightError("raw details")) == "BROWSER_ERROR"
    assert error_code(BrowserFailure("NOT_FOUND", "missing")) == "NOT_FOUND"
    assert error_code(cast(Exception, ValueError("private input"))) == "BROWSER_ERROR"
