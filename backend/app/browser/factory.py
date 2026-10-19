from app.browser.playwright_driver import PlaywrightDriver
from app.config import Settings
from app.fakes.fake_driver import FakeBrowserDriver
from app.interfaces.browser import BrowserDriver


def create_browser_driver(settings: Settings) -> BrowserDriver:
    if settings.browser_driver == "playwright":
        return PlaywrightDriver(settings)
    return FakeBrowserDriver()
