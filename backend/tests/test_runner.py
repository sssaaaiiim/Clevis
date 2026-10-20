import asyncio
from time import monotonic

import pytest

from app.agent.runner import run_agent
from app.core.budgets import Budget
from app.core.emitter import FanoutEventEmitter
from app.core.events import Action, Event, Target
from app.core.state import RunStateMachine, RunStatus
from app.core.store import InMemoryRunStore
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.skills import EmptySkillProvider
from app.interfaces.validator import AllowAllValidator


class Harness:
    def __init__(
        self,
        *,
        driver: FakeBrowserDriver | None = None,
        llm: FakeLLMClient | None = None,
        budget: Budget | None = None,
    ) -> None:
        self.store = InMemoryRunStore()
        self.emitter = FanoutEventEmitter(self.store)
        self.driver = driver or FakeBrowserDriver(delay=0)
        self.llm = llm or FakeLLMClient(delay=0)
        self.budget = budget or Budget()
        self.run_id = ""
        self.machine: RunStateMachine
        self.task: asyncio.Task[None]

    async def start(self) -> None:
        run = await self.store.create("Read sample result", "headless")
        self.run_id = run.runId
        self.machine = RunStateMachine(self.run_id, self.store, self.emitter)
        self.task = asyncio.create_task(
            run_agent(
                self.run_id,
                store=self.store,
                emitter=self.emitter,
                machine=self.machine,
                driver=self.driver,
                llm=self.llm,
                validator=AllowAllValidator(),
                skills=EmptySkillProvider(),
                budget=self.budget,
            )
        )

    async def wait_for(self, kind: str) -> None:
        async with asyncio.timeout(2):
            async with self.emitter.subscribe(self.run_id) as sub:
                while (await sub.queue.get()).type != kind:
                    pass

    async def events(self) -> list[Event]:
        return await self.store.list_events(self.run_id)


async def test_full_ordered_run() -> None:
    h = Harness()
    await h.start()
    await h.task
    events = await h.events()
    assert [e.type for e in events] == [
        "run.started",
        "plan.created",
        *["observation.summary", "step.proposed", "step.executed", "budget.update"] * 3,
        "run.finished",
    ]
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert h.budget.steps_used == 3
    assert h.budget.tokens_used == 40
    assert (await h.store.get(h.run_id)).status == RunStatus.FINISHED
    assert h.driver.closed


async def test_stop_interrupts_slow_operation_without_task_cancel() -> None:
    h = Harness(driver=FakeBrowserDriver(delay=10))
    await h.start()
    await h.wait_for("run.started")
    start = monotonic()
    await h.machine.transition(RunStatus.STOPPED)
    await asyncio.wait_for(h.task, 1.5)
    assert monotonic() - start < 2
    assert (await h.events())[-1].type == "run.stopped"
    assert h.driver.closed


async def test_pause_freezes_events_budget_and_resumes_same_step() -> None:
    h = Harness(driver=FakeBrowserDriver(delay=0.03), budget=Budget(max_seconds=0.8))
    await h.start()
    await h.wait_for("step.proposed")
    await h.machine.transition(RunStatus.PAUSED, reason="takeover")
    before = await h.events()
    counters = (h.budget.steps_used, h.budget.tokens_used, h.budget.seconds_used)
    await asyncio.sleep(0.9)
    assert await h.events() == before
    assert counters == (h.budget.steps_used, h.budget.tokens_used, h.budget.seconds_used)
    await h.machine.transition(RunStatus.RUNNING)
    await asyncio.wait_for(h.task, 2)
    assert (await h.store.get(h.run_id)).status == RunStatus.FINISHED
    events = await h.events()
    assert sum(e.type == "step.proposed" for e in events) == 3
    assert sum(e.type == "run.paused" for e in events) == 1
    assert sum(e.type == "run.resumed" for e in events) == 1
    assert h.budget.seconds_used < 0.8


@pytest.mark.parametrize(
    "budget, delay, message",
    [
        (Budget(max_steps=1), 0, "MAX_STEPS"),
        (Budget(max_seconds=0.03), 0.2, "MAX_SECONDS"),
    ],
)
async def test_budgets(budget: Budget, delay: float, message: str) -> None:
    h = Harness(driver=FakeBrowserDriver(delay=delay), budget=budget)
    await h.start()
    await asyncio.wait_for(h.task, 2)
    run = await h.store.get(h.run_id)
    assert run.status == RunStatus.FAILED
    assert run.error is not None and message in run.error
    assert (await h.events())[-1].type == "run.failed"
    assert h.driver.closed


async def test_loop_detection() -> None:
    action = Action(action="click", target=Target(ref="button"), rationale="Click the button.")
    h = Harness(llm=FakeLLMClient(actions=[action] * 3, delay=0))
    await h.start()
    await h.task
    run = await h.store.get(h.run_id)
    assert run.status == RunStatus.FAILED
    assert run.error is not None and "Loop detected" in run.error
    assert h.budget.steps_used == 3


@pytest.mark.parametrize("stage", ["start", "navigate", "observe", "act", "get_text", "close"])
async def test_driver_failures_never_leave_active_run(stage: str) -> None:
    driver = FakeBrowserDriver(delay=0)
    # All six public lifecycle methods can fail; no injected text leaks to the event log.
    driver.fail_on = stage  # type: ignore[assignment]
    h = Harness(driver=driver)
    await h.start()
    await h.task
    run = await h.store.get(h.run_id)
    assert run.status == RunStatus.FAILED
    assert run.error == "Unexpected RuntimeError during agent execution."
    assert (await h.events())[-1].type == "run.failed"


async def test_stop_while_paused() -> None:
    h = Harness(driver=FakeBrowserDriver(delay=0.02))
    await h.start()
    await h.wait_for("step.proposed")
    await h.machine.transition(RunStatus.PAUSED)
    await h.machine.transition(RunStatus.STOPPED)
    await asyncio.wait_for(h.task, 1)
    assert (await h.events())[-1].type == "run.stopped"


async def test_loop_identity_uses_ref_even_when_description_changes() -> None:
    actions = [
        Action(
            action="type",
            target=Target(ref="field", description=f"Label {i}"),
            value="same-value",
            rationale="Fill the field.",
        )
        for i in range(3)
    ]
    h = Harness(llm=FakeLLMClient(actions=actions, delay=0))
    await h.start()
    await h.task
    run = await h.store.get(h.run_id)
    assert run.status == RunStatus.FAILED
    assert run.error is not None and "Loop detected" in run.error


async def test_cancellation_flag_wakes_paused_run() -> None:
    h = Harness(driver=FakeBrowserDriver(delay=0.02))
    await h.start()
    await h.wait_for("step.proposed")
    await h.machine.transition(RunStatus.PAUSED)
    await asyncio.sleep(0)
    h.machine.cancelled.set()
    await asyncio.wait_for(h.task, 1)
    assert (await h.events())[-1].type == "run.stopped"


async def test_type_values_are_not_emitted() -> None:
    secret = "fake-only-password-value"
    actions = [
        Action(
            action="type",
            target=Target(ref="field"),
            value=secret,
            rationale=f"Fill the fake field with {secret}.",
        ),
        Action(action="done", value=secret, rationale="The demo is complete."),
    ]
    h = Harness(llm=FakeLLMClient(actions=actions, delay=0))
    await h.start()
    await h.task
    events = await h.events()
    assert secret not in "".join(event.model_dump_json() for event in events)
    proposed = next(event for event in events if event.type == "step.proposed")
    assert proposed.data.value == "[redacted]"
