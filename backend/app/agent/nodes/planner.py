from typing import Any

from app.agent import steps
from app.agent.context import current_context, node
from app.agent.state import AgentState, SubGoal
from app.core.events import EventType, make_event
from app.core.state import RunStatus


@node
async def planner_node(state: AgentState) -> dict[str, Any]:
    context = current_context.get()
    goal = state.goal
    if state.planner_revision:
        completed = [g.description for g in state.sub_goals if g.status == "completed"]
        goal += (
            "\nReplan only the remaining work. Completed sub-goals: "
            + repr(completed)
            + "\nPlanner feedback: "
            + context.execution.safe_text(state.planner_revision)
        )
    response = await context.execution.call(steps.plan, context.llm, goal)
    state.budget.add_usage(response.usage, response.tokens_used)
    state.plan = response.parsed
    completed_goals = [g for g in state.sub_goals if g.status == "completed"]
    state.sub_goals = completed_goals + [
        SubGoal(
            id=step.id,
            description=step.text,
            success_condition=step.text,
            max_steps=context.options.subgoal_max_steps,
            max_attempts=context.options.subgoal_max_attempts,
        )
        for step in response.parsed.steps
    ]
    state.current_sub_goal_idx = len(completed_goals)
    state.planner_revision = None
    state.reroute = False
    if (await context.store.get(state.run_id)).status == RunStatus.PLANNING:
        await context.machine.transition(RunStatus.RUNNING, plan=response.parsed)
    else:
        await context.execution.publish(
            make_event(
                state.run_id,
                EventType.PLAN_CREATED,
                response.parsed,
            )
        )
    state.status = "running"
    return context.sync(state)
