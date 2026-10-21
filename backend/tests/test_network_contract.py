"""Exercise the public contract over real loopback HTTP/WebSocket connections."""

import asyncio
import json
import socket
from time import monotonic

import uvicorn
from httpx import AsyncClient
from websockets.asyncio.client import connect

from app.core.events import Action
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.main import create_app
from tests.settings import IsolatedSettings


async def test_real_server_routes_sse_keepalive_and_websockets() -> None:
    application = create_app(
        IsolatedSettings(),
        driver_factory=lambda: FakeBrowserDriver(delay=0.02),
        llm_factory=lambda: FakeLLMClient(
            actions=[
                Action(action="handoff", value="Please check the page", rationale="Need help."),
                Action(action="done", value="Verified", rationale="Finished."),
            ],
            delay=0.02,
        ),
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(application, log_config=None, access_log=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    summary: dict[str, object] = {}
    try:
        async with asyncio.timeout(5):
            for _ in range(500):
                if server.started:
                    break
                await asyncio.sleep(0.01)
        async with AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=25) as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            created = await client.post(
                "/api/runs", json={"goal": "Verify demo", "mode": "headless"}
            )
            assert created.status_code == 201
            body = created.json()
            run_id = body["runId"]
            assert body["controlToken"] != body["previewToken"]
            async with asyncio.timeout(3):
                for _ in range(300):
                    if (await client.get(f"/api/runs/{run_id}")).json()["status"] == "paused":
                        break
                    await asyncio.sleep(0.01)
            assert (await client.post(f"/api/runs/{run_id}/takeover")).status_code == 409
            origin = application.state.service.settings.frontend_origin
            ws_base = f"ws://127.0.0.1:{port}/api/runs/{run_id}"
            async with connect(ws_base + "/preview", origin=origin) as preview:
                await preview.send(json.dumps({"type": "auth", "token": body["previewToken"]}))
                async with asyncio.timeout(3):
                    while not isinstance(frame := await preview.recv(), bytes):
                        pass
                assert isinstance(frame, bytes)
                size = int.from_bytes(frame[:4], "big")
                assert json.loads(frame[4 : 4 + size])["format"] == "jpeg"
                assert frame[4 + size :][:2] == b"\xff\xd8"
            async with connect(ws_base + "/input", origin=origin) as control:
                await control.send(json.dumps({"type": "auth", "token": body["controlToken"]}))
                state = json.loads(await control.recv())
                assert state["accepting"] and state["controller"]
                await control.send('{"type":"ping"}')
                assert json.loads(await control.recv()) == {"type": "pong"}
            started = monotonic()
            async with client.stream("GET", f"/api/runs/{run_id}/events") as stream:
                assert stream.status_code == 200
                async for line in stream.aiter_lines():
                    if line.startswith(": keep-alive"):
                        summary["keepaliveSeconds"] = round(monotonic() - started, 3)
                        break
            assert 14 <= float(str(summary["keepaliveSeconds"])) <= 20
            assert (await client.post(f"/api/runs/{run_id}/resume")).status_code == 200
            stream = await client.get(f"/api/runs/{run_id}/events")
            events = [
                json.loads(line[5:])
                for line in stream.text.splitlines()
                if line.startswith("data:")
            ]
            assert events[-1]["type"] == "run.finished"
            assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
            for cursor, headers in (("", {"Last-Event-ID": "2"}), ("?after=2", {})):
                replay = await client.get(f"/api/runs/{run_id}/events{cursor}", headers=headers)
                assert [
                    json.loads(s[5:])["seq"]
                    for s in replay.text.splitlines()
                    if s.startswith("data:")
                ] == list(range(3, len(events) + 1))
            assert (await client.post(f"/api/runs/{run_id}/stop")).status_code == 409
            second = (
                await client.post("/api/runs", json={"goal": "Stop", "mode": "headless"})
            ).json()["runId"]
            async with asyncio.timeout(3):
                for _ in range(300):
                    if (await client.get(f"/api/runs/{second}")).json()["status"] == "paused":
                        break
                    await asyncio.sleep(0.01)
            assert (await client.post(f"/api/runs/{second}/resume")).status_code == 200
            # User takeover is tested on another slowly-started run in test_api; here race it
            # immediately after resume, before the fake actor can finish.
            assert (await client.post(f"/api/runs/{second}/takeover")).status_code == 200
            assert (await client.post(f"/api/runs/{second}/takeover")).status_code == 200
            start = monotonic()
            assert (await client.post(f"/api/runs/{second}/stop")).status_code == 200
            summary["stopPausedSeconds"] = round(monotonic() - start, 4)
            assert (await client.post(f"/api/runs/{second}/stop")).status_code == 200
            assert (await client.get("/api/runs/missing")).status_code == 404
            assert (await client.post("/api/runs", json={})).status_code == 422
            summary.update(
                {
                    "health": 200,
                    "create": 201,
                    "get": 200,
                    "events": 200,
                    "resume": 200,
                    "takeover": 200,
                    "stop": 200,
                    "repeatStop": 200,
                    "terminalConflict": 409,
                    "unknown": 404,
                    "invalid": 422,
                    "preview": "authenticated JPEG",
                    "input": "authenticated state + pong",
                    "replay": "header and query",
                    "terminal": events[-1]["type"],
                }
            )
            print("NETWORK_CONTRACT " + json.dumps(summary, sort_keys=True))
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        listener.close()
