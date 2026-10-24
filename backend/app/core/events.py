from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


Mode = Literal["headed", "headless"]


class Target(Model):
    ref: str | None = None
    description: str | None = None


class Action(Model):
    action: Literal[
        "click", "type", "navigate", "scroll", "extract", "wait", "done", "handoff", "revise"
    ]
    target: Target = Field(default_factory=Target)
    value: str | None = None
    rationale: str = Field(min_length=1, max_length=300)
    plan_step_id: int | None = Field(default=None, ge=1)


class PlanStep(Model):
    id: int = Field(ge=1)
    text: str = Field(min_length=1)


class Plan(Model):
    steps: list[PlanStep] = Field(min_length=1)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    PLAN_CREATED = "plan.created"
    STEP_PROPOSED = "step.proposed"
    STEP_EXECUTED = "step.executed"
    OBSERVATION_SUMMARY = "observation.summary"
    BUDGET_UPDATE = "budget.update"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    RUN_FINISHED = "run.finished"
    RUN_FAILED = "run.failed"
    RUN_STOPPED = "run.stopped"
    STEP_VALIDATED = "step.validated"
    APPROVAL_REQUIRED = "approval.required"


ActionKind = Literal[
    "click", "type", "navigate", "scroll", "extract", "wait", "done", "handoff", "revise"
]


class StartedData(Model):
    goal: str
    mode: Mode


class ProposedData(Model):
    stepId: int = Field(ge=1)
    planStepId: int | None
    action: ActionKind
    target: Target
    value: str | None
    rationale: str = Field(min_length=1, max_length=300)


class ExecutedData(Model):
    stepId: int = Field(ge=1)
    ok: bool
    resultSummary: str


class ObservationData(Model):
    stepId: int = Field(ge=1)
    summary: str = Field(max_length=1000)


class BudgetData(Model):
    stepsUsed: int = Field(ge=0)
    maxSteps: int = Field(ge=1)
    secondsUsed: float = Field(ge=0, allow_inf_nan=False)
    maxSeconds: float = Field(gt=0, allow_inf_nan=False)
    tokensUsed: int = Field(ge=0)
    maxTokens: int = Field(ge=1)

    promptTokens: int = Field(default=0, ge=0)
    completionTokens: int = Field(default=0, ge=0)
    costUsd: float = Field(default=0, ge=0, allow_inf_nan=False)
    maxCostUsd: float = Field(default=0.50, ge=0, allow_inf_nan=False)
    costEstimated: bool = False


class ApprovalRequest(Model):
    action_summary: str = Field(max_length=300)
    risk: Literal["low", "medium", "high"]
    page_url: str


class ApprovalPausedData(Model):
    reason: Literal["approval"] = "approval"
    request: ApprovalRequest


class ReasonData(Model):
    reason: str


class HandoffData(Model):
    reason: Literal["handoff"] = "handoff"
    message: str = Field(max_length=300)


class FinishedData(Model):
    result: str


class FailedData(Model):
    error: str


class EmptyData(Model):
    pass


class ValidatedData(Model):
    stepId: int = Field(ge=1)
    verdict: Literal["allow", "deny", "approval"]
    reason: str


class ApprovalData(Model):
    stepId: int = Field(ge=1)
    action: Action
    risk: str


class EventBase(Model):
    runId: str = Field(min_length=1)
    seq: int = Field(default=1, ge=1)
    ts: str = Field(default_factory=utc_now)

    @field_validator("ts")
    @classmethod
    def utc_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() != UTC.utcoffset(None):
            raise ValueError("timestamp must be ISO 8601 UTC")
        return value


class RunStarted(EventBase):
    type: Literal["run.started"] = "run.started"
    data: StartedData


class PlanCreated(EventBase):
    type: Literal["plan.created"] = "plan.created"
    data: Plan


class StepProposed(EventBase):
    type: Literal["step.proposed"] = "step.proposed"
    data: ProposedData


class StepExecuted(EventBase):
    type: Literal["step.executed"] = "step.executed"
    data: ExecutedData


class ObservationSummary(EventBase):
    type: Literal["observation.summary"] = "observation.summary"
    data: ObservationData


class BudgetUpdate(EventBase):
    type: Literal["budget.update"] = "budget.update"
    data: BudgetData


class RunPaused(EventBase):
    type: Literal["run.paused"] = "run.paused"
    data: ApprovalPausedData | HandoffData | ReasonData


class RunResumed(EventBase):
    type: Literal["run.resumed"] = "run.resumed"
    data: ReasonData


class RunFinished(EventBase):
    type: Literal["run.finished"] = "run.finished"
    data: FinishedData


class RunFailed(EventBase):
    type: Literal["run.failed"] = "run.failed"
    data: FailedData


class RunStopped(EventBase):
    type: Literal["run.stopped"] = "run.stopped"
    data: EmptyData


class StepValidated(EventBase):
    type: Literal["step.validated"] = "step.validated"
    data: ValidatedData


class ApprovalRequired(EventBase):
    type: Literal["approval.required"] = "approval.required"
    data: ApprovalData


Event = Annotated[
    RunStarted
    | PlanCreated
    | StepProposed
    | StepExecuted
    | ObservationSummary
    | BudgetUpdate
    | RunPaused
    | RunResumed
    | RunFinished
    | RunFailed
    | RunStopped
    | StepValidated
    | ApprovalRequired,
    Field(discriminator="type"),
]
EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(cast(Any, Event))

TERMINAL_EVENTS = {EventType.RUN_FINISHED, EventType.RUN_FAILED, EventType.RUN_STOPPED}


def make_event(run_id: str, kind: EventType, data: BaseModel) -> Event:
    """Create an event draft; the emitter assigns its final sequence and timestamp."""
    return EVENT_ADAPTER.validate_python({"runId": run_id, "type": kind, "data": data.model_dump()})
