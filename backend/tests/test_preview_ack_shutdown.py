"""Cancelling capture supervision must not cancel outstanding frame acknowledgements."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from playwright.async_api import CDPSession

from app.browser.playwright_driver import PlaywrightDriver
from app.preview.cdp import CdpScreencastChannel
from app.preview.hub import PreviewHub
from tests.settings import IsolatedSettings


async def test_shutdown_keeps_inflight_ack_alive_when_supervisor_is_cancelled() -> None:
    settings = IsolatedSettings()
    channel = CdpScreencastChannel(PlaywrightDriver(settings), PreviewHub(settings), settings)
    session = MagicMock(spec=CDPSession)
    ack_started = asyncio.Event()
    release_ack = asyncio.Event()
    stop_sent = asyncio.Event()

    async def send(method: str, params: dict[str, Any] | None = None) -> None:
        if method == "Page.screencastFrameAck":
            ack_started.set()
            await release_ack.wait()
        elif method == "Page.stopScreencast":
            stop_sent.set()

    session.send = AsyncMock(side_effect=send)
    session.detach = AsyncMock()
    channel.session = session
    channel.running = True
    ack = asyncio.create_task(channel._receive({"sessionId": 1}, session, "fake-tab"))
    channel._acks.add(ack)
    ack.add_done_callback(channel._acks.discard)
    await ack_started.wait()
    channel._supervisor = asyncio.create_task(channel._detach())
    await stop_sent.wait()
    # Let the supervisor enter its ack drain before stop cancels that supervisor.
    await asyncio.sleep(0)
    stopping = asyncio.create_task(channel.stop_stream())
    try:
        await asyncio.sleep(0.01)
        assert not ack.done(), "Supervisor cancellation must not cancel an in-flight frame ack"
        release_ack.set()
        await asyncio.wait_for(stopping, 1)
        assert channel.received == channel.acked == 1
        assert not channel._acks
        assert channel.session is None
        session.detach.assert_awaited_once()
    finally:
        release_ack.set()
        await asyncio.gather(ack, stopping, return_exceptions=True)
        await channel.hub.close()
