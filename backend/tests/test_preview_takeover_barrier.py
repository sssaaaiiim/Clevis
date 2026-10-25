"""Input must wait for capture ownership to release scaled geometry."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from playwright.async_api import CDPSession, Page

from app.browser.playwright_driver import PlaywrightDriver
from app.preview.cdp import CdpScreencastChannel
from app.preview.hub import PreviewHub
from app.preview.input_protocol import Mouse
from app.preview.input_relay import CdpInputRelay
from tests.settings import IsolatedSettings


async def test_no_mouse_dispatch_before_preview_transition_completes() -> None:
    driver = PlaywrightDriver(IsolatedSettings(device_scale_factor=2))
    channel = CdpScreencastChannel(driver, PreviewHub(driver.settings), driver.settings)
    driver.on_input_prepare(channel._prepare_input)
    channel.running = True
    await driver.pause_actions()
    page = MagicMock(spec=Page)
    page.is_closed.return_value = False
    context = MagicMock()
    session = AsyncMock(spec=CDPSession)
    context.new_cdp_session = AsyncMock(return_value=session)
    driver._page = page
    driver._context = context
    relay = CdpInputRelay(driver)
    pending = asyncio.create_task(relay.send(Mouse(type="mouse", action="down", x=2, y=2)))
    try:
        await asyncio.sleep(0.02)
        assert not pending.done()
        context.new_cdp_session.assert_not_awaited()
        assert channel._wake.is_set()
        channel._native_ready.set()
        assert await asyncio.wait_for(pending, 1)
        assert session.send.call_args_list[-1].args[0] == "Input.dispatchMouseEvent"
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        channel.running = False
        await relay.close()
        await channel.hub.close()


async def test_supervisor_detaches_before_signalling_native_geometry() -> None:
    driver = PlaywrightDriver(IsolatedSettings(device_scale_factor=2))
    channel = CdpScreencastChannel(driver, PreviewHub(driver.settings), driver.settings)
    await driver.pause_actions()
    channel.running = True
    detached = asyncio.Event()
    release_capture = asyncio.Event()

    async def detach() -> None:
        detached.set()

    async def screenshot() -> None:
        assert detached.is_set() and not channel._native_ready.is_set()
        await release_capture.wait()

    channel._detach = detach  # type: ignore[method-assign]
    channel._screenshot = screenshot  # type: ignore[method-assign]
    supervisor = asyncio.create_task(channel._supervise())
    try:
        await asyncio.wait_for(detached.wait(), 1)
        assert not channel._native_ready.is_set()
        release_capture.set()
        await asyncio.wait_for(channel._native_ready.wait(), 1)
        assert channel._takeover_fallback
    finally:
        channel.running = False
        supervisor.cancel()
        await asyncio.gather(supervisor, return_exceptions=True)
        await channel.hub.close()
