from typing import Any

import pytest

from app.agent.context import RunContext, current_context
from app.agent.execution import _Execution
from app.agent.nodes.planner import planner_node
from app.agent.nodes.revise import revise_node
from app.agent.state import AgentState, SubGoal
from app.core.budgets import Budget
from app.core.emitter import FanoutEventEmitter
from app.core.events import Plan, PlanStep
from app.core.state import RunStateMachine, RunStatus
from app.core.store import InMemoryRunStore
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import Observation
from app.interfaces.skills import EmptySkillProvider
from app.interfaces.validator import AllowAllValidator
from tests.settings import IsolatedSettings


@pytest.mark.parametrize("attempts", [0, 1])
async def test_revision_preserves_completed_work_and_bounds_attempts(attempts: int) -> None:
    messages_seen: list[str] = []

    class RecordingLLM(FakeLLMClient):
        async def propose(self, messages: list[Any], schema: Any) -> Any:
            messages_seen.extend(message.content for message in messages)
            return await super().propose(messages, schema)

    store = InMemoryRunStore()
    run = await store.create("Read the remaining page", "headless")
    emitter = FanoutEventEmitter(store)
    machine = RunStateMachine(run.runId, store, emitter)
    await machine.transition(RunStatus.PLANNING)
    await machine.transition(RunStatus.RUNNING, plan=Plan(steps=[PlanStep(id=1, text="Read")]))
    state = AgentState(
        run_id=run.runId,
        goal=run.goal,
        current_sub_goal_idx=1,
        current_sub_goal_attempts=attempts,
        sub_goals=[
            SubGoal(id=7, description="Completed", success_condition="Read", status="completed"),
            SubGoal(id=8, description="Remaining", success_condition="Read", max_attempts=1),
        ],
        last_observation=Observation(text_excerpt="WEBSITE-CANARY-NOT-FOR-PLANNER"),
    )
    context = RunContext(
        store=store,
        emitter=emitter,
        machine=machine,
        driver=FakeBrowserDriver(delay=0),
        llm=RecordingLLM(delay=0),
        validator=AllowAllValidator(),
        skills=EmptySkillProvider(),
        options=IsolatedSettings(subgoal_max_steps=3, subgoal_max_attempts=1),
        external_budget=Budget(),
        execution=_Execution(machine, state.budget, emitter, ""),
    )
    token = current_context.set(context)
    try:
        revised = AgentState.model_validate(await revise_node(state))
        if attempts:
            assert revised.sub_goals[1].status == "failed"
            assert revised.error and revised.current_sub_goal_idx == 2
        else:
            assert revised.planner_revision
            planned = AgentState.model_validate(await planner_node(revised))
            assert planned.sub_goals[0].id == 7 and planned.sub_goals[0].status == "completed"
            assert [g.id for g in planned.sub_goals] == [7, 8, 9]
            assert planned.current_sub_goal_idx == 1 and planned.planner_revision is None
            assert all(g.max_steps == 3 and g.max_attempts == 1 for g in planned.sub_goals[1:])
            assert "Planner feedback:" in "\n".join(messages_seen)
            assert "WEBSITE-CANARY" not in "\n".join(messages_seen)
    finally:
        current_context.reset(token)
