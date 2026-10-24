from typing import Any

from app.agent import steps
from app.agent.context import current_context, node
from app.agent.state import AgentState, SubGoal
from app.core.events import EventType, Plan, PlanStep, make_event
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
    completed_goals = [g for g in state.sub_goals if g.status == "completed"]
    first_id = max((goal.id for goal in completed_goals), default=0) + 1
    state.sub_goals = completed_goals + [
        SubGoal(
            id=first_id + index,
            description=step.text,
            success_condition=step.text,
            max_steps=context.options.subgoal_max_steps,
            max_attempts=context.options.subgoal_max_attempts,
        )
        for index, step in enumerate(response.parsed.steps)
    ]
    state.plan = Plan(steps=[PlanStep(id=g.id, text=g.description) for g in state.sub_goals])
    state.current_sub_goal_idx = len(completed_goals)
    state.planner_revision = None
    state.reroute = False
    if (await context.store.get(state.run_id)).status == RunStatus.PLANNING:
        await context.machine.transition(RunStatus.RUNNING, plan=state.plan)
    else:
        await context.execution.publish(
            make_event(
                state.run_id,
                EventType.PLAN_CREATED,
                state.plan,
            )
        )
    state.status = "running"
    return context.sync(state)
