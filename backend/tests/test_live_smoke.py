"""Explicit opt-in only: pytest -m live; needs a key and configured primary model."""

import asyncio
import os
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app
from app.runtime import RunService
from tests.smoke_cases import SMOKE_CASES, SmokeCase


@pytest.mark.live
@pytest.mark.parametrize("case", SMOKE_CASES, ids=lambda case: case.name)
async def test_openrouter_smoke(testsite: str, case: SmokeCase) -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("Set OPENROUTER_API_KEY for live model tests.")
    settings = Settings(llm_provider="openrouter", browser_driver="playwright")
    if not settings.llm_model_primary:
        pytest.skip("Set LLM_MODEL_PRIMARY for live model tests.")
    application = create_app(settings)
    service = cast(RunService, application.state.service)
    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            created = await client.post(
                "/api/runs",
                json={
                    "goal": case.goal.format(base=testsite),
                    "mode": "headless",
                },
            )
            assert created.status_code == 201
            run_id = created.json()["runId"]
            task = service.tasks[run_id]
            async with asyncio.timeout(settings.max_seconds + 5):
                streamed = await client.get(f"/api/runs/{run_id}/events")
                await task
            record = await service.store.get(run_id)
            diagnostic = [
                (e.data.stepId, e.data.action, e.data.target.ref)
                for e in await service.store.list_events(run_id)
                if e.type == "step.proposed"
            ]
            failures = [
                e.data.resultSummary
                for e in await service.store.list_events(run_id)
                if e.type == "step.executed" and not e.data.ok
            ]
            assert record.status == "finished", (record.error, diagnostic, failures)
            assert record.result is not None
            for expected in case.expected:
                assert expected.lower() in record.result.lower(), "Result differs from demo data."
            events = await service.store.list_events(run_id)
            assert events[-1].type == "run.finished"
            assert [event.seq for event in events] == list(range(1, len(events) + 1))
            assert "event: run.finished" in streamed.text
            assert "step.proposed" in streamed.text and "budget.update" in streamed.text
