"""Serializable agent state: no browser objects, SDK clients or previous observations."""

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from app.agent.policy.dataflow import FlowEntry
from app.core.budgets import Budget
from app.core.events import Action, Mode, Model, Plan
from app.interfaces.browser import ActionResult, Observation
from app.interfaces.validator import ApprovalRequest, Verdict


class SubGoal(Model):
    id: int
    description: str
    success_condition: str
    max_steps: int = Field(default=8, ge=1)
    max_attempts: int = Field(default=2, ge=1)
    status: str = "pending"


class StepRecord(Model):
    step_id: int
    sub_goal_id: int | None = None
    action: str
    target_ref: str | None = None
    target_desc: str = ""
    value_hash: str | None = None
    result_summary: str
    ok: bool
    ts: str


@dataclass
class BudgetState(Budget):
    handoffs_used: int = 0


class OutcomeVerdict(Model):
    achieved: bool
    reason: str = Field(default="Success condition verified.", max_length=120)
    confidence: Literal["high", "low"] = "high"


class HistoryStep(Model):
    step_id: int
    action: str
    ref: str | None = None
    target_name: str = ""
    ok: bool
    summary: str

    def compact(self, detailed: bool = True) -> str:
        text = f'step {self.step_id}: {self.action} {self.ref or "-"} "{self.target_name[:80]}" → '
        return text + (
            ("ok" if self.ok else "retry")
            if not detailed
            else ("ok; " if self.ok else "retry; ") + self.summary[:160]
        )


class AgentState(Model):
    run_id: str = ""
    goal: str
    mode: Mode = "headless"
    sub_goals: list[SubGoal] = Field(default_factory=list)
    current_sub_goal_idx: int = 0
    current_sub_goal_attempts: int = 0
    step_history: list[StepRecord] = Field(default_factory=list)
    last_observation: Observation | None = None
    last_action: Action | None = None
    last_action_result: ActionResult | None = None
    validator_verdict: Verdict | None = None
    outcome_verdict: OutcomeVerdict | None = None
    planner_revision: str | None = None
    budget: BudgetState = Field(default_factory=BudgetState)
    status: str = "created"
    result: str | None = None
    error: str | None = None
    reroute: bool = False
    turn_epoch: int = 0
    previous_action_hash: str | None = None
    repetitions: int = 0
    recent_actions: list[str] = Field(default_factory=list)
    progress_fingerprint: str | None = None
    progress_count: int = 0
    sub_goal_steps: int = 0
    # Compatibility for existing prompt callers; the graph keeps these bounded too.
    plan: Plan | None = None
    current_plan_step: int | None = None
    history: list[HistoryStep] = Field(default_factory=list)
    empty_done_attempts: int = 0
    stale_attempts: int = 0
    invalid_action_attempts: int = 0
    data_flow: dict[str, FlowEntry] = Field(default_factory=dict)
    pending_approval: ApprovalRequest | None = None
    pending_approval_id: str | None = None
    consecutive_denials: int = 0
    denial_sub_goal: int | None = None
