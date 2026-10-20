import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.test_preview_ws import ORIGIN, app


@pytest.mark.parametrize("token", ["wrong", None, "preview", "other"])
def test_auth_rejects(token: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.ws.AUTH_TIMEOUT_S", 0.03)
    with TestClient(app()) as client:
        a = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        b = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        with client.websocket_connect(
            f"/api/runs/{a['runId']}/input", headers={"origin": ORIGIN}
        ) as ws:
            if token is not None:
                value = (
                    a["previewToken"]
                    if token == "preview"
                    else b["controlToken"]
                    if token == "other"
                    else token
                )
                ws.send_json({"type": "auth", "token": value})
            with pytest.raises(WebSocketDisconnect) as error:
                ws.receive_json()
            assert error.value.code == 4401


@pytest.mark.parametrize(
    "origin,run,code", [(None, True, 4403), ("https://wrong", True, 4403), (ORIGIN, False, 4404)]
)
def test_origin_unknown(origin: str | None, run: bool, code: int) -> None:
    with TestClient(app()) as client:
        created = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        path = f"/api/runs/{created['runId'] if run else 'missing'}/input"
        with client.websocket_connect(path, headers={"origin": origin} if origin else {}) as ws:
            with pytest.raises(WebSocketDisconnect) as error:
                ws.receive_json()
            assert error.value.code == code


def test_single_controller_and_nonaccepting_and_disconnect() -> None:
    with TestClient(app()) as client:
        a = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        path = f"/api/runs/{a['runId']}/input"

        def auth(ws: object) -> None:
            ws.send_json({"type": "auth", "token": a["controlToken"]})  # type: ignore[attr-defined]

        with client.websocket_connect(path, headers={"origin": ORIGIN}) as first:
            auth(first)
            assert first.receive_json() == {"type": "state", "accepting": False, "controller": True}
            with client.websocket_connect(path, headers={"origin": ORIGIN}) as second:
                auth(second)
                with pytest.raises(WebSocketDisconnect) as error:
                    second.receive_json()
                assert error.value.code == 4409
            first.send_json({"type": "text", "value": "PRIVATE"})
            assert first.receive_json()["accepting"] is False
            first.send_json({"type": "ping"})
            assert first.receive_json() == {"type": "pong"}
        with client.websocket_connect(path, headers={"origin": ORIGIN}) as third:
            auth(third)
            assert third.receive_json()["controller"]
            for _ in range(50):
                third.send_json({"type": "bad"})
            with pytest.raises(WebSocketDisconnect) as error:
                third.receive_json()
            assert error.value.code == 4400
