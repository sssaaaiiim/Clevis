"""Shared exact event expectations for successful scripted agent runs."""

ACTION_EVENTS = (
    "observation.summary",
    "step.proposed",
    "step.validated",
    "step.executed",
    "budget.update",
)


def successful_run_events(action_count: int) -> list[str]:
    return ["run.started", "plan.created", *ACTION_EVENTS * action_count, "run.finished"]
