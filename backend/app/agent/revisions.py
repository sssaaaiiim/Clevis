"""Planner feedback uses fixed categories, never page-derived prose or target names."""

from app.agent.state import StepRecord, SubGoal


def build_revision_message(
    sub_goal: SubGoal,
    outcome_reason: str,
    last_steps: list[StepRecord],
    attempts: int,
) -> str:
    reason = "The success condition was not verified."
    lower = outcome_reason.lower()
    if "confirm" in lower:
        reason = "Expected confirmation was not verified."
    elif "navigat" in lower or "destination" in lower:
        reason = "The intended destination was not verified."
    elif "verifier failed" in lower:
        reason = "The verifier could not establish the outcome."
    action = last_steps[-1].action if last_steps else "none"
    if action not in {"click", "type", "navigate", "scroll", "extract", "wait", "done", "handoff"}:
        action = "other"
    return (
        f"Sub-goal {sub_goal.id} failed after {attempts} attempt(s): {reason} "
        f"Last action: {action}. Try a different approach."
    )[:300]
