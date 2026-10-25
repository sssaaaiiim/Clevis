"""Keep a content-free terminal diagnostic snapshot, not the run's page history."""

from dataclasses import asdict
from typing import Any

from app.agent.context import RunContext
from app.agent.graph import agent_graph, checkpointer
from app.agent.state import AgentState, BudgetState
from app.core.state import RunRecord


async def retain_terminal_summary(record: RunRecord, context: RunContext) -> None:
    config: Any = {"configurable": {"thread_id": record.runId}}
    snapshot = await agent_graph.aget_state(config)
    state = AgentState.model_validate(snapshot.values or {"goal": ""})
    state.run_id = record.runId
    state.goal = ""
    state.mode = record.mode
    state.status = record.status.value
    # Public final answer/error remain available for existing diagnostics; page dumps,
    # action values and interrupted approval payloads do not belong in terminal history.
    state.result = context.execution.safe_text(record.result) if record.result else None
    state.error = context.execution.safe_text(record.error) if record.error else None
    state.budget = BudgetState(**asdict(context.execution.budget))
    state.permissions = record.permissions
    state.ssrf_blocks = list(context.ssrf_blocks)
    state.last_observation = None
    state.last_action = None
    state.last_action_result = None
    state.validator_verdict = None
    state.outcome_verdict = None
    state.planner_revision = None
    state.pending_approval = None
    state.pending_approval_id = None
    state.candidate_result = None
    state.plan = None
    state.reroute = False
    for goal in state.sub_goals:
        goal.description = "Completed sub-goal" if goal.status == "completed" else "Sub-goal"
        goal.success_condition = "Not retained after run end."
    for step in state.step_history:
        step.target_desc = ""
        step.result_summary = "Action succeeded." if step.ok else "Action did not succeed."
    for history in state.history:
        history.target_name = ""
        history.summary = "Action succeeded." if history.ok else "Action did not succeed."
    # Updating the latest checkpoint alone leaves old values and interrupt/error writes
    # reachable through alist(). Delete the entire thread before seeding the safe summary.
    await checkpointer.adelete_thread(record.runId)
    await agent_graph.aupdate_state(config, state.model_dump(mode="json"), as_node="finish")
    context.machine.pending_approval_id = None
