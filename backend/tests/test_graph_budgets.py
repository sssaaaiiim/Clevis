import pytest

from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.core.budgets import Budget
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from tests.test_runner import Harness


@pytest.mark.parametrize(
    "budget,delay,limit",
    [
        (Budget(max_steps=1), 0, "MAX_STEPS"),
        (Budget(max_tokens=1), 0, "MAX_TOKENS"),
        (Budget(max_seconds=0.001), 0.02, "MAX_SECONDS"),
    ],
)
async def test_budget_failure_checkpoints_terminal_state(
    budget: Budget,
    delay: float,
    limit: str,
) -> None:
    h = Harness(budget=budget, driver=FakeBrowserDriver(delay=delay), llm=FakeLLMClient(delay=0))
    await h.start()
    await h.task
    record = await h.store.get(h.run_id)
    assert record.status == "failed" and record.error and limit in record.error
    snapshot = await agent_graph.aget_state({"configurable": {"thread_id": h.run_id}})
    state = AgentState.model_validate(snapshot.values)
    assert state.status == "failed" and state.error == record.error
    assert state.budget.steps_used == budget.steps_used
    assert state.budget.tokens_used == budget.tokens_used
    assert not snapshot.next
    assert h.driver.closed
