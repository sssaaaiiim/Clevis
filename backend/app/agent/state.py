"""Serializable agent state: no browser objects, SDK clients or previous observations."""

from pydantic import Field

from app.core.events import Model, Plan


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
    goal: str
    plan: Plan | None = None
    current_plan_step: int | None = None
    history: list[HistoryStep] = Field(default_factory=list)
    empty_done_attempts: int = 0
    stale_attempts: int = 0
