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


def verification_handoff(action: Action, observation: Observation) -> Action:
    """A known interactive verification page needs a human rather than repeated waiting."""
    if action.action != "wait":
        return action
    phrases = ("verify you are human", "verify that you are human", "i am not a robot")
    checkbox = any(
        element.role == "checkbox" and any(p in element.name.lower() for p in phrases)
        for element in observation.elements
    )
    text = " ".join(observation.text_excerpt.lower().split())
    challenge = observation.title.strip().lower().startswith("just a moment") and (
        "performing security verification" in text or any(p in text for p in phrases)
    )
    if not checkbox and not challenge:
        return action
    return Action(
        action="handoff",
        value="Please complete the browser's human verification, then click Resume agent.",
        rationale="Human verification needs your control instead of repeated waiting.",
        plan_step_id=action.plan_step_id,
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
