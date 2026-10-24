import asyncio
import json
import logging
from time import monotonic
from typing import Literal

import pytest

from app.agent.graph import agent_graph
from app.agent.policy.approvals import submit_approval
from app.agent.policy.validator import PolicyValidator
from app.core.events import Action, Event
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import Element, Observation
from tests.settings import IsolatedSettings
from tests.test_agent_loop import LoopRun, done


class FormDriver(FakeBrowserDriver):
    async def observe(self) -> Observation:
        return Observation(
            url="https://public.example/form",
            elements=[
                Element(
                    ref="e1",
                    tag="button",
                    role="button",
                    type="submit",
                    name="Submit",
                )
            ],
        )


async def wait_for(run: LoopRun, kind: str) -> list[Event]:
    async with asyncio.timeout(3):
        while True:
            events = await run.store.list_events(run.run_id)
            if any(event.type == kind for event in events):
                return events
            if run.task.done():
                raise AssertionError("Run ended before the expected policy event.")
            await asyncio.sleep(0.005)


@pytest.mark.parametrize("decision", ["approved", "denied"])
async def test_real_graph_approval_interrupt_and_resume(
    decision: Literal["approved", "denied"],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="clevis")
    driver = FormDriver(delay=0)
    run = LoopRun(
        FakeLLMClient(
            actions=[
                Action.model_validate(
                    {
                        "action": "click",
                        "target": {"ref": "e1"},
                        "rationale": "Submit demo.",
                    }
                ),
                done(),
            ],
            delay=0,
        ),
        driver=driver,
        validator=PolicyValidator(IsolatedSettings(), resolver=lambda _: ["8.8.8.8"]),
    )
    await run.start()
    try:
        await wait_for(run, "run.paused")
        async with asyncio.timeout(3):
            while True:
                snapshot = await agent_graph.aget_state({"configurable": {"thread_id": run.run_id}})
                if snapshot.interrupts:
                    break
                await asyncio.sleep(0.005)
        assert snapshot.next == ("approval_gate",)
        assert run.machine.pause_reason == "approval" and not driver.actions
        assert not run.task.done() and not driver.closed
        await asyncio.sleep(0.02)
        await submit_approval(run.machine, decision)
        record, events = await run.finish()
        assert record.status == "finished" and record.result == "Complete" and driver.closed
        assert [a.action for a in driver.actions] == (
            ["click", "done"] if decision == "approved" else ["done"]
        )
        assert sum(e.type == "approval.required" for e in events) == 1
        assert sum(e.type == "run.paused" for e in events) == 1
        assert sum(e.type == "run.resumed" for e in events) == 1
        assert sum(e.type == "step.validated" for e in events) == 2
        final = await agent_graph.aget_state({"configurable": {"thread_id": run.run_id}})
        assert final.values["pending_approval"] is None
        assert len(final.values["step_history"]) == 2
        assert not final.next
        assert "public.example" not in caplog.text
    finally:
        if not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)


async def test_policy_three_denials_never_act_and_have_gap_free_events() -> None:
    driver = FakeBrowserDriver(delay=0)
    run = LoopRun(
        FakeLLMClient(
            actions=[
                Action(
                    action="navigate",
                    value=f"http://127.0.0.{i}/",
                    rationale="Open page.",
                )
                for i in range(1, 4)
            ],
            delay=0,
        ),
        driver=driver,
        validator=PolicyValidator(IsolatedSettings(), resolver=lambda _: ["8.8.8.8"]),
    )
    await run.start()
    record, events = await run.finish()
    assert record.status == "failed" and record.error and "three consecutive" in record.error
    assert "SSRF" in record.error and not driver.actions and driver.closed
    assert sum(e.type == "step.validated" for e in events) == 3
    assert [e.seq for e in events] == list(range(1, len(events) + 1))


async def test_stop_during_approval_closes_resources_within_two_seconds() -> None:
    driver = FormDriver(delay=0)
    run = LoopRun(
        FakeLLMClient(
            actions=[
                Action.model_validate(
                    {
                        "action": "click",
                        "target": {"ref": "e1"},
                        "rationale": "Submit.",
                    }
                )
            ],
            delay=0,
        ),
        driver=driver,
        validator=PolicyValidator(IsolatedSettings(), resolver=lambda _: ["8.8.8.8"]),
    )
    await run.start()
    await wait_for(run, "run.paused")
    started = monotonic()
    run.task.cancel()
    await run.task
    assert monotonic() - started < 2
    assert driver.closed
    assert (await run.store.get(run.run_id)).status == "stopped"
    snapshot = await agent_graph.aget_state({"configurable": {"thread_id": run.run_id}})
    assert snapshot.values["status"] == "stopped" and not snapshot.next
    assert "value" not in json.dumps(snapshot.values["step_history"])


async def test_extraction_to_other_domain_requires_approval(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class DomainDriver(FakeBrowserDriver):
        async def observe(self) -> Observation:
            return Observation(url=self.url)

    from app.agent.policy.dataflow import content_hash

    caplog.set_level(logging.DEBUG, logger="clevis")
    value = "Sample result: Travel Mug, $12.00."
    driver = DomainDriver(delay=0)
    run = LoopRun(
        FakeLLMClient(
            actions=[
                Action(action="navigate", value="https://source.example", rationale="Open source."),
                Action(action="extract", rationale="Read data."),
                Action(
                    action="navigate", value="https://destination.example", rationale="Open target."
                ),
                Action(action="type", value=value, rationale="Fill target."),
                done(),
            ],
            delay=0,
        ),
        driver=driver,
        validator=PolicyValidator(IsolatedSettings(), resolver=lambda _: ["8.8.8.8"]),
    )
    await run.start()
    try:
        events = await wait_for(run, "approval.required")
        proposed = [e for e in events if e.type == "step.proposed"][-1]
        assert proposed.data.action == "type" and proposed.data.value == "[redacted]"
        assert all(a.action != "type" for a in driver.actions)
        snapshot = await agent_graph.aget_state({"configurable": {"thread_id": run.run_id}})
        assert snapshot.values["data_flow"][content_hash(value)]["domains"] == ["source.example"]
        assert value not in json.dumps(snapshot.values["data_flow"])
        assert value not in caplog.text and "source.example" not in caplog.text
        await wait_for(run, "run.paused")
        await submit_approval(run.machine, "approved")
        record, _ = await run.finish()
        assert record.status == "finished"
    finally:
        if not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
