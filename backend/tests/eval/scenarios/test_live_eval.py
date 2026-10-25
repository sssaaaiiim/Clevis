"""Explicit billing opt-in only; all browser destinations stay on the fake local site."""

import asyncio
import os
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.config import Settings
from app.main import create_app
from tests.eval.scenarios.base import EvalScenario
from tests.smoke_cases import SMOKE_CASES, SmokeCase


@pytest.mark.live_eval
@pytest.mark.parametrize("case", SMOKE_CASES, ids=lambda case: case.name)
async def test_live_evaluation(
    case: SmokeCase, testsite: str, request: pytest.FixtureRequest
) -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("Set OPENROUTER_API_KEY and explicitly select -m live_eval (paid).")
    settings = Settings(
        llm_provider="openrouter",
        agent_driver="playwright",
        browser_driver="playwright",
        block_private_network=False,
        allowed_domains="127.0.0.1,localhost",
        max_seconds=120,
        require_approval_for_submit=False,
        require_approval_for_send=False,
    )
    if not settings.llm_model_primary:
        pytest.skip("Set LLM_MODEL_PRIMARY for paid evaluations.")
    app = create_app(settings)
    data: dict[str, Any] = {"scenario": "Live-" + case.name}
    request.node.eval_data = data
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/runs", json={"goal": case.goal.format(base=testsite), "mode": "headless"}
            )
            assert response.status_code == 201
            run_id = response.json()["runId"]
            async with asyncio.timeout(125):
                task = app.state.service.tasks.get(run_id)
                if task is not None:
                    await asyncio.shield(task)
            state = AgentState.model_validate(
                (await agent_graph.aget_state({"configurable": {"thread_id": run_id}})).values
            )
            events = [e.type for e in await app.state.service.store.list_events(run_id)]
            scenario = EvalScenario(
                goal=case.goal,
                expected_events=["run.started", "plan.created", "step.validated", "run.finished"],
            )
            matched, _ = scenario.check(state, events)
            checks = [
                state.status == "finished",
                all(s.lower() in (state.result or "").lower() for s in case.expected),
            ]
            data.update(
                events_matched=matched,
                assertions_passed=checks,
                steps=state.budget.steps_used,
                tokens=state.budget.tokens_used,
                cost_usd=state.budget.cost_usd,
            )
            assert matched and all(checks)
