import asyncio
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient

from app.browser.factory import create_browser_driver
from app.browser.playwright_driver import PlaywrightDriver
from app.core.events import EVENT_ADAPTER, Action, Mode, Target
from app.fakes.fake_driver import FakeBrowserDriver
from app.main import create_app
from app.runtime import RunService
from tests.scripted_browser_llm import ObservedScriptLLM, form_script
from tests.settings import IsolatedSettings


def test_factory_selection() -> None:
    assert isinstance(create_browser_driver(IsolatedSettings()), FakeBrowserDriver)
    assert isinstance(
        create_browser_driver(IsolatedSettings(browser_driver="playwright")), PlaywrightDriver
    )


async def run_form(testsite: str, mode: Mode) -> None:
    settings = IsolatedSettings(browser_driver="playwright", max_seconds=45)
    application = create_app(
        settings, llm_factory=lambda: ObservedScriptLLM(actions=form_script(testsite), delay=0)
    )
    service = cast(RunService, application.state.service)
    async with application.router.lifespan_context(application):
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/runs", json={"goal": "Fill the local demo form", "mode": mode}
            )
            assert response.status_code == 201
            run_id = response.json()["runId"]
            response = await client.get(f"/api/runs/{run_id}/events")
            events = [
                EVENT_ADAPTER.validate_json(line[5:].strip())
                for line in response.text.splitlines()
                if line.startswith("data:")
            ]
            assert [e.seq for e in events] == list(range(1, len(events) + 1))
            assert [e.type for e in events] == ["run.started", "plan.created"] + [
                "step.proposed",
                "step.executed",
                "observation.summary",
                "budget.update",
            ] * 7 + ["run.finished"]
            assert (await client.get(f"/api/runs/{run_id}")).json()["status"] == "finished"
            assert "demo@example.test" not in response.text and "Demo Example" not in response.text
        assert service.emitter.subscriber_count == 0
    assert not service.tasks


async def test_real_browser_runner_and_sse(testsite: str) -> None:
    await run_form(testsite, "headless")


@pytest.mark.parametrize("stop", [True, False])
async def test_real_driver_failure_and_stop_cleanup(testsite: str, stop: bool) -> None:
    drivers: list[PlaywrightDriver] = []

    def factory() -> PlaywrightDriver:
        driver = PlaywrightDriver(IsolatedSettings())
        drivers.append(driver)
        return driver

    script = [Action(action="navigate", value=testsite + "/form.html", rationale="Open demo.")]
    if stop:
        script.append(Action(action="wait", value="10", rationale="Wait for operator."))
    else:
        script.append(
            Action(action="click", target=Target(ref="e999999"), rationale="Fail safely.")
        )
    service = RunService(
        IsolatedSettings(), factory, lambda: ObservedScriptLLM(actions=script, delay=0)
    )
    run = await service.create("Test browser cleanup", "headless")
    task = service.tasks[run.runId]
    try:
        if stop:
            async with service.emitter.subscribe(run.runId) as sub:
                async with asyncio.timeout(10):
                    while True:
                        event = await sub.queue.get()
                        if event.type == "step.proposed" and event.data.action == "wait":
                            break
            await asyncio.wait_for(service.stop(run.runId), 2)
        await asyncio.wait_for(task, 10)
        assert (await service.store.get(run.runId)).status == ("stopped" if stop else "failed")
        with pytest.raises(Exception, match="not running"):
            drivers[0].get_context()
    finally:
        await service.shutdown()


async def test_headed_start_error_is_clear_in_run_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.browser.playwright_driver.display_available", lambda: False)
    settings = IsolatedSettings(browser_driver="playwright")
    application = create_app(settings)
    service = cast(RunService, application.state.service)
    async with application.router.lifespan_context(application):
        run = await service.create("Open a headed demo", "headed")
        await asyncio.gather(*list(service.tasks.values()))
        failed = await service.store.get(run.runId)
        assert failed.status == "failed"
        assert failed.error is not None and "requires a display" in failed.error
