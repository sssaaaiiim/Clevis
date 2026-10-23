import asyncio
from typing import Any

import pytest

from app.agent.runner import run_agent
from app.core.budgets import Budget
from app.core.emitter import FanoutEventEmitter
from app.core.events import Action, Event, Target
from app.core.state import RunRecord, RunStateMachine
from app.core.store import InMemoryRunStore
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import ActionResult, BrowserDriver
from app.interfaces.llm import LLMClient, LLMResponse, Message, T, Usage
from app.interfaces.skills import EmptySkillProvider
from app.interfaces.validator import ActionValidator, AllowAllValidator, Verdict


def done(value: str = "Complete") -> Action:
    return Action(action="done", value=value, rationale="Finished.")


class LoopRun:
    def __init__(
        self,
        llm: LLMClient,
        *,
        budget: Budget | None = None,
        driver: BrowserDriver | None = None,
        validator: ActionValidator | None = None,
    ) -> None:
        self.store = InMemoryRunStore()
        self.emitter = FanoutEventEmitter(self.store)
        self.llm = llm
        self.driver = driver or FakeBrowserDriver(delay=0)
        self.validator = validator or AllowAllValidator()
        self.budget = budget or Budget()
        self.machine: RunStateMachine
        self.run_id = ""
        self.task: asyncio.Task[None]

    async def start(self) -> None:
        run = await self.store.create("Read the demo", "headless")
        self.run_id = run.runId
        self.machine = RunStateMachine(run.runId, self.store, self.emitter)
        self.task = asyncio.create_task(
            run_agent(
                run.runId,
                store=self.store,
                emitter=self.emitter,
                machine=self.machine,
                driver=self.driver,
                llm=self.llm,
                validator=self.validator,
                skills=EmptySkillProvider(),
                budget=self.budget,
            )
        )

    async def finish(self) -> tuple[RunRecord, list[Event]]:
        await asyncio.wait_for(self.task, 5)
        return await self.store.get(self.run_id), await self.store.list_events(self.run_id)


@pytest.mark.parametrize("empty_count", [1, 2])
async def test_empty_done_reasked_once(empty_count: int) -> None:
    run = LoopRun(FakeLLMClient(actions=[done("")] * empty_count + [done()], delay=0))
    await run.start()
    record, events = await run.finish()
    assert record.status == ("finished" if empty_count == 1 else "failed")
    assert run.budget.steps_used == 2
    assert sum(e.type == "step.proposed" for e in events) == 2


class StaleDriver(FakeBrowserDriver):
    def __init__(self, count: int) -> None:
        super().__init__(delay=0)
        self.remaining = count
        self.observations = 0

    async def observe(self) -> Any:
        self.observations += 1
        return await super().observe()

    async def act(self, action: Action) -> ActionResult:
        if self.remaining:
            self.remaining -= 1
            return ActionResult(ok=False, summary="Reference is stale.", error_code="STALE_REF")
        return await super().act(action)


@pytest.mark.parametrize("count", [1, 3])
async def test_stale_reobserves_and_three_fail(count: int) -> None:
    actions = [
        Action(action="click", target=Target(ref=f"e{i}"), rationale="Click.") for i in range(count)
    ] + [done()]
    driver = StaleDriver(count)
    run = LoopRun(FakeLLMClient(actions=actions, delay=0), driver=driver)
    await run.start()
    record, _ = await run.finish()
    assert record.status == ("finished" if count == 1 else "failed")
    assert driver.observations == count + (count == 1)
    if count == 3:
        assert record.error and "stale/not-found" in record.error


class DenyOnce:
    calls = 0

    async def validate(self, run_state: RunRecord, action: Action) -> Verdict:
        self.calls += 1
        return Verdict(verdict="deny" if self.calls == 1 else "allow", reason="Policy denied")


async def test_denied_action_not_executed_and_reproposed() -> None:
    class CountingDriver(FakeBrowserDriver):
        calls = 0

        async def act(self, action: Action) -> ActionResult:
            self.calls += 1
            return await super().act(action)

    driver = CountingDriver(delay=0)
    run = LoopRun(
        FakeLLMClient(actions=[done(), done()], delay=0), driver=driver, validator=DenyOnce()
    )
    await run.start()
    record, events = await run.finish()
    assert record.status == "finished" and driver.calls == 1
    assert run.budget.steps_used == 2
    executed = [e for e in events if e.type == "step.executed"]
    assert not executed[0].data.ok and executed[1].data.ok


class CostLLM(FakeLLMClient):
    async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
        response = await super().propose(messages, schema)
        usage = Usage(prompt_tokens=6, completion_tokens=4, cost_usd=0.1)
        return LLMResponse(parsed=response.parsed, tokens_used=10, usage=usage)


@pytest.mark.parametrize(
    "budget, name",
    [
        (Budget(max_steps=1), "MAX_STEPS"),
        (Budget(max_seconds=0.01), "MAX_SECONDS"),
        (Budget(max_tokens=15), "MAX_TOKENS"),
        (Budget(max_cost_usd=0.15), "MAX_COST_USD"),
    ],
)
async def test_all_limits_report_final_counters(budget: Budget, name: str) -> None:
    run = LoopRun(CostLLM(delay=0.03), budget=budget)
    await run.start()
    record, events = await run.finish()
    assert record.status == "failed" and record.error and name in record.error
    last = [e for e in events if e.type == "budget.update"][-1]
    assert last.data.tokensUsed == budget.tokens_used
    assert last.data.costUsd == budget.cost_usd
    assert last.data.stepsUsed == budget.steps_used
    assert last.data.promptTokens + last.data.completionTokens == last.data.tokensUsed


async def test_cost_limit_disabled() -> None:
    run = LoopRun(CostLLM(actions=[done()], delay=0), budget=Budget(max_cost_usd=0))
    await run.start()
    assert (await run.finish())[0].status == "finished"


async def test_no_progress_with_different_actions() -> None:
    actions = [
        Action(action="click", target=Target(ref=f"e{i}"), rationale="Click.") for i in range(5)
    ]
    run = LoopRun(FakeLLMClient(actions=actions, delay=0))
    await run.start()
    record, _ = await run.finish()
    assert record.status == "failed" and record.error
    assert "no page progress over 5" in record.error
    assert "click e4" in record.error
    assert run.budget.steps_used == 5


async def test_different_values_do_not_trigger_identical_action_loop() -> None:
    actions = [
        Action(action="type", target=Target(ref="same"), value=str(i), rationale="Fill.")
        for i in range(3)
    ] + [done()]
    run = LoopRun(FakeLLMClient(actions=actions, delay=0))
    await run.start()
    assert (await run.finish())[0].status == "finished"


async def test_verification_wait_hands_off_without_hitting_loop_limit() -> None:
    from app.core.state import RunStatus
    from app.interfaces.browser import Observation

    class VerificationDriver(FakeBrowserDriver):
        blocked = True

        async def observe(self) -> Observation:
            if self.blocked:
                return Observation(
                    title="Just a moment...",
                    text_excerpt="Performing security verification. Verify you are human.",
                )
            return await super().observe()

    driver = VerificationDriver(delay=0)
    llm = FakeLLMClient(
        actions=[Action(action="wait", value="5", rationale="Wait for verification."), done()],
        delay=0,
    )
    run = LoopRun(llm, driver=driver)
    await run.start()
    try:
        async with run.emitter.subscribe(run.run_id) as sub, asyncio.timeout(2):
            while (await sub.queue.get()).type != "run.paused":
                pass
        paused = await run.store.get(run.run_id)
        assert paused.status == "paused" and run.machine.pause_reason == "handoff"
        assert llm.index == 1 and not driver.actions
        assert run.budget.steps_used == 1
        events = await run.store.list_events(run.run_id)
        proposed = next(e for e in events if e.type == "step.proposed")
        assert proposed.data.model_dump()["action"] == "handoff"
        assert not any(e.type == "run.failed" for e in events)
        driver.blocked = False
        await driver.resume_actions()
        await run.machine.transition(RunStatus.RUNNING)
        record, _ = await run.finish()
        assert record.status == "finished"
    finally:
        if not run.task.done():
            run.task.cancel()
        await asyncio.gather(run.task, return_exceptions=True)
