"""Internal approval bridge for Task 3; deliberately no new HTTP routes."""

from typing import Literal

from app.core.state import InvalidTransition, RunStateMachine, RunStatus


class ApprovalMismatch(ValueError):
    pass


async def submit_approval(
    machine: RunStateMachine,
    decision: Literal["approved", "denied"],
    *,
    reason: str = "",
    approval_id: str | None = None,
) -> None:
    async with machine.control_lock:
        run = await machine.store.get(machine.run_id)
        if run.status != RunStatus.PAUSED or machine.pause_reason != "approval":
            raise InvalidTransition("Run is not waiting for policy approval.")
        if approval_id is not None and approval_id != machine.pending_approval_id:
            raise ApprovalMismatch("Approval request has expired.")
        if decision not in {"approved", "denied"}:
            raise InvalidTransition("Invalid approval decision.")
        if machine.approval_decision_submitted or machine.approval_decisions.full():
            raise InvalidTransition("An approval decision is already pending.")
        machine.approval_decision_submitted = True
        machine.approval_decision_reason = denial_category(reason) if decision == "denied" else ""
        machine.approval_decisions.put_nowait(decision)


def denial_category(reason: str) -> str:
    lowered = reason.lower()
    if "privacy" in lowered:
        return "Operator declined for privacy reasons."
    if "cost" in lowered or "price" in lowered:
        return "Operator declined the cost."
    if "domain" in lowered or "destination" in lowered:
        return "Operator requested a different destination."
    return "Operator denied the action."
