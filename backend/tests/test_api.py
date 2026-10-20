import asyncio
from collections.abc import AsyncIterator
from time import monotonic
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from starlette.types import Message, Scope
from starlette.websockets import WebSocketDisconnect

from app.core.events import EVENT_ADAPTER, Event
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.main import create_app
from app.runtime import RunService
from tests.settings import IsolatedSettings


@pytest.fixture
def application() -> FastAPI:
    return create_app(
        IsolatedSettings(),
        driver_factory=lambda: FakeBrowserDriver(delay=0.02),
        llm_factory=lambda: FakeLLMClient(delay=0.01),
    )


@pytest.fixture
async def client(application: FastAPI) -> AsyncIterator[AsyncClient]:
    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as c:
            yield c


def parse_events(text: str) -> list[Event]:
    return [
        EVENT_ADAPTER.validate_json(line[5:].strip())
        for line in text.splitlines()
        if line.startswith("data:")
    ]


async def create(client: AsyncClient) -> str:
    response = await client.post("/api/runs", json={"goal": "Find result", "mode": "headless"})
    assert response.status_code == 201
    return cast(str, response.json()["runId"])


async def test_create_state_stream_and_replay(client: AsyncClient, application: FastAPI) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}
    run_id = await create(client)
    response = await client.get(f"/api/runs/{run_id}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_events(response.text)
    assert events[0].type == "run.started"
    assert events[1].type == "plan.created"
    assert events[-1].type == "run.finished"
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    for event in events:
        assert f"id: {event.seq}" in response.text
        assert f"event: {event.type}" in response.text
    state = (await client.get(f"/api/runs/{run_id}")).json()
    assert set(state) == {"runId", "status", "goal", "mode", "result", "error", "createdAt"}
    assert state["status"] == "finished" and state["result"] and state["error"] is None
    replay = await client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "3"})
    assert parse_events(replay.text) == events[3:]
    query = await client.get(f"/api/runs/{run_id}/events?after=5", headers={"Last-Event-ID": "3"})
    assert parse_events(query.text) == events[5:]
    empty = await client.get(f"/api/runs/{run_id}/events?after={events[-1].seq}")
    assert empty.text == ""
    for suffix in ("stop", "takeover", "resume"):
        conflict = await client.post(f"/api/runs/{run_id}/{suffix}")
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "invalid_transition"
    service = cast(RunService, application.state.service)
    assert service.emitter.subscriber_count == 0


async def test_validation_errors_and_404s(client: AsyncClient) -> None:
    for body in (
        {},
        {"goal": "", "mode": "headless"},
        {"goal": " ", "mode": "headless"},
        {"goal": "x" * 2001, "mode": "headless"},
        {"goal": "x", "mode": "other"},
        {"goal": "x", "mode": "headless", "maxSteps": 10},
    ):
        response = await client.post("/api/runs", json=body)
        assert response.status_code == 422
        assert response.json() == {
            "error": {
                "code": "validation_error",
                "message": "Request validation failed.",
            }
        }
    for suffix, method in (
        ("", "GET"),
        ("/events", "GET"),
        ("/stop", "POST"),
        ("/takeover", "POST"),
        ("/resume", "POST"),
    ):
        response = await client.request(method, f"/api/runs/missing{suffix}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "run_not_found"
    assert (await client.get("/missing")).json()["error"]["code"] == "http_404"
    run_id = await create(client)
    for cursor in ("nope", "-1"):
        response = await client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": cursor})
        assert response.status_code == 400
        assert set(response.json()["error"]) == {"code", "message"}
    assert (await client.get(f"/api/runs/{run_id}/events?after=-1")).status_code == 422


async def test_stop_is_fast_and_idempotent() -> None:
    application = create_app(IsolatedSettings(), driver_factory=lambda: FakeBrowserDriver(delay=5))
    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as c:
            run_id = await create(c)
            start = monotonic()
            response = await c.post(f"/api/runs/{run_id}/stop")
            assert response.status_code == 200
            assert response.json()["status"] == "stopped"
            assert monotonic() - start < 2
            assert (await c.post(f"/api/runs/{run_id}/stop")).status_code == 200
            assert (await c.get(f"/api/runs/{run_id}")).json()["status"] == "stopped"
            events = parse_events((await c.get(f"/api/runs/{run_id}/events")).text)
            assert events[-1].type == "run.stopped"
            assert sum(e.type == "run.stopped" for e in events) == 1


async def test_takeover_resume(client: AsyncClient, application: FastAPI) -> None:
    run_id = await create(client)
    service = cast(RunService, application.state.service)
    async with service.emitter.subscribe(run_id) as sub:
        async with asyncio.timeout(2):
            while (await sub.queue.get()).type != "step.proposed":
                pass
    paused = await client.post(f"/api/runs/{run_id}/takeover")
    assert paused.status_code == 200 and paused.json()["status"] == "paused"
    before = await service.store.list_events(run_id)
    assert before[-1].type == "run.paused"
    assert before[-1].data.model_dump() == {"reason": "takeover"}
    await asyncio.sleep(0.1)
    assert await service.store.list_events(run_id) == before
    assert (await client.post(f"/api/runs/{run_id}/takeover")).status_code == 409
    assert (await client.post(f"/api/runs/{run_id}/resume")).json()["status"] == "running"
    events = parse_events((await client.get(f"/api/runs/{run_id}/events")).text)
    assert any(e.type == "run.resumed" for e in events)
    assert events[-1].type == "run.finished"


async def test_cors(client: AsyncClient) -> None:
    allowed = await client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = await client.get("/health", headers={"Origin": "http://untrusted.test"})
    assert "access-control-allow-origin" not in denied.headers
    preflight = await client.options(
        "/api/runs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type,Last-Event-ID",
        },
    )
    assert preflight.status_code == 200
    denied_preflight = await client.options(
        "/api/runs",
        headers={
            "Origin": "http://untrusted.test",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert denied_preflight.status_code == 400
    assert set(denied_preflight.json()["error"]) == {"code", "message"}


async def test_disconnect_cleans_sse_subscription(
    client: AsyncClient, application: FastAPI
) -> None:
    run_id = await create(client)
    disconnected = asyncio.Event()
    requested = False

    async def receive() -> Message:
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and b"data:" in message.get("body", b""):
            disconnected.set()

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": f"/api/runs/{run_id}/events",
        "raw_path": b"/",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "server": ("test", 80),
        "client": ("test", 123),
    }
    await asyncio.wait_for(application(scope, receive, send), 2)
    service = cast(RunService, application.state.service)
    assert disconnected.is_set()
    assert service.emitter.subscriber_count == 0


def test_websocket_stubs(application: FastAPI) -> None:
    with TestClient(application) as client:
        run_id = client.post("/api/runs", json={"goal": "test", "mode": "headless"}).json()["runId"]
        for channel in ("preview", "input"):
            for identifier, code in ((run_id, 1000), ("missing", 4404)):
                with client.websocket_connect(f"/api/runs/{identifier}/{channel}") as socket:
                    with pytest.raises(WebSocketDisconnect) as exc:
                        socket.receive_text()
                    assert exc.value.code == code


async def test_shutdown_stops_and_drains_tasks() -> None:
    application = create_app(IsolatedSettings(), driver_factory=lambda: FakeBrowserDriver(delay=10))
    service = cast(RunService, application.state.service)
    async with application.router.lifespan_context(application):
        run = await service.create("test", "headless")
        await asyncio.sleep(0)
    assert not service.tasks
    assert (await service.store.get(run.runId)).status == "stopped"
    assert (await service.store.list_events(run.runId))[-1].type == "run.stopped"


async def test_openrouter_missing_config_is_rejected() -> None:
    application = create_app(
        IsolatedSettings(
            llm_provider="openrouter", llm_model_primary="", openrouter_api_key=SecretStr("")
        )
    )
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY and LLM_MODEL_PRIMARY"):
        async with application.router.lifespan_context(application):
            pass


async def test_resume_during_planning_is_conflict() -> None:
    application = create_app(IsolatedSettings(), driver_factory=lambda: FakeBrowserDriver(delay=5))
    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as c:
            run_id = await create(c)
            response = await c.post(f"/api/runs/{run_id}/resume")
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "invalid_transition"


async def test_sse_keepalive_configuration(application: FastAPI) -> None:
    from app.api.runs import events

    service = cast(RunService, application.state.service)
    run = await service.store.create("test", "headless")
    response = await events(run.runId, service, after=0, last_event_id=None)
    assert response.ping_interval == 15
    assert response.ping_message_factory is not None
    assert b": keep-alive" in response.ping_message_factory().encode()


async def test_structured_run_logs_exclude_goal_and_token_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json

    application = create_app(
        IsolatedSettings(),
        driver_factory=lambda: FakeBrowserDriver(delay=0),
        llm_factory=lambda: FakeLLMClient(delay=0),
    )
    service = cast(RunService, application.state.service)
    async with application.router.lifespan_context(application):
        run = await service.create("private goal text " * 30, "headless")
        await asyncio.gather(*list(service.tasks.values()))
    output = capsys.readouterr().err
    records = [json.loads(line) for line in output.splitlines()]
    assert records and all(record["runId"] == run.runId for record in records)
    assert "private goal" not in output and "tokens" not in output.lower()
