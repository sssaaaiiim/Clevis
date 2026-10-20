import json
import logging
from typing import TypeVar, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.agent.prompts import actor_messages
from app.agent.state import AgentState
from app.browser.input_privacy import InputPrivacy
from app.core.events import Action
from app.core.state import RunStatus
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import Element, Observation
from app.interfaces.llm import LLMResponse, Message
from app.main import create_app
from app.preview.input_protocol import Input, Text
from app.runtime import RunService
from tests.settings import IsolatedSettings
from tests.test_preview_ws import ORIGIN
from tests.test_takeover_state import wait_status

T = TypeVar("T", bound=BaseModel)

CANARY = "CANARY-PASSWORD-9137"


def test_fingerprint_split_typing_and_no_plaintext_history() -> None:
    guard = InputPrivacy()
    for char in CANARY:
        guard.remember(char)
    assert CANARY not in guard.scrub("Welcome " + CANARY)
    observation = Observation(
        text_excerpt="Echo " + CANARY,
        elements=[
            Element(
                ref="e1",
                role="textbox",
                name="Username",
                tag="input",
                value="untracked-headed-value",
            )
        ],
    )
    safe = guard.observation(observation)
    messages = actor_messages(AgentState(goal="Read the result"), safe, 5)
    assert CANARY not in json.dumps([m.model_dump() for m in messages])
    assert safe.elements[0].value == "[redacted]"
    assert CANARY not in str(vars(guard))


class EchoDriver(FakeBrowserDriver):
    echo = False

    async def observe(self) -> Observation:
        return Observation(title="Result", text_excerpt="Echo " + CANARY if self.echo else "Ready")


class RecordingLLM(FakeLLMClient):
    def __init__(self) -> None:
        super().__init__(
            actions=[
                Action(action="handoff", value="Please sign in", rationale="Need help."),
                Action(action="done", value="Welcome", rationale="Finish."),
            ],
            delay=0.01,
        )
        self.bodies: list[str] = []

    async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
        self.bodies.append(json.dumps([m.model_dump() for m in messages]))
        return await super().propose(messages, schema)


class PrivateRelay:
    def __init__(self, driver: EchoDriver) -> None:
        self.driver = driver

    async def send(self, message: Input) -> bool:
        if isinstance(message, Text):
            self.driver.echo = True
            raise RuntimeError(message.value)  # Raw driver failure must not escape input transport.
        return True

    async def close(self) -> None:
        pass


def test_websocket_canary_never_reaches_public_channels(caplog: pytest.LogCaptureFixture) -> None:
    llm = RecordingLLM()
    driver = EchoDriver(delay=0.01)
    application = create_app(
        IsolatedSettings(), driver_factory=lambda: driver, llm_factory=lambda: llm
    )
    with TestClient(application) as client:
        a = client.post("/api/runs", json={"goal": "Read the result", "mode": "headless"}).json()
        service = cast(RunService, application.state.service)
        assert client.portal
        client.portal.call(wait_status, service, a["runId"], RunStatus.PAUSED)
        # The fake page starts echoing the canary only after human input.
        service.controls[a["runId"]].relay = PrivateRelay(driver)
        caplog.set_level(logging.DEBUG)
        with client.websocket_connect(
            f"/api/runs/{a['runId']}/input", headers={"origin": ORIGIN}
        ) as ws:
            ws.send_json({"type": "auth", "token": a["controlToken"]})
            assert ws.receive_json()["accepting"]
            ws.send_json({"type": "text", "value": CANARY})
            assert ws.receive_json() == {"type": "error", "code": "INPUT_UNAVAILABLE"}
            assert client.post(f"/api/runs/{a['runId']}/resume").status_code == 200
        client.portal.call(wait_status, service, a["runId"], RunStatus.FINISHED)
        events = client.get(f"/api/runs/{a['runId']}/events").text
        record = client.get(f"/api/runs/{a['runId']}").text
        assert CANARY not in events + record + str(
            client.portal.call(service.store.list_events, a["runId"])
        )
        assert CANARY not in "".join(llm.bodies)
        assert CANARY not in caplog.text
