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
            assert first.receive_json() == {
                "type": "state",
                "accepting": False,
                "controller": True,
                "limits": {"maxTextLength": 2000, "maxMessageBytes": 8192},
            }
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


def test_rate_limited_input_and_oversize_rejects() -> None:
    import time
    from typing import cast

    from app.core.events import Action
    from app.core.state import RunStatus
    from app.fakes.fake_driver import FakeBrowserDriver
    from app.fakes.fake_llm import FakeLLMClient
    from app.main import create_app
    from app.preview.input_protocol import Input
    from app.runtime import RunService
    from tests.settings import IsolatedSettings
    from tests.test_takeover_state import wait_status

    class CountingRelay:
        count = 0

        async def send(self, message: Input) -> bool:
            self.count += 1
            return True

        async def close(self) -> None:
            pass

    relay = CountingRelay()
    application = create_app(
        IsolatedSettings(input_max_messages_per_second=2),
        driver_factory=lambda: FakeBrowserDriver(delay=0),
        llm_factory=lambda: FakeLLMClient(
            actions=[Action(action="handoff", rationale="Need help.")], delay=0
        ),
    )
    with TestClient(application) as client:
        a = client.post("/api/runs", json={"goal": "Demo", "mode": "headless"}).json()
        service = cast(RunService, application.state.service)
        assert client.portal
        client.portal.call(wait_status, service, a["runId"], RunStatus.PAUSED)
        control = service.controls[a["runId"]]
        control.relay = relay
        with client.websocket_connect(
            f"/api/runs/{a['runId']}/input", headers={"origin": ORIGIN}
        ) as ws:
            ws.send_json({"type": "auth", "token": a["controlToken"]})
            assert ws.receive_json()["accepting"]
            for _ in range(10):
                ws.send_json({"type": "text", "value": "fake text"})
            time.sleep(1.1)
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
            assert relay.count == 2 and control.counters.rate_limited == 8
            # A UTF-8 oversize frame is rejected without touching the relay.
            ws.send_json({"type": "text", "value": "非" * 4000})
            time.sleep(1.1)
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}
            assert control.counters.rejected == 1 and relay.count == 2
