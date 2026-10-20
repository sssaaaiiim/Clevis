"""Authenticated input transport. Never log input, rejected payloads or exception text."""

import asyncio
import hmac
from contextlib import suppress
from time import monotonic
from typing import Any, cast

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.state import TERMINAL_STATES
from app.core.store import RunNotFound
from app.preview.factory import create_input_relay
from app.preview.input_protocol import Auth, Key, Mouse, Ping, RateLimit, Text, parse_input
from app.runtime import RunService

router = APIRouter(prefix="/api/runs")
AUTH_TIMEOUT_S = 5.0


@router.websocket("/{run_id}/input")
async def input_socket(socket: WebSocket, run_id: str) -> None:
    await socket.accept()
    service = cast(RunService, socket.app.state.service)
    try:
        await service.store.get(run_id)
    except RunNotFound:
        await socket.close(code=4404, reason="Run not found.")
        return
    if socket.headers.get("origin") != service.settings.frontend_origin:
        await socket.close(code=4403, reason="Origin denied.")
        return

    async def receive() -> str | bytes | None:
        message = await socket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))
        return cast(str | bytes | None, message.get("text", message.get("bytes")))

    try:
        async with asyncio.timeout(AUTH_TIMEOUT_S):
            auth = parse_input(await receive(), service.settings)
        expected = service.control_tokens.get(run_id, "")
        if (
            not isinstance(auth, Auth)
            or not expected
            or not hmac.compare_digest(auth.token.encode(), expected.encode())
        ):
            await socket.close(code=4401, reason="Control authentication required.")
            return
        del auth
    except TimeoutError:
        await socket.close(code=4401, reason="Control authentication timed out.")
        return
    except WebSocketDisconnect:
        return
    control = service.controls[run_id]
    owner = control.claim()
    if owner is None:
        await socket.close(code=4409, reason="Another window controls this run.")
        return
    ended = control.disconnected
    send_lock = asyncio.Lock()

    async def send(value: dict[str, Any]) -> None:
        if value.get("type") == "state":
            value = {
                **value,
                "limits": {
                    "maxTextLength": service.settings.input_max_text_length,
                    "maxMessageBytes": service.settings.input_max_message_bytes,
                },
            }
        async with asyncio.timeout(2):
            async with send_lock:
                await socket.send_json(value)

    async def watch() -> None:
        previous: bool | None = None
        while not ended.is_set():
            accepting = await control.accepting(owner)
            if accepting != previous:
                await send({"type": "state", "accepting": accepting, "controller": True})
                previous = accepting
            if (await service.store.get(run_id)).status in TERMINAL_STATES:
                return
            await asyncio.sleep(0.03)

    async def inputs() -> None:
        rate = RateLimit(service.settings.input_max_messages_per_second)
        rejects = 0
        while not ended.is_set():
            raw = await receive()
            control.counters.received += 1
            if not rate.allow():
                control.counters.rate_limited += 1
                del raw
                continue
            message = parse_input(raw, service.settings)
            del raw
            if message is None or isinstance(message, Auth):
                rejects += 1
                control.counters.rejected += 1
                if rejects >= 50:
                    await socket.close(code=4400, reason="Too many invalid messages.")
                    return
                continue
            if isinstance(message, Ping):
                control.last_activity = monotonic()
                await send({"type": "pong"})
                continue
            async with control.lock:
                if not await control.accepting(owner):
                    await send({"type": "state", "accepting": False, "controller": True})
                else:
                    if control.relay is None:
                        control.relay = create_input_relay(service.drivers[run_id])
                    control.last_activity = monotonic()
                    privacy = control.machine.input_privacy
                    if isinstance(message, Text):
                        privacy.remember(message.value)
                    elif isinstance(message, Mouse) and message.action == "down":
                        privacy.boundary()
                    elif isinstance(message, Key):
                        if len(message.key) == 1 and not message.modifiers & 6:
                            privacy.remember(message.key)
                        elif message.key in {"Tab", "Enter", "Backspace", "Delete"}:
                            privacy.boundary()
                    try:
                        async with asyncio.timeout(1):
                            ok = await control.relay.send(message) if control.relay else False
                        if not ok:
                            await send({"type": "error", "code": "INPUT_UNAVAILABLE"})
                    except Exception:
                        await send({"type": "error", "code": "INPUT_UNAVAILABLE"})
            del message

    tasks = [
        asyncio.create_task(inputs()),
        asyncio.create_task(watch()),
        asyncio.create_task(ended.wait()),
    ]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        # ASGI cancellation can repeat; finish releasing sockets/sessions before propagating it.
        with anyio.CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            async with control.lock:
                await control.release(owner)
            with suppress(RuntimeError, WebSocketDisconnect, OSError):
                await socket.close(code=1000)
