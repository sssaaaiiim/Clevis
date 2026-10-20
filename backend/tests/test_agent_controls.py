import asyncio
from time import monotonic

import pytest

from app.core.budgets import Budget
from app.core.events import Action
from app.core.state import RunStatus
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.llm import LLMResponse, Message, T
from tests.test_agent_loop import LoopRun, done


@pytest.mark.parametrize("stage", ["llm", "browser"])
async def test_stop_during_inflight_io(stage: str) -> None:
    started, aborted = asyncio.Event(), asyncio.Event()

    class SlowLLM(FakeLLMClient):
        closed = False

        async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
            if schema is Action and stage == "llm":
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    aborted.set()
            return await super().propose(messages, schema)

        async def close(self) -> None:
            self.closed = True

    class SlowDriver(FakeBrowserDriver):
        async def act(self, action: Action):  # type: ignore[no-untyped-def]
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                aborted.set()
            return await super().act(action)

    llm = SlowLLM(actions=[done()], delay=0)
    driver = SlowDriver(delay=0) if stage == "browser" else FakeBrowserDriver(delay=0)
    run = LoopRun(llm, driver=driver)
    await run.start()
    await asyncio.wait_for(started.wait(), 2)
    begin = monotonic()
    run.machine.cancelled.set()
    run.task.cancel()
    record, events = await run.finish()
    assert monotonic() - begin < 2
    assert record.status == "stopped" and aborted.is_set()
    assert driver.closed and llm.closed
    assert events[-1].type == "run.stopped"


async def test_pause_during_proposal_reobserves_before_next_proposal() -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    class PausingLLM(FakeLLMClient):
        actor_calls = 0

        async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
            if schema is Action:
                self.actor_calls += 1
                if self.actor_calls == 1:
                    entered.set()
                    await release.wait()
            return await super().propose(messages, schema)

    class WatchingDriver(FakeBrowserDriver):
        observations = 0

        async def observe(self):  # type: ignore[no-untyped-def]
            self.observations += 1
            return await super().observe()

    driver = WatchingDriver(delay=0)
    llm = PausingLLM(actions=[done("Discarded"), done("Fresh")], delay=0)
    run = LoopRun(llm, driver=driver, budget=Budget(max_seconds=0.2))
    await run.start()
    await entered.wait()
    await run.machine.transition(RunStatus.PAUSED)
    snapshot = await run.store.list_events(run.run_id)
    counters = run.budget.event_data()
    release.set()
    await asyncio.sleep(0.3)
    assert run.budget.event_data() == counters
    assert await run.store.list_events(run.run_id) == snapshot
    assert driver.observations == 1 and llm.actor_calls == 1
    await run.machine.transition(RunStatus.RUNNING)
    record, _ = await run.finish()
    assert record.status == "finished" and record.result == "Fresh"
    assert driver.observations == 2
    assert run.budget.seconds_used < 0.2
