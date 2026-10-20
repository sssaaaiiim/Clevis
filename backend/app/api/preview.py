import asyncio
import hmac
import json
from contextlib import suppress
from time import monotonic
from typing import Any, cast

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.store import RunNotFound
from app.preview.framing import Frame
from app.preview.hub import Message, Status
from app.runtime import RunService

router = APIRouter(prefix="/api/runs")
PING_INTERVAL_S = 20.0


async def read_message(socket: WebSocket) -> dict[str, Any] | None:
    message = await socket.receive()
    if message["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    text = message.get("text")
    if not isinstance(text, str) or len(text) > 4096:
        return None
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except ValueError:
        return None


@router.websocket("/{run_id}/preview")
async def preview(socket: WebSocket, run_id: str) -> None:
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
    try:
        async with asyncio.timeout(service.settings.preview_auth_timeout_s):
            message = await read_message(socket)
        token = message.get("token") if message and message.get("type") == "auth" else None
        expected = service.preview_tokens.get(run_id, "")
        valid = isinstance(token, str) and len(token) <= 256 and bool(expected)
        if not valid or not hmac.compare_digest(str(token).encode(), expected.encode()):
            await socket.close(code=4401, reason="Preview authentication required.")
            return
    except TimeoutError:
        await socket.close(code=4401, reason="Preview authentication timed out.")
        return
    except WebSocketDisconnect:
        return
    hub = service.preview_hubs[run_id]
    send_lock = asyncio.Lock()
    last_ping = monotonic()

    async def send(message: Message | dict[str, str]) -> None:
        async with asyncio.timeout(2):
            async with send_lock:
                if isinstance(message, Frame):
                    await socket.send_bytes(message.packet())
                else:
                    await socket.send_json(
                        message.json() if isinstance(message, Status) else message
                    )

    async def sender(queue: asyncio.Queue[Message]) -> None:
        if hub.latest:
            await send(hub.latest)
        last_status = hub.status
        await send(last_status)
        if last_status.status == "ended":
            return
        while True:
            item = await queue.get()
            if isinstance(item, Status) and item.status == "ended":
                # Even queue=1 must deliver the last image before ended.
                if hub.latest:
                    await send(hub.latest)
                await send(item)
                return
            if isinstance(item, Frame) and hub.status != last_status:
                if hub.status.status == "ended":
                    await send(hub.latest or item)
                    await send(hub.status)
                    return
                last_status = hub.status
                await send(last_status)
            elif isinstance(item, Status):
                last_status = item
            await send(item)

    async def receiver() -> None:
        nonlocal last_ping
        while True:
            message = await read_message(socket)
            if message and message.get("type") == "ping":
                last_ping = monotonic()
                await send({"type": "pong"})
            # Input, extra auth and all other messages are ignored, never logged or forwarded.

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL_S)
            if monotonic() - last_ping > 2 * PING_INTERVAL_S:
                await socket.close(code=4408, reason="Preview heartbeat timed out.")
                return
            await send({"type": "ping"})

    tasks: list[asyncio.Task[None]] = []
    try:
        async with hub.subscribe() as queue:
            tasks = [
                asyncio.create_task(sender(queue)),
                asyncio.create_task(receiver()),
                asyncio.create_task(heartbeat()),
            ]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (WebSocketDisconnect, RuntimeError, TimeoutError, OSError):
        pass
    finally:
        # ASGI cancellation can repeat; finish releasing sockets/sessions before propagating it.
        with anyio.CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            with suppress(RuntimeError, WebSocketDisconnect, OSError):
                await socket.close(code=1000)
