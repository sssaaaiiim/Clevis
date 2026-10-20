from app.browser.playwright_driver import PlaywrightDriver
from app.config import Settings
from app.interfaces.browser import BrowserDriver, PreviewChannel
from app.preview.cdp import CdpScreencastChannel
from app.preview.control import InputRelay
from app.preview.fake import FakePreviewChannel
from app.preview.hub import PreviewHub
from app.preview.input_relay import CdpInputRelay


def create_preview_channel(
    driver: BrowserDriver,
    hub: PreviewHub,
    settings: Settings,
) -> PreviewChannel:
    if isinstance(driver, PlaywrightDriver):
        return CdpScreencastChannel(driver, hub, settings)
    return FakePreviewChannel(hub, settings)


def create_input_relay(driver: BrowserDriver) -> InputRelay | None:
    return CdpInputRelay(driver) if isinstance(driver, PlaywrightDriver) else None
