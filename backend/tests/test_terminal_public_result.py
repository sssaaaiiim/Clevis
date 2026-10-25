"""Terminal cleanup preserves the already-sanitized public answer, never secret values."""

import pytest

from app.agent.graph import agent_graph
from app.core.events import Action, Target
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import ActionResult, Element, Observation
from tests.test_runner import Harness


@pytest.mark.parametrize("field_type", ["text", "password"])
async def test_terminal_summary_preserves_only_intentionally_public_result(field_type: str) -> None:
    public_value = "demo-user"

    class EchoField(FakeBrowserDriver):
        filled = False

        async def observe(self) -> Observation:
            return Observation(elements=[Element(
                ref="field", role="textbox", tag="input", name="Demo field", type=field_type,
                value=public_value if self.filled else None,
            )])

        async def act(self, action: Action) -> ActionResult:
            self.filled = True
            return await super().act(action)

    h = Harness(driver=EchoField(delay=0), llm=FakeLLMClient(actions=[
        Action(action="type", target=Target(ref="field"), value=public_value,
               rationale="Fill demo field."),
        Action(action="done", value="Welcome, " + public_value, rationale="Report result."),
    ], delay=0))
    await h.start()
    await h.task
    record = await h.store.get(h.run_id)
    assert record.status == "finished" and record.result is not None
    assert (public_value in record.result) == (field_type == "text")
    snapshot = await agent_graph.aget_state({"configurable": {"thread_id": h.run_id}})
    assert snapshot.values["result"] == record.result
    assert snapshot.values["last_observation"] is None
    assert snapshot.values["last_action"] is None
