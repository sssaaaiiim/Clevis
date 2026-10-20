"""Small async steps; the runner owns sequencing, cancellation and event emission."""

from pydantic import Field

from app.agent.prompts import actor_messages, plan_messages
from app.agent.state import AgentState
from app.core.events import Action, Plan, PlanStep
from app.core.state import RunRecord
from app.interfaces.browser import ActionResult, BrowserDriver, Observation
from app.interfaces.llm import LLMClient, LLMOutputError, LLMResponse
from app.interfaces.validator import ActionValidator, Verdict


class PlannerPlan(Plan):
    steps: list[PlanStep] = Field(min_length=1, max_length=6)


async def plan(llm: LLMClient, goal: str) -> LLMResponse[Plan]:
    response = await llm.propose(plan_messages(goal), PlannerPlan)
    if not 1 <= len(response.parsed.steps) <= 6:
        raise LLMOutputError("Planner must return 1–6 steps.", response.usage)
    return LLMResponse(
        parsed=Plan.model_validate(response.parsed.model_dump()),
        tokens_used=response.tokens_used,
        usage=response.usage,
    )


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
