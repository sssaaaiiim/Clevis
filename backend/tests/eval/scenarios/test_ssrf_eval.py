from typing import Any

import pytest

from app.browser.network import NavigationMonitor
from app.browser.playwright_driver import PlaywrightDriver
from app.core.events import Action, Target
from tests.eval.scenarios.base import EvalScenario
from tests.eval.scenarios.test_policy_eval import done, navigate
from tests.settings import IsolatedSettings


@pytest.mark.parametrize(
    "name,mode,strict,domain",
    [
        ("JsRedirectBlocked", "js", False, "127.0.0.1"),
        ("MetaRefreshBlocked", "meta", False, "192.168.1.1"),
        ("FormRedirectBlocked", "form", False, "10.0.0.1"),
        ("StrictModeFailsRun", "js", True, "127.0.0.1"),
        ("NonStrictModeWarns", "js", False, "127.0.0.1"),
    ],
)
async def test_ssrf_scenarios(
    name: str, mode: str, strict: bool, domain: str, testsite: str, evaluate: Any
) -> None:
    options = IsolatedSettings(ssrf_strict_mode=strict)

    class FixtureDriver(PlaywrightDriver):
        def configure_navigation_monitor(self, monitor: NavigationMonitor, on_block: Any) -> None:
            monitor.settings = options.model_copy(update={"block_private_network": True})
            original = monitor.warning

            async def warning(url: str, *, fresh: bool = False) -> str | None:
                return None if url.startswith(testsite + "/") else await original(url, fresh=fresh)

            monitor.warning = warning  # type: ignore[method-assign]
            super().configure_navigation_monitor(monitor, on_block)

    target = (
        "JS redirect"
        if mode == "js"
        else "Meta refresh"
        if mode == "meta"
        else "Submit private form"
    )
    actions = [
        navigate(testsite + "/ssrf-redirect.html"),
        Action(action="click", target=Target(description=target), rationale="Test redirect."),
        Action(action="wait", value=".5", rationale="Wait for guard."),
        done(),
    ]
    scenario = EvalScenario(
        goal="Exercise local redirect safety",
        expected_outcome="failed" if strict else "finished",
        expected_events=["run.started", "observation.summary"],
    )
    run = await evaluate(actions, settings=options, driver_factory=lambda: FixtureDriver(options))
    await run.start(scenario)
    state = await run.finish(scenario)
    assert domain in state.ssrf_blocks
    assert all(":" not in host and "/" not in host for host in state.ssrf_blocks)
    warnings = [e for e in await run.events() if e.type == "observation.summary" and e.data.warning]
    assert warnings and warnings[0].data.warning == "SSRF redirect blocked"
    if strict:
        assert state.error == "SSRF: navigation to private address blocked"
