import asyncio

import pytest

from app.preview.framing import Frame, FrameMetadata, decode_frame, encode_frame
from app.preview.hub import PreviewHub, Status
from tests.settings import IsolatedSettings


def frame(seq: int = 1) -> Frame:
    return Frame(
        b"\xff\xd8test-image",
        FrameMetadata(
            format="jpeg",
            width=1280,
            height=720,
            deviceScaleFactor=1,
            viewportWidth=1280,
            viewportHeight=720,
            seq=seq,
            ts="2026-10-20T00:00:00Z",
            tabId="test-tab",
        ),
    )


@pytest.mark.parametrize("image", [b"", b"\xff\xd8", b"a" * 4_000_000])
@pytest.mark.parametrize("metadata", [{}, {"name": "Unicode ✓", "seq": 1}])
def test_framing_roundtrip(metadata: dict[str, object], image: bytes) -> None:
    assert decode_frame(encode_frame(metadata, image)) == (metadata, image)


@pytest.mark.parametrize("packet", [b"", b"\0\0\0\xff{}", b"\0\0\0\x02[]"])
def test_bad_framing(packet: bytes) -> None:
    with pytest.raises(ValueError):
        decode_frame(packet)


async def test_latest_wins_multiple_viewers_and_cleanup() -> None:
    hub = PreviewHub(IsolatedSettings(preview_client_queue=2))
    async with hub.subscribe() as slow, hub.subscribe() as fast:
        for seq in range(1, 101):
            hub.publish(frame(seq))
            while not fast.empty():
                fast.get_nowait()
        assert slow.qsize() == 2
        assert hub.latest and hub.latest.metadata.seq == 100
        newest = [await slow.get(), await slow.get()]
        assert all(isinstance(item, Frame) for item in newest)
        assert isinstance(newest[-1], Frame) and newest[-1].metadata.seq == 100
    assert not hub.viewers
    await hub.close()


async def test_idle_resend_stall_and_retention() -> None:
    hub = PreviewHub(IsolatedSettings(preview_idle_resend_s=0.01, preview_retain_after_end_s=0.03))
    hub.start()
    hub.publish(frame())
    async with hub.subscribe() as queue:
        await asyncio.sleep(0.025)
        assert hub.status.message == "Preview paused: page is idle"
        assert hub.latest is not None and queue.qsize() <= 2
        hub.last_activity -= 6
        await asyncio.sleep(0.02)
        assert hub.status.status == "stalled"
        await hub.end()
        assert hub.status == Status("ended", "Run ended")
        assert hub.latest is not None
        await asyncio.sleep(0.04)
        assert hub.latest is None
    await hub.close()


def test_transport_debug_payloads_are_filtered(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from app.logging import TransportPrivacyFilter, configure_logging

    filter_ = TransportPrivacyFilter()
    for name in ("uvicorn.error", "websockets.server", "websockets.client"):
        record = logging.LogRecord(
            name, logging.DEBUG, __file__, 1, "> %s", (b"PRIVATE_FRAME_AND_AUTH_DATA",), None
        )
        assert not filter_.filter(record)
    assert filter_.filter(
        logging.LogRecord("clevis", logging.INFO, __file__, 1, "state.transition", (), None)
    )
    configure_logging("DEBUG")
    transport = logging.getLogger("uvicorn.error")
    assert any(isinstance(item, TransportPrivacyFilter) for item in transport.filters)
    old_level = transport.level
    transport.addHandler(caplog.handler)
    try:
        transport.setLevel(logging.DEBUG)
        transport.debug("< %s", b"PRIVATE_FRAME_MARKER")
        transport.debug("< %s", '{"type":"auth","token":"PRIVATE_PREVIEW_TOKEN"}')
        assert "PRIVATE_FRAME_MARKER" not in caplog.text
        assert "PRIVATE_PREVIEW_TOKEN" not in caplog.text
    finally:
        transport.removeHandler(caplog.handler)
        transport.setLevel(old_level)


async def test_run_retention_starts_after_resource_cleanup() -> None:
    hub = PreviewHub(IsolatedSettings(preview_retain_after_end_s=0.02), defer_retention=True)
    hub.publish(frame())
    await hub.end()  # Capture stops before the browser's potentially slower close.
    await asyncio.sleep(0.03)
    assert hub.latest is not None
    hub.begin_retention()  # Runtime signals that the run and its cleanup have ended.
    assert hub.latest is not None
    await asyncio.sleep(0.03)
    assert hub.latest is None
    await hub.close()
