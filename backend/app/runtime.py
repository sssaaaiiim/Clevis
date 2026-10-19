import asyncio
from collections.abc import Callable

from app.agent.runner import run_agent
from app.config import Settings
from app.core.budgets import Budget
from app.core.emitter import FanoutEventEmitter
from app.core.events import Mode
from app.core.state import TERMINAL_STATES, InvalidTransition, RunRecord, RunStateMachine, RunStatus
from app.core.store import InMemoryRunStore
from app.interfaces.browser import BrowserDriver
from app.interfaces.llm import LLMClient
from app.interfaces.skills import EmptySkillProvider
from app.interfaces.validator import AllowAllValidator


class RunService:
    def __init__(
        self,
        settings: Settings,
        driver_factory: Callable[[], BrowserDriver],
        llm_factory: Callable[[], LLMClient],
    ) -> None:
        self.settings = settings
        self.driver_factory = driver_factory
        self.llm_factory = llm_factory
        self.store = InMemoryRunStore()
        self.emitter = FanoutEventEmitter(self.store)
        self.machines: dict[str, RunStateMachine] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}

    async def create(self, goal: str, mode: Mode) -> RunRecord:
        # Construct dependencies before persisting a run so a factory failure cannot strand it.
        driver, llm = self.driver_factory(), self.llm_factory()
        run = await self.store.create(goal, mode)
        machine = RunStateMachine(run.runId, self.store, self.emitter)
        self.machines[run.runId] = machine
        task = asyncio.create_task(
            run_agent(
                run.runId,
                store=self.store,
                emitter=self.emitter,
                machine=machine,
                driver=driver,
                llm=llm,
                validator=AllowAllValidator(),
                skills=EmptySkillProvider(),
                budget=Budget(
                    max_steps=self.settings.max_steps,
                    max_seconds=self.settings.max_seconds,
                    max_tokens=self.settings.max_tokens,
                ),
            ),
            name=f"run:{run.runId}",
        )
        self.tasks[run.runId] = task
        task.add_done_callback(lambda completed: self.tasks.pop(run.runId, None))
        return run

    async def stop(self, run_id: str) -> RunRecord:
        run = await self.store.get(run_id)
        if run.status == RunStatus.STOPPED:
            return run
        if run.status in TERMINAL_STATES:
            raise InvalidTransition(f"Cannot stop a {run.status} run.")
        try:
            run = await self.machines[run_id].transition(RunStatus.STOPPED)
        except InvalidTransition:
            run = await self.store.get(run_id)
            if run.status != RunStatus.STOPPED:
                raise
        task = self.tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return run

    async def shutdown(self) -> None:
        tasks = list(self.tasks.values())
        for run_id in list(self.tasks):
            run = await self.store.get(run_id)
            if run.status not in TERMINAL_STATES:
                await self.machines[run_id].transition(RunStatus.STOPPED)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
