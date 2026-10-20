import asyncio
import secrets
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
from app.preview.control import ControlSession
from app.preview.factory import create_preview_channel
from app.preview.hub import PreviewHub


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
        self.preview_hubs: dict[str, PreviewHub] = {}
        self.preview_tokens: dict[str, str] = {}
        self.control_tokens: dict[str, str] = {}
        self.controls: dict[str, ControlSession] = {}

    async def create(self, goal: str, mode: Mode) -> RunRecord:
        # Construct dependencies before persisting a run so a factory failure cannot strand it.
        driver, llm = self.driver_factory(), self.llm_factory()
        key = self.settings.openrouter_api_key.get_secret_value()
        safe_goal = goal.replace(key, "[redacted]") if key else goal
        run = await self.store.create(safe_goal, mode)
        machine = RunStateMachine(run.runId, self.store, self.emitter)
        self.machines[run.runId] = machine
        self.controls[run.runId] = ControlSession(machine)
        self.control_tokens[run.runId] = secrets.token_urlsafe(32)
        hub = PreviewHub(self.settings, defer_retention=True)
        self.preview_hubs[run.runId] = hub
        self.preview_tokens[run.runId] = secrets.token_urlsafe(32)
        channel = create_preview_channel(driver, hub, self.settings)

        async def execute() -> None:
            try:
                await run_agent(
                    run.runId,
                    store=self.store,
                    emitter=self.emitter,
                    machine=machine,
                    driver=driver,
                    llm=llm,
                    validator=AllowAllValidator(),
                    skills=EmptySkillProvider(),
                    settings=self.settings,
                    preview=channel,
                    budget=Budget(
                        max_steps=self.settings.max_steps,
                        max_seconds=self.settings.max_seconds,
                        max_tokens=self.settings.max_tokens,
                        max_cost_usd=self.settings.max_cost_usd,
                    ),
                )
            finally:
                await hub.end()
                hub.begin_retention()

        task = asyncio.create_task(execute(), name=f"run:{run.runId}")
        self.tasks[run.runId] = task
        task.add_done_callback(lambda completed: self.tasks.pop(run.runId, None))
        return run

    async def stop(self, run_id: str) -> RunRecord:
        run = await self.store.get(run_id)
        if run.status == RunStatus.STOPPED:
            return run
        if run.status in TERMINAL_STATES:
            raise InvalidTransition(f"Cannot stop a {run.status} run.")
        machine = self.machines[run_id]
        task = self.tasks.get(run_id)
        if task is not None and not task.done():
            if not machine.cancelled.is_set():
                machine.cancelled.set()
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        run = await self.store.get(run_id)
        if run.status not in TERMINAL_STATES:
            run = await machine.transition(RunStatus.STOPPED)
        elif run.status != RunStatus.STOPPED:
            raise InvalidTransition(f"Cannot stop a {run.status} run.")
        await self.preview_hubs[run_id].end()
        self.preview_hubs[run_id].begin_retention()
        return run

    async def shutdown(self) -> None:
        active = list(self.tasks)
        await asyncio.gather(*(self.stop(run_id) for run_id in active), return_exceptions=True)
        await asyncio.gather(*(hub.close() for hub in self.preview_hubs.values()))
        self.preview_tokens.clear()
        self.control_tokens.clear()
        await asyncio.gather(*(control.release() for control in self.controls.values()))
