import asyncio
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.main import create_app
from app.preview.framing import decode_frame
from app.runtime import RunService
from tests.settings import IsolatedSettings
from tests.test_preview_hub import frame

ORIGIN = "http://localhost:5173"


def app(timeout: float = 0.05, driver_delay: float = 10) -> FastAPI:
    return create_app(
        IsolatedSettings(preview_auth_timeout_s=timeout),
        driver_factory=lambda: FakeBrowserDriver(delay=driver_delay),
        llm_factory=lambda: FakeLLMClient(delay=0.2),
    )


@pytest.mark.parametrize("token", ["wrong", None, "你好"])
def test_bad_or_missing_auth(token: str | None) -> None:
    application = app()
    with TestClient(application) as client:
        created = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        with client.websocket_connect(
            f"/api/runs/{created['runId']}/preview", headers={"origin": ORIGIN}
        ) as socket:
            if token is not None:
                socket.send_json({"type": "auth", "token": token})
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_text()
            assert error.value.code == 4401


@pytest.mark.parametrize("origin", [None, "https://wrong.example"])
def test_origin_and_unknown_run(origin: str | None) -> None:
    application = app()
    with TestClient(application) as client:
        run_id = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()["runId"]
        headers = {"origin": origin} if origin else {}
        for identifier, code in [(run_id, 4403), ("missing", 4404)]:
            with client.websocket_connect(
                f"/api/runs/{identifier}/preview", headers=headers
            ) as socket:
                with pytest.raises(WebSocketDisconnect) as error:
                    socket.receive_text()
                assert error.value.code == code


def test_valid_token_frames_ping_and_cleanup() -> None:
    application = app()
    with TestClient(application) as client:
        created = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        service = cast(RunService, application.state.service)
        run_id, token = created["runId"], created["previewToken"]
        assert len(token) >= 40
        assert token not in client.get(f"/api/runs/{run_id}").text
        assert client.portal
        client.portal.call(service.preview_hubs[run_id].publish, frame())
        with client.websocket_connect(
            f"/api/runs/{run_id}/preview", headers={"origin": ORIGIN}
        ) as socket:
            socket.send_json({"type": "auth", "token": token})
            data = socket.receive_bytes()
            metadata, image = decode_frame(data)
            assert image.startswith(b"\xff\xd8") and metadata["width"] == 1280
            assert socket.receive_json()["status"] == "live"
            socket.send_json({"type": "input", "text": "ignored-demo-input"})
            socket.send_json({"type": "ping"})
            assert socket.receive_json()["type"] == "pong"
        assert not service.preview_hubs[run_id].viewers
        assert token not in str(client.portal.call(service.store.list_events, run_id))


def test_token_is_bound_to_run() -> None:
    application = app()
    with TestClient(application) as client:
        first = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        second = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        with client.websocket_connect(
            f"/api/runs/{second['runId']}/preview", headers={"origin": ORIGIN}
        ) as socket:
            socket.send_json({"type": "auth", "token": first["previewToken"]})
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_text()
            assert error.value.code == 4401


def test_late_viewer_gets_retained_frame_before_ended() -> None:
    application = app()
    with TestClient(application) as client:
        created = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        service = cast(RunService, application.state.service)
        assert client.portal
        hub = service.preview_hubs[created["runId"]]
        client.portal.call(hub.publish, frame())
        client.post(f"/api/runs/{created['runId']}/stop")
        with client.websocket_connect(
            f"/api/runs/{created['runId']}/preview", headers={"origin": ORIGIN}
        ) as socket:
            socket.send_json({"type": "auth", "token": created["previewToken"]})
            assert decode_frame(socket.receive_bytes())[0]["seq"] == 1
            assert socket.receive_json()["status"] == "ended"


async def test_preview_lifecycle_privacy_and_shutdown() -> None:
    application = app(driver_delay=0.01)
    service = cast(RunService, application.state.service)
    async with application.router.lifespan_context(application):
        run = await service.create("Demo", "headless")
        task = service.tasks[run.runId]
        service.preview_hubs[run.runId].publish(frame())
        await asyncio.wait_for(task, 5)
        assert service.preview_hubs[run.runId].status.status == "ended"
        assert service.preview_hubs[run.runId].latest
        assert "test-image" not in str(await service.store.list_events(run.runId))
        assert "test-image" not in (await service.store.get(run.runId)).model_dump_json()
    assert service.preview_hubs[run.runId].latest is None
    assert not service.preview_tokens


def test_single_slot_queue_keeps_status_and_final_frame() -> None:
    application = create_app(
        IsolatedSettings(preview_client_queue=1), driver_factory=lambda: FakeBrowserDriver(delay=10)
    )
    with TestClient(application) as client:
        created = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        service = cast(RunService, application.state.service)
        assert client.portal
        hub = service.preview_hubs[created["runId"]]
        with client.websocket_connect(
            f"/api/runs/{created['runId']}/preview", headers={"origin": ORIGIN}
        ) as socket:
            socket.send_json({"type": "auth", "token": created["previewToken"]})
            assert socket.receive_json()["status"] == "waiting"
            client.portal.call(hub.publish, frame())
            assert socket.receive_json()["status"] == "live"
            assert decode_frame(socket.receive_bytes())[0]["seq"] == 1
            client.post(f"/api/runs/{created['runId']}/stop")
            assert decode_frame(socket.receive_bytes())[0]["seq"] == 1
            assert socket.receive_json()["status"] == "ended"


def test_server_heartbeat_and_dead_viewer_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.preview.PING_INTERVAL_S", 0.03)
    application = app()
    with TestClient(application) as client:
        created = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        with client.websocket_connect(
            f"/api/runs/{created['runId']}/preview", headers={"origin": ORIGIN}
        ) as socket:
            socket.send_json({"type": "auth", "token": created["previewToken"]})
            assert socket.receive_json()["status"] == "waiting"
            assert socket.receive_json()["type"] == "ping"
            with pytest.raises(WebSocketDisconnect) as error:
                while True:
                    socket.receive_text()
            assert error.value.code == 4408
        service = cast(RunService, application.state.service)
        assert not service.preview_hubs[created["runId"]].viewers


def test_repeated_viewer_disconnects_complete_cleanup() -> None:
    application = app()
    with TestClient(application) as client:
        created = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        service = cast(RunService, application.state.service)
        for _ in range(20):
            with client.websocket_connect(
                f"/api/runs/{created['runId']}/preview", headers={"origin": ORIGIN}
            ) as socket:
                socket.send_json({"type": "auth", "token": created["previewToken"]})
                assert socket.receive_json()["type"] == "status"
            assert not service.preview_hubs[created["runId"]].viewers
