from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

from playwright.async_api import CDPSession, Frame, Page
from playwright.async_api import Error as PlaywrightError

from app.browser.playwright_driver import PlaywrightDriver
from tests.settings import PolicySettings


async def test_block_stops_pending_loader_before_replacement_navigation() -> None:
    loading = True
    page = cast(Page, object())
    frame = SimpleNamespace(
        page=page,
        url="https://example.test/original",
        wait_for_load_state=AsyncMock(),
    )

    async def send(method: str) -> None:
        nonlocal loading
        assert method == "Page.stopLoading"
        loading = False

    async def goto(url: str, **kwargs: int) -> None:
        assert kwargs["timeout"] == 1000
        if loading:
            raise PlaywrightError("Pending loader interrupted replacement navigation.")
        frame.url = url

    session = SimpleNamespace(send=AsyncMock(side_effect=send))
    frame.goto = AsyncMock(side_effect=goto)
    callback = AsyncMock()
    driver = PlaywrightDriver(PolicySettings())
    driver._network_sessions[page] = cast(CDPSession, session)
    driver._on_block = callback
    await driver._block_navigation(
        cast(Frame, frame), "https://example.test/private?not-recorded=yes", "SSRF redirect blocked"
    )
    session.send.assert_awaited_once_with("Page.stopLoading")
    assert frame.url == "about:blank"
    callback.assert_awaited_once_with("example.test", "SSRF redirect blocked")


async def test_block_waits_for_renderer_to_apply_loader_stop() -> None:
    import asyncio

    stopped = asyncio.Event()
    page = cast(Page, object())
    frame = SimpleNamespace(
        page=page, url="https://example.test/original", wait_for_load_state=AsyncMock()
    )

    async def renderer_stops() -> None:
        await asyncio.sleep(0.01)
        stopped.set()

    renderer = asyncio.create_task(renderer_stops())

    async def goto(url: str, **kwargs: int) -> None:
        if not stopped.is_set():
            raise PlaywrightError("Renderer is still applying loader cancellation.")
        frame.url = url

    frame.goto = AsyncMock(side_effect=goto)
    callback = AsyncMock()
    driver = PlaywrightDriver(PolicySettings())
    driver._network_sessions[page] = cast(CDPSession, SimpleNamespace(send=AsyncMock()))
    driver._on_block = callback
    try:
        await driver._block_navigation(
            cast(Frame, frame), "https://example.test/", "SSRF redirect blocked"
        )
        assert frame.url == "about:blank"
        callback.assert_awaited_once_with("example.test", "SSRF redirect blocked")
    finally:
        await renderer
