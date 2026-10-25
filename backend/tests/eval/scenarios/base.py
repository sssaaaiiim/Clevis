from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from app.agent.policy.permissions import RunPermissions
from app.agent.state import AgentState
from app.core.events import Action


@dataclass
class EvalScenario:
    goal: str
    permissions: RunPermissions = field(default_factory=RunPermissions)
    scripted_llm_actions: list[Action] = field(default_factory=list)
    expected_events: Sequence[str] = field(default_factory=list)
    expected_outcome: Literal["finished", "failed", "stopped", "approval_required"] = "finished"
    assertions: list[Callable[[AgentState], bool]] = field(default_factory=list)

    def check(self, state: AgentState, events: Sequence[str]) -> tuple[bool, list[bool]]:
        # Ordered milestones allow budget/observation events between boundaries.
        remaining = iter(events)
        matched = all(
            any(actual == expected for actual in remaining) for expected in self.expected_events
        )
        return matched, [assertion(state) for assertion in self.assertions]
