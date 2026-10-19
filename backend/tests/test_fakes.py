import pytest

from app.core.events import Action, Plan
from app.fakes.fake_driver import FakeBrowserDriver
from app.fakes.fake_llm import FakeLLMClient
from app.interfaces.browser import BrowserDriver
from app.interfaces.llm import LLMClient
from app.interfaces.skills import EmptySkillProvider
from app.interfaces.validator import AllowAllValidator
from app.core.state import RunRecord


async def test_fakes_implement_interfaces() -> None:
    driver: BrowserDriver = FakeBrowserDriver(delay=0)
    llm: LLMClient = FakeLLMClient(delay=0)
    await driver.start("headless")
    await driver.navigate("https://example.test")
    assert (await driver.observe()).url == "https://example.test"
    assert (await llm.propose([], Plan)).parsed.steps
    actions = [(await llm.propose([], Action)).parsed for _ in range(3)]
    assert actions[-1].action == "done"
    run = RunRecord(runId="r", goal="test", mode="headless")
    for action in actions:
        assert (await AllowAllValidator().validate(run, action)).verdict == "allow"
        assert (await driver.act(action)).ok
    assert await driver.get_text()
    assert await EmptySkillProvider().get_skills("test", "about:blank") == []
    await driver.close()
    with pytest.raises(RuntimeError, match="exhausted"):
        await llm.propose([], Action)


async def test_injected_driver_failure() -> None:
    driver = FakeBrowserDriver(delay=0, fail_on="observe")
    with pytest.raises(RuntimeError, match="Injected"):
        await driver.observe()
