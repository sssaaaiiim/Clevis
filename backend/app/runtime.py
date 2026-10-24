import asyncio
import logging
import secrets
from collections.abc import Callable
from time import monotonic

from app.agent.graph import agent_graph
from app.agent.policy.approvals import ApprovalMismatch, submit_approval
from app.agent.policy.validator import PolicyValidator
from app.agent.runner import run_agent
from app.browser.input_privacy import InputPrivacy
from app.config import Settings
from app.core.budgets import Budget
from app.core.emitter import FanoutEventEmitter
from app.core.events import Mode
from app.core.state import TERMINAL_STATES, InvalidTransition, RunRecord, RunStateMachine, RunStatus
from app.core.store import InMemoryRunStore
from app.interfaces.browser import BrowserDriver, PausableDriver
from app.interfaces.llm import LLMClient
from app.interfaces.skills import EmptySkillProvider
from app.preview.control import ControlSession
from app.preview.factory import create_preview_channel
from app.preview.hub import PreviewHub


class RunCapacityExceeded(Exception):
    """All configured per-process browser/run slots are occupied."""


class StaleApproval(ValueError):
    pass


class RunService:
    def __init__(
        self,
        settings: Settings,
        driver_factory: Callable[[], BrowserDriver],
        llm_factory: Callable[[], LLMClient],
        outcome_llm_factory: Callable[[], LLMClient] | None = None,
    ) -> None:
        self.admission_lock = asyncio.Lock()
        self.settings = settings
        self.driver_factory = driver_factory
        self.llm_factory = llm_factory
        self.outcome_llm_factory = outcome_llm_factory
        self.store = InMemoryRunStore()
        self.emitter = FanoutEventEmitter(self.store)
        self.machines: dict[str, RunStateMachine] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.preview_hubs: dict[str, PreviewHub] = {}
        self.preview_tokens: dict[str, str] = {}
        self.control_tokens: dict[str, str] = {}
        self.approval_tokens: dict[str, str] = {}
        self.controls: dict[str, ControlSession] = {}
        self.drivers: dict[str, BrowserDriver] = {}
        self.control_watchers: dict[str, asyncio.Task[None]] = {}

    async def create(self, goal: str, mode: Mode) -> RunRecord:
        async with self.admission_lock:
            if sum(not task.done() for task in self.tasks.values()) >= (
                self.settings.max_concurrent_runs
            ):
                raise RunCapacityExceeded
            return await self._create(goal, mode)

    async def _create(self, goal: str, mode: Mode) -> RunRecord:
        # Construct dependencies before persisting a run so a factory failure cannot strand it.
        driver, llm = self.driver_factory(), self.llm_factory()
        key = self.settings.openrouter_api_key.get_secret_value()
        safe_goal = goal.replace(key, "[redacted]") if key else goal
        run = await self.store.create(safe_goal, mode)
        machine = RunStateMachine(run.runId, self.store, self.emitter)
        privacy = getattr(driver, "input_privacy", None)
        if isinstance(privacy, InputPrivacy):
            machine.input_privacy = privacy
        self.machines[run.runId] = machine
        self.controls[run.runId] = ControlSession(machine)
        self.drivers[run.runId] = driver
        self.control_tokens[run.runId] = secrets.token_urlsafe(32)
        self.approval_tokens[run.runId] = secrets.token_urlsafe(32)
        hub = PreviewHub(self.settings, defer_retention=True)
        self.preview_hubs[run.runId] = hub
        self.preview_tokens[run.runId] = secrets.token_urlsafe(32)
        channel = create_preview_channel(driver, hub, self.settings)

        async def handoff(message: str) -> None:
            await self.takeover(run.runId, reason="handoff", message=message)

        async def execute() -> None:
            try:
                await run_agent(
                    run.runId,
                    store=self.store,
                    emitter=self.emitter,
                    machine=machine,
                    driver=driver,
                    llm=llm,
                    outcome_llm=self.outcome_llm_factory() if self.outcome_llm_factory else None,
                    validator=PolicyValidator(self.settings),
                    skills=EmptySkillProvider(),
                    settings=self.settings,
                    preview=channel,
                    on_handoff=handoff,
                    budget=Budget(
                        max_steps=self.settings.max_steps,
                        max_seconds=self.settings.max_seconds,
                        max_tokens=self.settings.max_tokens,
                        max_cost_usd=self.settings.max_cost_usd,
                    ),
                )
            finally:
                control = self.controls[run.runId]
                control.ready = False
                async with control.lock:
                    await control.release()
                watcher = self.control_watchers.pop(run.runId, None)
                if watcher:
                    watcher.cancel()
                    await asyncio.gather(watcher, return_exceptions=True)
                await hub.end()
                hub.begin_retention()

        task = asyncio.create_task(execute(), name=f"run:{run.runId}")
        self.tasks[run.runId] = task
        task.add_done_callback(lambda completed: self.tasks.pop(run.runId, None))
        return run

    async def decide_approval(
        self,
        run_id: str,
        approval_id: str,
        decision: str,
        reason: str = "",
    ) -> None:
        from typing import Literal, cast

        await self.store.get(run_id)
        machine = self.machines[run_id]
        # submit_approval takes this lock too; verify and enqueue under one lock via
        # its bound-ID check to reject duplicates and newer approval races atomically.
        run = await self.store.get(run_id)
        if run.status != RunStatus.PAUSED or machine.pause_reason != "approval":
            raise InvalidTransition("Run is not waiting for approval.")
        snapshot = await agent_graph.aget_state({"configurable": {"thread_id": run_id}})
        if approval_id != snapshot.values.get("pending_approval_id"):
            raise StaleApproval("Approval request has expired.")
        try:
            await submit_approval(
                machine,
                cast(Literal["approved", "denied"], decision),
                reason=reason,
                approval_id=approval_id,
            )
        except ApprovalMismatch:
            raise StaleApproval("Approval request has expired.") from None
        logging.getLogger("clevis").info(
            f"policy.{decision}",
            extra={
                "runId": run_id,
                "tier": 2,
                "action": (snapshot.values.get("last_action") or {}).get("action", "unknown"),
            },
        )

    async def takeover(
        self, run_id: str, *, reason: str = "takeover", message: str = ""
    ) -> RunRecord:
        await self.store.get(run_id)
        machine = self.machines[run_id]
        async with machine.control_lock:
            run = await self.store.get(run_id)
            if run.status == RunStatus.PAUSED and machine.pause_reason == reason:
                return run
            if run.status != RunStatus.RUNNING:
                raise InvalidTransition(f"Cannot take over a {run.status} run.")
            control, driver = self.controls[run_id], self.drivers[run_id]
            async with control.lock:
                if isinstance(driver, PausableDriver):
                    await driver.pause_actions()
                run = await machine.transition(RunStatus.PAUSED, reason=reason, message=message)
                pending = machine.in_flight
                if pending and not pending.done():
                    pending.cancel()
                    try:
                        async with asyncio.timeout(1.8):
                            await asyncio.gather(pending, return_exceptions=True)
                    except TimeoutError:
                        await machine.transition(
                            RunStatus.FAILED, error="Take-over could not stop active work."
                        )
                        self.tasks[run_id].cancel()
                        raise InvalidTransition("Take-over could not stop active work.") from None
                machine.input_privacy.active = True
                control.ready = True
                control.last_activity = monotonic()
            self.control_watchers[run_id] = asyncio.create_task(self._control_timeout(run_id))
            return run

    async def resume(self, run_id: str) -> RunRecord:
        await self.store.get(run_id)
        machine = self.machines[run_id]
        async with machine.control_lock:
            run = await self.store.get(run_id)
            if run.status != RunStatus.PAUSED:
                raise InvalidTransition(f"Cannot resume a {run.status} run.")
            if machine.pause_reason == "approval":
                raise InvalidTransition(
                    "Policy approval requires an approval decision, not takeover resume."
                )
            control = self.controls[run_id]
            async with control.lock:
                control.ready = False
                await control.release()
                driver = self.drivers[run_id]
                if isinstance(driver, PausableDriver):
                    await driver.resume_actions()
                run = await machine.transition(RunStatus.RUNNING, expected=RunStatus.PAUSED)
            watcher = self.control_watchers.pop(run_id, None)
            if watcher:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
            return run

    async def _control_timeout(self, run_id: str) -> None:
        machine, control = self.machines[run_id], self.controls[run_id]
        while (await self.store.get(run_id)).status == RunStatus.PAUSED:
            now = monotonic()
            if machine.paused_at is not None and (
                now - machine.paused_at >= self.settings.takeover_max_seconds
                or now - control.last_activity >= self.settings.input_idle_timeout_s
            ):
                # Transition first so cancellation cleanup cannot overwrite failure with stopped.
                async with machine.control_lock:
                    if (await self.store.get(run_id)).status != RunStatus.PAUSED:
                        return
                    await machine.transition(
                        RunStatus.FAILED, expected=RunStatus.PAUSED, error="Take-over timed out"
                    )
                    control.ready = False
                    task = self.tasks.get(run_id)
                    if task:
                        task.cancel()
                return
            await asyncio.sleep(0.02)

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
        pending = list(self.tasks.values())
        await asyncio.gather(*(self.stop(run_id) for run_id in active), return_exceptions=True)
        # Terminal runs can still be closing Chromium; stop rejects them, so join cleanup too.
        await asyncio.gather(*pending, return_exceptions=True)
        await asyncio.gather(*(hub.close() for hub in self.preview_hubs.values()))
        self.preview_tokens.clear()
        self.control_tokens.clear()
        self.approval_tokens.clear()
        await asyncio.gather(*(control.release() for control in self.controls.values()))
