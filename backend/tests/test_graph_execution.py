import asyncio
import json
from collections.abc import AsyncIterator
from importlib.metadata import version
from time import monotonic
from typing import Any
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agent.graph import agent_graph, checkpointer
from app.agent.policy.approvals import submit_approval
from app.agent.state import AgentState
from app.agent.version import LANGGRAPH_TESTED_VERSION
from app.core.events import Action, Target
from app.core.state import RunRecord
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.llm import LLMError, LLMOutputError
from app.interfaces.validator import Verdict
from tests.event_sequences import successful_run_events
from tests.settings import IsolatedSettings
from tests.test_agent_loop import LoopRun
from tests.test_runner import Harness


async def test_graph_order_events_and_final_counters(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    original = agent_graph.astream

    async def stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        async for update in original(*args, **kwargs):
            order.extend(update)
            yield update

    monkeypatch.setattr(agent_graph, "astream", stream)
    harness = Harness()
    await harness.start()
    await harness.task
    events = await harness.events()
    assert [event.type for event in events] == successful_run_events(4, verified_after=(2, 4))
    cycle = ["navigator", "policy_check", "executor", "outcome_check"]
    assert order == ["planner", *cycle * 2, "next_sub_goal", *cycle * 2, "finish"]
    snapshot = await agent_graph.aget_state({"configurable": {"thread_id": harness.run_id}})
    state = AgentState.model_validate(snapshot.values)
    assert state.status == "finished" and state.result == "Found the sample result."
    assert len(state.sub_goals) == 2
    assert state.budget.steps_used == harness.budget.steps_used == 4
    assert state.budget.tokens_used == harness.budget.tokens_used == 70
    assert not snapshot.next


async def test_checkpoint_contains_no_typed_values_and_threads_are_isolated() -> None:
    canary = "CANARY-PASSWORD-9137"
    a = Harness(
        llm=FakeLLMClient(
            actions=[
                Action(
                    action="type", target=Target(ref="field"), value=canary, rationale="Fill field."
                ),
                Action(action="done", value="Complete", rationale="Finish."),
            ],
            delay=0,
        )
    )
    b = Harness()
    await a.start()
    await b.start()
    await asyncio.gather(a.task, b.task)
    async for snapshot in agent_graph.aget_state_history({"configurable": {"thread_id": a.run_id}}):
        assert canary not in json.dumps(snapshot.values, default=str)
    state = await agent_graph.aget_state({"configurable": {"thread_id": a.run_id}})
    other = await agent_graph.aget_state({"configurable": {"thread_id": b.run_id}})
    assert state.values["budget"]["steps_used"] == 2
    assert other.values["budget"]["steps_used"] == 4
    assert len(state.values["step_history"][0]["value_hash"]) == 64


async def test_interrupt_checkpoint_resumes_with_command() -> None:
    assert version("langgraph") == LANGGRAPH_TESTED_VERSION
    saver = MemorySaver()

    async def gate(state: AgentState) -> dict[str, Any]:
        answer = interrupt({"reason": "test approval", "run_id": state.run_id})
        return {"result": "approved" if answer["approved"] else "denied"}

    builder = StateGraph(AgentState)
    builder.add_node("gate", gate)
    builder.add_edge(START, "gate")
    builder.add_edge("gate", END)
    graph = builder.compile(checkpointer=saver)
    thread = uuid4().hex
    result = await graph.ainvoke(
        AgentState(run_id=thread, goal="Test interrupt"),
        config={"configurable": {"thread_id": thread}},
    )
    assert result["__interrupt__"]
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread}})
    assert snapshot.values["run_id"] == thread and snapshot.next == ("gate",)
    resumed = await graph.ainvoke(
        Command(resume={"approved": True}),
        config={"configurable": {"thread_id": thread}},
    )
    assert resumed["result"] == "approved"
    assert not (await graph.aget_state({"configurable": {"thread_id": thread}})).next


async def test_approval_pauses_until_approved_and_emits_validation() -> None:
    class ApprovalValidator:
        async def validate(self, run_state: RunRecord, action: Action) -> Verdict:
            return Verdict(verdict="approval", reason="Exercise policy approval.")

    run = LoopRun(
        FakeLLMClient(
            actions=[
                Action(action="done", value="Complete", rationale="Finish."),
            ],
            delay=0,
        ),
        validator=ApprovalValidator(),
    )
    await run.start()
    try:
        async with asyncio.timeout(3):
            while True:
                snapshot = await agent_graph.aget_state({"configurable": {"thread_id": run.run_id}})
                if snapshot.interrupts:
                    break
                await asyncio.sleep(0.005)
        assert snapshot.next == ("approval_gate",)
        assert (await run.store.get(run.run_id)).status == "paused"
        assert run.machine.pause_reason == "approval"
        assert not run.task.done()
        assert isinstance(run.driver, FakeBrowserDriver) and not run.driver.actions
        assert not run.driver.closed
        await submit_approval(run.machine, "approved")
        record, events = await run.finish()
        assert record.status == "finished"
        validated = [
            event.model_dump()["data"] for event in events if event.type == "step.validated"
        ]
        assert len(validated) == 1 and validated[0]["verdict"] == "approval"
        assert sum(event.type == "approval.required" for event in events) == 1
        assert sum(event.type == "run.paused" for event in events) == 1
        assert sum(event.type == "run.resumed" for event in events) == 1
        assert [action.action for action in run.driver.actions] == ["done"]
        assert record.result == "Complete" and run.driver.closed
    finally:
        if not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)


async def test_graph_history_is_capped_and_cost_prompt_is_present() -> None:
    class RecordingLLM(FakeLLMClient):
        async def propose(self, messages: list[Any], schema: Any) -> Any:
            if schema is Action:
                assert "Cost remaining USD:" in messages[-1].content
                assert "Current sub-goal:" in messages[-1].content
            return await super().propose(messages, schema)

    h = Harness(
        settings=IsolatedSettings(subgoal_max_steps=30),
        llm=RecordingLLM(
            actions=[
                Action(
                    action="navigate",
                    value=f"https://example.test/page/{i}",
                    rationale="Open page.",
                )
                for i in range(10)
            ]
            + [Action(action="done", value="Complete", rationale="Finish.")],
            delay=0,
        )
    )
    await h.start()
    await h.task
    snapshot = await agent_graph.aget_state({"configurable": {"thread_id": h.run_id}})
    state = AgentState.model_validate(snapshot.values)
    assert state.status == "finished"
    assert len(state.step_history) == len(state.history) == 8
    assert state.step_history[0].step_id == 4
    assert state.step_history[-1].step_id == 11


@pytest.mark.parametrize("stage", ["navigator", "executor"])
async def test_graph_stop_interrupts_in_flight_node_within_two_seconds(stage: str) -> None:
    ready = asyncio.Event()

    class SlowDriver(FakeBrowserDriver):
        async def act(self, action: Action) -> Any:
            if stage == "executor":
                ready.set()
                await asyncio.sleep(10)
            return await super().act(action)

    class SlowLLM(FakeLLMClient):
        closed = False

        async def propose(self, messages: list[Any], schema: Any) -> Any:
            if schema is Action and stage == "navigator":
                ready.set()
                await asyncio.sleep(10)
            return await super().propose(messages, schema)

        async def close(self) -> None:
            self.closed = True

    llm = SlowLLM(delay=0)
    h = Harness(driver=SlowDriver(delay=0), llm=llm)
    await h.start()
    await asyncio.wait_for(ready.wait(), 2)
    started = monotonic()
    h.machine.cancelled.set()
    h.task.cancel()
    await asyncio.wait_for(h.task, 2)
    elapsed = monotonic() - started
    assert elapsed < 2
    assert h.driver.closed and llm.closed
    assert (await h.events())[-1].type == "run.stopped"
    snapshot = await agent_graph.aget_state({"configurable": {"thread_id": h.run_id}})
    assert snapshot.values["status"] == "stopped"


@pytest.mark.parametrize("failure", [RuntimeError, LLMError, LLMOutputError])
async def test_checkpoint_error_channels_do_not_store_raw_exception_text(
    failure: type[Exception],
) -> None:
    canary = "CANARY-PASSWORD-9137"

    class FailingLLM(FakeLLMClient):
        async def propose(self, messages: list[Any], schema: Any) -> Any:
            if schema is Action:
                raise failure(canary)
            return await super().propose(messages, schema)

    h = Harness(llm=FailingLLM(delay=0))
    await h.start()
    await h.task
    assert (await h.store.get(h.run_id)).status == "failed"
    async for saved in checkpointer.alist({"configurable": {"thread_id": h.run_id}}):
        assert canary not in repr(saved.checkpoint)
        assert canary not in repr(saved.pending_writes)
    assert canary not in repr(await h.events())
