"""CDP input only: no DOM access, clipboard access, input history, payload logging or raw errors."""

import asyncio
from contextlib import suppress
from typing import Any

from playwright.async_api import CDPSession, Page

from app.browser.playwright_driver import PlaywrightDriver
from app.preview.input_protocol import Input, Key, Mouse, Text, Wheel

KEY_CODES: dict[str, int] = {
    "Enter": 13,
    "Tab": 9,
    "Backspace": 8,
    "Delete": 46,
    "Escape": 27,
    "ArrowLeft": 37,
    "ArrowUp": 38,
    "ArrowRight": 39,
    "ArrowDown": 40,
    "Home": 36,
    "End": 35,
    "PageUp": 33,
    "PageDown": 34,
    " ": 32,
    "Space": 32,
    "Shift": 16,
    "Control": 17,
    "Alt": 18,
    "Meta": 91,
}
BUTTONS = {"left": 1, "right": 2, "middle": 4}


class CdpInputRelay:
    def __init__(self, driver: PlaywrightDriver) -> None:
        self.driver = driver
        self.session: CDPSession | None = None
        self.page: Page | None = None
        self.buttons = 0
        self.closed = False
        self._dirty = True
        self._keys: dict[str, dict[str, Any]] = {}
        self._position = (0.0, 0.0)
        driver.on_active_page_changed(self._changed)

    def _changed(self, page: Page) -> None:
        if not self.closed and page is not self.page:
            self._dirty = True

    async def _attach(self) -> CDPSession:
        page = self.driver.get_active_page()
        if self._dirty or self.page is not page or self.session is None:
            await self._detach()
            if self.driver.actions_paused is True:
                await self.driver.prepare_input()
            self.page = page
            self.session = await self.driver.get_context().new_cdp_session(page)
            viewport = self.driver.get_viewport()
            if self.driver.actions_paused is True and viewport["deviceScaleFactor"] != 1:
                # A scaled screencast compositor misroutes input into out-of-process iframes.
                # Restore native CSS geometry before the first human input. Capture uses the
                # existing device-pixel screenshot fallback while paused at HiDPI.
                await self.session.send(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": viewport["width"],
                        "height": viewport["height"],
                        "deviceScaleFactor": viewport["deviceScaleFactor"],
                        "mobile": False,
                    },
                )
                # Chromium propagates the new compositor hit-test regions asynchronously;
                # an immediate click can still be routed using the previous scale.
                await asyncio.sleep(0.1)
            self.session.on("close", self._session_closed)
            self._dirty = False
        return self.session

    def _session_closed(self, session: CDPSession) -> None:
        if session is self.session:
            self._dirty = True

    async def send(self, message: Input) -> bool:
        if self.closed:
            return False
        try:
            session = await self._attach()
            if isinstance(message, Text):
                await session.send("Input.insertText", {"text": message.value})
            elif isinstance(message, Key):
                code = KEY_CODES.get(message.key, 0)
                if not code and len(message.key) == 1 and message.key.isascii():
                    code = ord(message.key.upper())
                params: dict[str, Any] = {
                    "type": "keyDown" if message.action == "down" else "keyUp",
                    "key": message.key,
                    "code": message.code,
                    "windowsVirtualKeyCode": code,
                    "modifiers": message.modifiers,
                }
                # Enter needs its generated character for native form submission in Chromium.
                if message.action == "down" and not message.modifiers & 7:
                    if message.key == "Enter":
                        params["text"] = "\r"
                    elif message.key in {" ", "Space"}:
                        params["text"] = " "
                # Blink's documented editing command also works on Linux without clipboard reads.
                if message.action == "down" and message.modifiers & 6:
                    command = {"a": "selectAll", "c": "copy", "x": "cut"}.get(message.key.lower())
                    if command:
                        params["commands"] = [command]
                if message.action == "down":
                    self._keys[message.code] = {k: v for k, v in params.items() if k != "commands"}
                else:
                    self._keys.pop(message.code, None)
                await session.send("Input.dispatchKeyEvent", params)
            elif isinstance(message, (Mouse, Wheel)):
                viewport = self.driver.get_viewport()
                x = min(max(0, message.x), viewport["width"] - 1)
                y = min(max(0, message.y), viewport["height"] - 1)
                self._position = (x, y)
                params = {"x": x, "y": y, "buttons": self.buttons}
                if isinstance(message, Mouse):
                    bit = BUTTONS[message.button]
                    if message.action == "down":
                        self.buttons |= bit
                    elif message.action == "up":
                        self.buttons &= ~bit
                    params.update(
                        {
                            "type": {
                                "move": "mouseMoved",
                                "down": "mousePressed",
                                "up": "mouseReleased",
                            }[message.action],
                            "button": message.button
                            if message.action != "move" or self.buttons
                            else "none",
                            "buttons": self.buttons,
                            "clickCount": message.clickCount,
                            "modifiers": message.modifiers,
                        }
                    )
                else:
                    params.update(
                        {"type": "mouseWheel", "deltaX": message.dx, "deltaY": message.dy}
                    )
                await session.send("Input.dispatchMouseEvent", params)
            return True
        except asyncio.CancelledError:
            raise
        except Exception:
            # The driver/transport may put text into its exception; never propagate or stringify it.
            self._dirty = True
            return False

    async def _detach(self) -> None:
        session, self.session = self.session, None
        if session:
            with suppress(Exception):
                async with asyncio.timeout(0.25):
                    for key in self._keys.values():
                        await session.send(
                            "Input.dispatchKeyEvent", {**key, "type": "keyUp", "modifiers": 0}
                        )
                    for button, bit in BUTTONS.items():
                        if self.buttons & bit:
                            await session.send(
                                "Input.dispatchMouseEvent",
                                {
                                    "type": "mouseReleased",
                                    "x": self._position[0],
                                    "y": self._position[1],
                                    "button": button,
                                    "buttons": 0,
                                    "clickCount": 1,
                                },
                            )
            with suppress(Exception):
                async with asyncio.timeout(0.25):
                    await session.detach()
        self._keys.clear()
        self.buttons = 0
        self._position = (0, 0)
        self.page = None

    async def close(self) -> None:
        self.closed = True
        self.driver.remove_active_page_changed(self._changed)
        await self._detach()
