"""Public approval/permission/auth contracts over real loopback sockets."""

import asyncio
import json
import socket
from uuid import uuid4

import pytest
import uvicorn
from httpx import AsyncClient
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.agent.graph import agent_graph
from tests.test_approval_api import application


async def test_real_http_approval_permissions_and_websocket_rejections() -> None:
    app = application()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, access_log=False))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    statuses: dict[str, int | bool] = {}
    origin = app.state.service.settings.frontend_origin

    async def closed(path: str, expected: int, *, bad_auth: bool = False) -> None:
        async with connect(f"ws://127.0.0.1:{port}" + path, origin=origin) as ws:
            if bad_auth:
                await ws.send('{"type":"auth","token":"deliberately-invalid-test-token"}')
            with pytest.raises(ConnectionClosed) as error:
                await ws.recv()
            assert error.value.rcvd is not None
            assert error.value.rcvd.code == expected

    try:
        async with asyncio.timeout(5):
            for _ in range(500):
                if server.started:
                    break
                await asyncio.sleep(0.01)
        async with AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            for decision in ("approve", "deny"):
                created = await client.post("/api/runs", json={
                    "goal": "Verify the public approval contract", "mode": "headless",
                    "permissions": {"allowed_domains": ["localhost"], "max_steps": 5},
                })
                assert created.status_code == 201
                data = created.json()
                run_id = data["runId"]
                async with asyncio.timeout(3):
                    while True:
                        snapshot = await agent_graph.aget_state(
                            {"configurable": {"thread_id": run_id}}
                        )
                        if snapshot.interrupts:
                            break
                        await asyncio.sleep(0.005)
                approval_id = snapshot.values["pending_approval_id"]
                state = await client.get(f"/api/runs/{run_id}")
                assert state.status_code == 200
                effective = state.json()["permissions"]
                assert effective["allowed_domains"] == ["localhost"]
                assert effective["max_steps"] == 5
                assert effective["max_cost_usd"] is not None
                statuses["effective_permissions"] = True
                path = f"/api/runs/{run_id}/{decision}"
                body = {"approval_id": approval_id}
                headers = {"Authorization": "Bearer " + data["approvalToken"]}
                unauthorized = await client.post(path, json=body)
                assert unauthorized.status_code == 401
                assert set(unauthorized.json()) == {"error"}
                stale = await client.post(path, headers=headers, json={"approval_id": str(uuid4())})
                assert stale.status_code == 422
                assert (await client.get(f"/api/runs/{run_id}")).json()["status"] == "paused"
                accepted = await client.post(path, headers=headers, json=body)
                assert accepted.status_code == 200
                assert accepted.json() == {
                    "status": "approved" if decision == "approve" else "denied"
                }
                assert (await client.post(path, headers=headers, json=body)).status_code == 409
                statuses.update({decision: 200, decision + "_unauthorized": 401,
                                 decision + "_stale": 422, decision + "_duplicate": 409})
                for _ in range(300):
                    state = await client.get(f"/api/runs/{run_id}")
                    if state.json()["status"] == "finished":
                        break
                    await asyncio.sleep(0.01)
                assert state.json()["status"] == "finished"
                if decision == "approve":
                    for channel in ("preview", "input"):
                        await closed(f"/api/runs/{run_id}/{channel}", 4401, bad_auth=True)
                        await closed(f"/api/runs/{run_id}/{channel}", 4401)
                        await closed(f"/api/runs/missing/{channel}", 4404)
                        statuses[channel + "_bad_or_missing_auth"] = 4401
                        statuses[channel + "_unknown"] = 4404
            print("REAL_APPROVAL_HTTP " + json.dumps(statuses, sort_keys=True))
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, 5)
        listener.close()
