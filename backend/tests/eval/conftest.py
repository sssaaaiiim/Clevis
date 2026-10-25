import asyncio
from collections.abc import AsyncIterator, Callable, Generator
from typing import Any, cast

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.browser.playwright_driver import PlaywrightDriver
from app.core.events import Action, Event, Plan
from app.main import create_app
from tests.eval.eval_recorder import append_result
from tests.eval.scenarios.base import EvalScenario
from tests.scripted_browser_llm import ObservedScriptLLM
from tests.settings import IsolatedSettings
from tests.test_outcome_graph import ScriptVerifier


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[Any]
) -> Generator[None, Any, None]:
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and not report.skipped:
        data = getattr(item, "eval_data", {"scenario": item.name})
        append_result(data, report.passed)


class EvalRun:
    def __init__(self, app: Any, client: AsyncClient, record: dict[str, Any]) -> None:
        self.app, self.client, self.record = app, client, record
        self.run_id = ""
        self.tokens: dict[str, str] = {}

    async def start(self, scenario: EvalScenario) -> None:
        response = await self.client.post(
            "/api/runs",
            json={
                "goal": scenario.goal,
                "mode": "headless",
                "permissions": scenario.permissions.model_dump(exclude_none=True),
            },
        )
        assert response.status_code == 201
        self.tokens = response.json()
        self.run_id = self.tokens["runId"]

    async def events(self) -> list[Event]:
        return cast(list[Event], await self.app.state.service.store.list_events(self.run_id))

    async def pending(self) -> str:
        async with asyncio.timeout(8):
            while True:
                snapshot = await agent_graph.aget_state(
                    {"configurable": {"thread_id": self.run_id}}
                )
                for event in reversed(await self.events()):
                    if event.type == "approval.required" and snapshot.interrupts:
                        return str(event.data.approval_id)
                await asyncio.sleep(0.005)

    async def decide(
        self, decision: str, approval_id: str | None = None, *, auth: bool = True
    ) -> Any:
        return await self.client.post(
            f"/api/runs/{self.run_id}/{decision}",
            json={"approval_id": approval_id or await self.pending()},
            headers={"Authorization": "Bearer " + self.tokens["approvalToken"]} if auth else {},
        )

    async def finish(self, scenario: EvalScenario) -> AgentState:
        task = self.app.state.service.tasks.get(self.run_id)
        if task:
            await asyncio.wait_for(asyncio.shield(task), 8)
        snapshot = await agent_graph.aget_state({"configurable": {"thread_id": self.run_id}})
        state = AgentState.model_validate(snapshot.values)
        events = [e.type for e in await self.events()]
        matched, assertions = scenario.check(state, events)
        assertions = [
            state.status == scenario.expected_outcome,
            state.budget.steps_used > 0,
            *assertions,
        ]
        self.record.update(
            events_matched=matched,
            assertions_passed=assertions,
            steps=state.budget.steps_used,
            tokens=state.budget.tokens_used,
            cost_usd=state.budget.cost_usd,
        )
        assert matched and all(assertions)
        assert state.status == scenario.expected_outcome
        return state


@pytest.fixture
async def evaluate(request: pytest.FixtureRequest) -> AsyncIterator[Callable[..., Any]]:
    resources: list[Any] = []
    data: dict[str, Any] = {"scenario": request.node.name}
    request.node.eval_data = data

    async def create(
        actions: list[Action],
        *,
        outcomes: list[bool] | None = None,
        settings: IsolatedSettings | None = None,
        plan: Plan | None = None,
        driver_factory: Callable[[], PlaywrightDriver] | None = None,
    ) -> EvalRun:
        options = settings or IsolatedSettings()
        app = create_app(
            options,
            driver_factory=driver_factory or (lambda: PlaywrightDriver(options)),
            llm_factory=lambda: ObservedScriptLLM(actions=actions, plan=plan, delay=0),
            outcome_llm_factory=(lambda: ScriptVerifier(outcomes)) if outcomes else None,
        )
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        resources.append((client, lifespan))
        return EvalRun(app, client, data)

    yield create
    for client, lifespan in reversed(resources):
        await client.aclose()
        await lifespan.__aexit__(None, None, None)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # A key being set is not authorization to incur charges during a normal suite.
    if "live_eval" not in config.option.markexpr:
        for item in items:
            if item.get_closest_marker("live_eval"):
                item.add_marker(
                    pytest.mark.skip(reason="Paid evaluations require explicit -m live_eval.")
                )
