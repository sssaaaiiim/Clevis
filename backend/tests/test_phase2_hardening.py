"""Audit regressions: terminal checkpoint privacy and authenticated browser approvals."""

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.graph import agent_graph, checkpointer
from app.core.events import Action, Target
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import ActionResult, Element, Observation
from app.main import create_app
from tests.settings import PolicySettings
from tests.test_runner import Harness

PAGE_CANARY = "PRIVATE-PAGE-AUDIT-7312"
TYPE_CANARY = "TYPED-AUDIT-9248"


@pytest.mark.parametrize("ending", ["finished", "failed", "stopped"])
async def test_terminal_checkpoints_remove_page_content_and_action_values(ending: str) -> None:
    ready = asyncio.Event()

    class PrivatePage(FakeBrowserDriver):
        async def observe(self) -> Observation:
            return Observation(
                title=PAGE_CANARY,
                text_excerpt=PAGE_CANARY,
                elements=[Element(ref="field", name=PAGE_CANARY, tag="input", role="textbox")],
            )

        async def act(self, action: Action) -> ActionResult:
            if action.action == "type":
                if ending == "failed":
                    raise RuntimeError("simulated failure")
                if ending == "stopped":
                    ready.set()
                    await asyncio.sleep(10)
            return await super().act(action)

    h = Harness(
        driver=PrivatePage(delay=0),
        llm=FakeLLMClient(actions=[
            Action(action="type", target=Target(ref="field"), value=TYPE_CANARY,
                   rationale="Fill the field."),
            Action(action="done", value="Complete", rationale="Finish."),
        ], delay=0),
    )
    await h.start()
    if ending == "stopped":
        await asyncio.wait_for(ready.wait(), 2)
        h.task.cancel()
    await asyncio.wait_for(h.task, 3)
    assert (await h.store.get(h.run_id)).status == ending
    saved = [s async for s in checkpointer.alist({"configurable": {"thread_id": h.run_id}})]
    assert saved
    assert PAGE_CANARY not in repr(saved)
    assert TYPE_CANARY not in repr(saved)
    snapshot = await agent_graph.aget_state({"configurable": {"thread_id": h.run_id}})
    assert not snapshot.next and not snapshot.interrupts
    assert snapshot.values["status"] == ending


async def test_approval_timeout_erases_interrupt_history() -> None:
    from tests.test_approval_api import application

    app = application(timeout=1)
    async with app.router.lifespan_context(app):
        run = await app.state.service.create("Check timeout", "headless")
        await asyncio.wait_for(app.state.service.tasks[run.runId], 2)
        snapshot = await agent_graph.aget_state({"configurable": {"thread_id": run.runId}})
        assert snapshot.values["status"] == "failed"
        assert not snapshot.next and not snapshot.interrupts
        assert snapshot.values["pending_approval_id"] is None
        assert snapshot.values["pending_approval"] is None
        history = [
            s async for s in checkpointer.alist({"configurable": {"thread_id": run.runId}})
        ]
        assert len(history) == 1
        assert all("__interrupt__" not in repr(s.pending_writes) for s in history)
        assert not app.state.service.tasks


async def test_invalid_permission_response_never_echoes_user_domain() -> None:
    app = create_app(PolicySettings())
    canary = "https://private-domain-audit.invalid/path"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/runs", json={
            "goal": "Read", "mode": "headless", "permissions": {"allowed_domains": [canary]},
        })
    assert response.status_code == 422
    assert canary not in response.text
    assert set(json.loads(response.text)) == {"error"}
