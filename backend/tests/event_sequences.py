"""Shared exact event expectations for successful scripted agent runs."""

ACTION_EVENTS = (
    "observation.summary",
    "step.proposed",
    "step.validated",
    "step.executed",
    "budget.update",
)


def successful_run_events(
    action_count: int, *, verified_after: tuple[int, ...] | None = None
) -> list[str]:
    boundaries = (action_count,) if verified_after is None else verified_after
    events = ["run.started", "plan.created"]
    for step in range(1, action_count + 1):
        events.extend(ACTION_EVENTS)
        if step in boundaries:
            events.append("budget.update")
    return [*events, "run.finished"]
