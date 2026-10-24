"""Internal approval bridge for Task 3; deliberately no new HTTP routes."""

from typing import Literal

from app.core.state import InvalidTransition, RunStateMachine, RunStatus


async def submit_approval(
    machine: RunStateMachine,
    decision: Literal["approved", "denied"],
) -> None:
    async with machine.control_lock:
        run = await machine.store.get(machine.run_id)
        if run.status != RunStatus.PAUSED or machine.pause_reason != "approval":
            raise InvalidTransition("Run is not waiting for policy approval.")
        if decision not in {"approved", "denied"}:
            raise InvalidTransition("Invalid approval decision.")
        if machine.approval_decisions.full():
            raise InvalidTransition("An approval decision is already pending.")
        machine.approval_decisions.put_nowait(decision)
