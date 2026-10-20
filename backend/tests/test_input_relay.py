from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from playwright.async_api import CDPSession, Page

from app.browser.playwright_driver import PlaywrightDriver
from app.preview.input_protocol import Key, Mouse, Text, Wheel
from app.preview.input_relay import KEY_CODES, CdpInputRelay


def setup() -> tuple[CdpInputRelay, MagicMock, AsyncMock]:
    driver = MagicMock(spec=PlaywrightDriver)
    driver.get_viewport.return_value = {"width": 1280, "height": 720, "deviceScaleFactor": 2}
    driver.get_active_page.return_value = MagicMock(spec=Page)
    session = AsyncMock(spec=CDPSession)
    driver.get_context.return_value.new_cdp_session = AsyncMock(return_value=session)
    return CdpInputRelay(cast(PlaywrightDriver, driver)), driver, session


@pytest.mark.parametrize(
    "button,bit,count", [("left", 1, 1), ("left", 1, 2), ("right", 2, 1), ("middle", 4, 1)]
)
async def test_mouse_exact(button: str, bit: int, count: int) -> None:
    relay, _, session = setup()
    for action in ["down", "move", "up"]:
        assert await relay.send(
            Mouse.model_validate(
                dict(
                    type="mouse",
                    action=action,
                    x=-10,
                    y=900,
                    button=button,
                    clickCount=count,
                    modifiers=8,
                )
            )
        )
    calls = session.send.call_args_list
    assert [c.args for c in calls] == [
        (
            "Input.dispatchMouseEvent",
            dict(
                type=kind, x=0, y=719, button=button, buttons=buttons, clickCount=count, modifiers=8
            ),
        )
        for kind, buttons in [("mousePressed", bit), ("mouseMoved", bit), ("mouseReleased", 0)]
    ]
    await relay.close()
    await relay.close()
    session.detach.assert_awaited_once()


@pytest.mark.parametrize(
    "key",
    [
        "Enter",
        "Tab",
        "Backspace",
        "Delete",
        "Escape",
        "ArrowLeft",
        " ",
        "Home",
        "End",
        "PageUp",
        "PageDown",
    ],
)
async def test_keys_exact(key: str) -> None:
    relay, _, session = setup()
    code = "Space" if key == " " else key
    for action in ["down", "up"]:
        await relay.send(Key(type="key", action=action, key=key, code=code))  # type: ignore[arg-type]
    assert [c.args for c in session.send.call_args_list] == [
        (
            "Input.dispatchKeyEvent",
            dict(type=kind, key=key, code=code, windowsVirtualKeyCode=KEY_CODES[key], modifiers=0),
        )
        for kind in ["keyDown", "keyUp"]
    ]
    await relay.close()


async def test_wheel_shortcut_text_and_popup() -> None:
    relay, driver, session = setup()
    await relay.send(Wheel(type="wheel", x=25, y=30, dx=0, dy=200))
    session.send.assert_awaited_with(
        "Input.dispatchMouseEvent",
        dict(type="mouseWheel", x=25, y=30, buttons=0, deltaX=0, deltaY=200),
    )
    await relay.send(Key(type="key", action="down", key="a", code="KeyA", modifiers=2))
    session.send.assert_awaited_with(
        "Input.dispatchKeyEvent",
        dict(
            type="keyDown",
            key="a",
            code="KeyA",
            windowsVirtualKeyCode=65,
            modifiers=2,
            commands=["selectAll"],
        ),
    )
    await relay.send(Text(type="text", value="demo非拉丁"))
    session.send.assert_awaited_with("Input.insertText", {"text": "demo非拉丁"})
    driver.get_active_page.return_value = MagicMock(spec=Page)
    await relay.send(Text(type="text", value="next tab"))
    assert driver.get_context.return_value.new_cdp_session.await_count == 2
    await relay.close()
    assert not relay._keys and relay.buttons == 0


async def test_errors_are_not_propagated_or_echoed() -> None:
    relay, _, session = setup()
    session.send.side_effect = RuntimeError("PRIVATE-PAYLOAD")
    assert not await relay.send(Text(type="text", value="PRIVATE-PAYLOAD"))
    await relay.close()
