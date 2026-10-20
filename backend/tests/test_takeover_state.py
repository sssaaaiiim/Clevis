import asyncio
from time import monotonic

import pytest

from app.core.events import Action
from app.core.state import InvalidTransition, RunStatus
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.runtime import RunService
from tests.settings import IsolatedSettings


async def wait_status(service: RunService, run_id: str, status: RunStatus) -> None:
    async with asyncio.timeout(3):
        async with service.emitter.subscribe(run_id) as subscription:
            while (await service.store.get(run_id)).status != status:
                await subscription.queue.get()


class SlowAct(FakeBrowserDriver):
    def __init__(self) -> None:
        super().__init__(delay=0)
        self.entered = asyncio.Event()
        self.interrupted = asyncio.Event()

    async def act(self, action: Action):  # type: ignore[no-untyped-def]
        if self.interrupted.is_set():
            return await super().act(action)
        self.entered.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            self.interrupted.set()
            raise
        return await super().act(action)


async def test_takeover_waits_for_inflight_and_resume_observes() -> None:
    driver = SlowAct()
    llm = FakeLLMClient(
        actions=[
            Action(action="wait", rationale="Wait."),
            Action(action="done", value="Finished", rationale="Finish."),
        ],
        delay=0,
    )
    service = RunService(IsolatedSettings(), lambda: driver, lambda: llm)
    try:
        run = await service.create("Demo", "headless")
        await asyncio.wait_for(driver.entered.wait(), 2)
        started = monotonic()
        assert (await service.takeover(run.runId)).status == RunStatus.PAUSED
        assert monotonic() - started < 2 and driver.interrupted.is_set()
        assert driver.paused and not driver.closed
        assert await service.takeover(run.runId) == await service.store.get(run.runId)
        count = len(await service.store.list_events(run.runId))
        await asyncio.sleep(0.1)
        assert len(await service.store.list_events(run.runId)) == count
        pending = service.machines[run.runId].in_flight
        assert pending is None or pending.done()
        await service.resume(run.runId)
        await wait_status(service, run.runId, RunStatus.FINISHED)
        events = await service.store.list_events(run.runId)
        resumed = next(i for i, e in enumerate(events) if e.type == "run.resumed")
        assert events[resumed + 1].type == "observation.summary"
        with pytest.raises(InvalidTransition):
            await service.takeover(run.runId)
    finally:
        await service.shutdown()


@pytest.mark.parametrize("idle", [False, True])
async def test_control_timeout_and_stop(idle: bool) -> None:
    driver = SlowAct()
    service = RunService(
        IsolatedSettings(
            takeover_max_seconds=10 if idle else 0.05, input_idle_timeout_s=0.05 if idle else 10
        ),
        lambda: driver,
        lambda: FakeLLMClient(delay=0),
    )
    try:
        run = await service.create("Demo", "headless")
        await driver.entered.wait()
        await service.takeover(run.runId)
        await wait_status(service, run.runId, RunStatus.FAILED)
        assert (await service.store.get(run.runId)).error == "Take-over timed out"
        await asyncio.sleep(0.1)
        assert driver.closed
    finally:
        await service.shutdown()


async def test_stop_during_takeover() -> None:
    driver = SlowAct()
    service = RunService(IsolatedSettings(), lambda: driver, lambda: FakeLLMClient(delay=0))
    run = await service.create("Demo", "headless")
    try:
        await driver.entered.wait()
        await service.takeover(run.runId)
        assert (await asyncio.wait_for(service.stop(run.runId), 2)).status == RunStatus.STOPPED
        assert driver.closed
    finally:
        await service.shutdown()


async def test_handoff_resume_and_limit() -> None:
    from app.agent.prompts import SYSTEM_PROMPT
    from app.core.events import HandoffData

    driver = FakeBrowserDriver(delay=0)
    llm = FakeLLMClient(
        actions=[
            Action(
                action="handoff",
                value="Please sign in, then click Resume",
                rationale="A human is needed.",
            ),
            Action(action="handoff", value="Please complete 2FA", rationale="A human is needed."),
        ],
        delay=0,
    )
    service = RunService(IsolatedSettings(max_handoffs=1), lambda: driver, lambda: llm)
    try:
        run = await service.create("Demo", "headless")
        await wait_status(service, run.runId, RunStatus.PAUSED)
        assert driver.paused and service.controls[run.runId].ready
        events = await service.store.list_events(run.runId)
        pause = events[-1]
        assert isinstance(pause.data, HandoffData)
        assert pause.data.message == "Please sign in, then click Resume"
        assert service.machines[run.runId].pause_reason == "handoff"
        await service.resume(run.runId)
        await wait_status(service, run.runId, RunStatus.FAILED)
        assert "MAX_HANDOFFS" in ((await service.store.get(run.runId)).error or "")
        assert not driver.actions  # Handoff never reaches the browser action implementation.
        assert "handoff" in SYSTEM_PROMPT and "Never include secrets" in SYSTEM_PROMPT
    finally:
        await service.shutdown()
