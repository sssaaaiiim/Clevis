from typing import Literal, Protocol

from app.core.events import Action, Model
from app.core.state import RunRecord


class Verdict(Model):
    verdict: Literal["allow", "deny", "approval"]
    reason: str


class ActionValidator(Protocol):
    async def validate(self, run_state: RunRecord, action: Action) -> Verdict: ...


class AllowAllValidator:
    # TODO Phase 2: policy tiers, domain allowlist, approvals
    async def validate(self, run_state: RunRecord, action: Action) -> Verdict:
        return Verdict(verdict="allow", reason="Allowed by the fake-only policy.")
