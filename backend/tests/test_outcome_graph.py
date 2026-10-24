import asyncio

import pytest

from app.agent.graph import agent_graph
from app.agent.revisions import build_revision_message
from app.agent.routing import after_outcome, after_revise
from app.agent.runner import run_agent
from app.agent.state import AgentState, OutcomeVerdict, StepRecord, SubGoal
from app.core.budgets import Budget
from app.core.emitter import FanoutEventEmitter
from app.core.events import Action, Plan, PlanStep
from app.core.state import RunStateMachine
from app.core.store import InMemoryRunStore
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.llm import LLMResponse, Message, T, Usage
from app.interfaces.skills import EmptySkillProvider
from app.interfaces.validator import AllowAllValidator
from tests.settings import PolicySettings


class ScriptVerifier(FakeLLMClient):
    def __init__(self, answers: list[bool]) -> None:
        super().__init__(delay=0)
        self.answers = iter(answers)
        self.calls = 0

    async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
        self.calls += 1
        return LLMResponse(
            parsed=schema.model_validate(
                {
                    "achieved": next(self.answers),
                    "reason": "Expected confirmation was checked.",
                }
            ),
            tokens_used=7,
            usage=Usage(prompt_tokens=5, completion_tokens=2),
        )


async def exercise(
    actions: list[Action], verifier: ScriptVerifier, *, goals: int = 1, max_steps: int = 8
) -> tuple[InMemoryRunStore, str]:
    store = InMemoryRunStore()
    record = await store.create("Complete demo sub-goals", "headless")
    emitter = FanoutEventEmitter(store)
    machine = RunStateMachine(record.runId, store, emitter)
    actor = FakeLLMClient(
        actions=actions,
        plan=Plan(steps=[PlanStep(id=i + 1, text=f"Complete part {i + 1}") for i in range(goals)]),
        delay=0,
    )
    await asyncio.wait_for(
        run_agent(
            record.runId,
            store=store,
            emitter=emitter,
            machine=machine,
            driver=FakeBrowserDriver(delay=0),
            llm=actor,
            outcome_llm=verifier,
            validator=AllowAllValidator(),
            skills=EmptySkillProvider(),
            budget=Budget(),
            settings=PolicySettings(subgoal_max_steps=max_steps),
        ),
        3,
    )
    return store, record.runId


def done() -> Action:
    return Action(action="done", value="Demo completed", rationale="Complete sub-goal.")


async def test_verified_subgoals_complete_and_count_verifier_usage() -> None:
    verifier = ScriptVerifier([True, True])
    store, run_id = await exercise([done(), done()], verifier, goals=2)
    record = await store.get(run_id)
    assert record.status == "finished" and record.result == "Demo completed"
    snapshot = await agent_graph.aget_state({"configurable": {"thread_id": run_id}})
    assert all(g["status"] == "completed" for g in snapshot.values["sub_goals"])
    assert verifier.calls == 2 and snapshot.values["budget"]["tokens_used"] == 44


async def test_one_failed_check_revises_then_retries_with_fresh_observation() -> None:
    verifier = ScriptVerifier([False, True])
    store, run_id = await exercise([done(), done()], verifier)
    assert (await store.get(run_id)).status == "finished"
    events = await store.list_events(run_id)
    revisions = [e for e in events if e.type == "step.proposed" and e.data.action == "revise"]
    assert len(revisions) == 1 and revisions[0].data.value is None
    assert verifier.calls == 2


async def test_subgoal_step_limit_triggers_one_check_not_per_action() -> None:
    verifier = ScriptVerifier([True])
    actions = [Action(action="scroll", value="down", rationale="Read more.")]
    store, run_id = await exercise(actions, verifier, max_steps=1)
    assert (await store.get(run_id)).status == "finished" and verifier.calls == 1


async def test_two_failures_replan_remaining_work_then_finish_partial_at_limit() -> None:
    verifier = ScriptVerifier([False, False, False])
    store, run_id = await exercise([done(), done(), done()], verifier)
    record = await store.get(run_id)
    assert record.status == "finished" and record.result and "Partial result" in record.result
    assert sum(e.type == "plan.created" for e in await store.list_events(run_id)) == 2


def test_revision_is_bounded_and_never_echoes_page_or_target_content() -> None:
    canary = "PRIVATE-PAGE-CANARY"
    goal = SubGoal(id=2, description="Read", success_condition="Read")
    history = [
        StepRecord(
            step_id=1,
            action="type",
            target_desc=canary,
            result_summary=canary,
            value_hash="a" * 64,
            ok=True,
            ts="test",
        )
    ]
    revision = build_revision_message(goal, canary, history, 1)
    assert len(revision) <= 300 and "Sub-goal 2" in revision and "type" in revision
    assert canary not in revision and "a" * 64 not in revision


@pytest.mark.parametrize("attempts,route", [(1, "navigator"), (2, "planner")])
def test_revision_routes(attempts: int, route: str) -> None:
    assert (
        after_revise(
            AgentState(goal="Test", current_sub_goal_attempts=attempts, planner_revision="Retry")
        )
        == route
    )


def test_failed_outcome_at_max_routes_to_finish() -> None:
    assert (
        after_outcome(
            AgentState(
                goal="Test",
                sub_goals=[
                    SubGoal(
                        id=1,
                        description="Test",
                        success_condition="Test",
                        max_attempts=2,
                    )
                ],
                current_sub_goal_attempts=2,
                outcome_verdict=OutcomeVerdict(achieved=False),
            )
        )
        == "finish"
    )
