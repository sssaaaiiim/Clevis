"""Small async steps; the runner owns sequencing, cancellation and event emission."""

from app.agent.prompts import actor_messages, plan_messages
from app.agent.state import AgentState
from app.core.events import Action, Plan
from app.core.state import RunRecord
from app.interfaces.browser import ActionResult, BrowserDriver, Observation
from app.interfaces.llm import LLMClient, LLMOutputError, LLMResponse
from app.interfaces.validator import ActionValidator, Verdict


async def plan(llm: LLMClient, goal: str) -> LLMResponse[Plan]:
    response = await llm.propose(plan_messages(goal), Plan)
    if not 1 <= len(response.parsed.steps) <= 6:
        raise LLMOutputError("Planner must return 1–6 steps.", response.usage)
    return response


async def observe(driver: BrowserDriver) -> Observation:
    return await driver.observe()


async def propose(
    llm: LLMClient,
    state: AgentState,
    observation: Observation,
    remaining: int,
    history_limit: int,
    api_key: str,
) -> LLMResponse[Action]:
    return await llm.propose(
        actor_messages(state, observation, remaining, history_limit, api_key), Action
    )


async def validate(
    validator: ActionValidator,
    run: RunRecord,
    action: Action,
) -> Verdict:
    # TODO Phase 2: policy validator. Denials return feedback; they never execute actions.
    return await validator.validate(run, action)


async def act(driver: BrowserDriver, action: Action) -> ActionResult:
    return await driver.act(action)


def check_done(action: Action, result: ActionResult) -> bool:
    return action.action == "done" and bool((action.value or "").strip()) and result.ok
