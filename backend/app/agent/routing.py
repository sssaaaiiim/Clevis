"""Pure graph routes: no browser I/O, mutation, logging, or event emission."""

from app.agent.state import AgentState


def after_planner(state: AgentState) -> str:
    return "planner" if state.reroute else "navigator"


def after_navigator(state: AgentState) -> str:
    if state.error:
        return "finish"
    return "navigator" if state.reroute else "policy_check"


def after_policy(state: AgentState) -> str:
    if state.error:
        return "finish"
    if state.reroute:
        return "navigator"
    verdict = state.validator_verdict
    if verdict is None or verdict.verdict == "deny":
        return "navigator"
    return "approval_gate" if verdict.verdict == "approval" else "executor"


def after_approval(state: AgentState) -> str:
    return (
        "executor"
        if not state.reroute
        and state.validator_verdict
        and (state.validator_verdict.verdict == "allow")
        else "navigator"
    )


def after_executor(state: AgentState) -> str:
    return "navigator" if state.reroute else "outcome_check"


def after_outcome(state: AgentState) -> str:
    if state.error or state.result is not None:
        return "finish"
    if state.reroute or state.outcome_verdict is None:
        return "navigator"
    if state.outcome_verdict.achieved:
        return "next_sub_goal"
    goal = state.sub_goals[state.current_sub_goal_idx] if state.sub_goals else None
    return "finish" if goal and state.current_sub_goal_attempts >= goal.max_attempts else "revise"


def after_revise(state: AgentState) -> str:
    if state.error:
        return "finish"
    if state.current_sub_goal_attempts == 1:
        return "navigator"
    return "planner" if state.planner_revision else "navigator"


def after_next(state: AgentState) -> str:
    return "finish" if state.error or state.result is not None else "navigator"


def after_finish(state: AgentState) -> str:
    return "navigator" if state.reroute else "__end__"
