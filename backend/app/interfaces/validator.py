from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import Field, model_validator

from app.core.events import Action, Model
from app.core.events import ApprovalRequest as ApprovalRequest
from app.core.state import RunRecord

if TYPE_CHECKING:
    from app.agent.state import AgentState


class Verdict(Model):
    verdict: Literal["allow", "deny", "approval"]
    reason: str = ""
    tier: int = Field(default=0, ge=0, le=3)
    display: ApprovalRequest | None = None

    @model_validator(mode="before")
    @classmethod
    def decision_input(cls, value: Any) -> Any:
        if isinstance(value, dict) and "decision" in value:
            value = dict(value)
            decision = value.pop("decision")
            value["verdict"] = "approval" if decision == "approve" else decision
        return value

    @property
    def decision(self) -> Literal["allow", "approve", "deny"]:
        return "approve" if self.verdict == "approval" else self.verdict


class ActionValidator(Protocol):
    async def validate(self, run_state: RunRecord, action: Action) -> Verdict: ...


@runtime_checkable
class StateActionValidator(Protocol):
    async def validate_agent(self, state: "AgentState", action: Action) -> Verdict: ...


@runtime_checkable
class NetworkPolicy(Protocol):
    async def guard_url(self, url: str, navigation: bool) -> None: ...
    def authorize_destination(self, state: "AgentState", action: Action) -> None: ...


class AllowAllValidator:
    # TODO Phase 2: policy tiers, domain allowlist, approvals
    async def validate(self, run_state: RunRecord, action: Action) -> Verdict:
        return Verdict(verdict="allow", reason="Allowed by the placeholder policy.")
