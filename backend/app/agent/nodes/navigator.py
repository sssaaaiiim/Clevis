from typing import Any
from urllib.parse import urlsplit

from app.agent import steps
from app.agent.context import action_signature, current_context, node, private_action
from app.agent.execution import AgentFailure
from app.agent.state import AgentState
from app.browser.safety import SECRET_PATTERN
from app.core.budgets import BudgetExceeded
from app.core.events import EventType, ObservationData, ProposedData, make_event


@node
async def navigator_node(state: AgentState) -> dict[str, Any]:
    context = current_context.get()
    execution, budget = context.execution, state.budget
    if budget.steps_used >= budget.max_steps:
        raise BudgetExceeded(f"MAX_STEPS exceeded after {budget.steps_used} steps.")
    state.reroute = False
    state.turn_epoch = context.machine.resume_count
    observation = context.machine.input_privacy.observation(
        await execution.call(steps.observe, context.driver)
    )
    context.observation = observation
    visible = {e.value for e in observation.elements if e.value and e.value != "[redacted]"}
    execution.public_values.update(execution.typed_values.intersection(visible))
    step_id = budget.steps_used + 1
    path = urlsplit(observation.url).path
    await execution.publish(
        make_event(
            state.run_id,
            EventType.OBSERVATION_SUMMARY,
            ObservationData(
                stepId=step_id,
                summary=execution.safe_text(
                    f"{observation.title[:160]} | {path[:160]} | "
                    f"{len(observation.elements)} elements"
                )[:1000],
            ),
        )
    )
    response = await execution.call(
        steps.propose,
        context.llm,
        state.model_copy(update={"goal": context.goal or state.goal}),
        observation,
        budget.max_steps - budget.steps_used,
        context.options.max_history_steps_in_prompt,
        execution.api_key,
    )
    action = steps.verification_handoff(response.parsed, observation)
    if action.action == "revise":
        raise AgentFailure(
            "Revise is an internal timeline action and cannot be proposed by the actor."
        )
    budget.add_usage(response.usage, response.tokens_used)
    budget.steps_used += 1
    state.sub_goal_steps += 1
    context.action = action
    if action.action == "type" and action.value:
        execution.typed_values.add(action.value)
        target = next((e for e in observation.elements if e.ref == action.target.ref), None)
        if target and (
            target.type == "password"
            or target.value == "[redacted]"
            or SECRET_PATTERN.search(target.name)
        ):
            execution.secret_values.add(action.value)
    context.sync(state)
    if state.turn_epoch != context.machine.resume_count:
        state.reroute = True
        await execution.publish(
            make_event(state.run_id, EventType.BUDGET_UPDATE, budget.event_data())
        )
        return context.sync(state)
    state.current_plan_step = action.plan_step_id
    signature = action_signature(action)
    state.repetitions = state.repetitions + 1 if signature == state.previous_action_hash else 1
    state.previous_action_hash = signature
    state.recent_actions = [
        *state.recent_actions[-4:],
        f"{action.action} {execution.safe_text(action.target.ref or '-')}",
    ]
    if action.action == "handoff":
        state.repetitions = 0
        state.previous_action_hash = None
    if state.repetitions >= 3 and state.stale_attempts == 0 and state.consecutive_denials == 0:
        raise AgentFailure(
            "Loop detected: same action, target and value 3 times in a row. Recent: "
            + "; ".join(state.recent_actions)
        )
    state.last_action = private_action(action, context)
    state.last_observation = context.safe_observation(observation)
    state.last_action_result = None
    state.validator_verdict = None
    await execution.publish(
        make_event(
            state.run_id,
            EventType.STEP_PROPOSED,
            ProposedData(
                stepId=step_id,
                planStepId=action.plan_step_id,
                action=action.action,
                target=state.last_action.target,
                value="[redacted]"
                if action.action == "type" and action.value is not None
                else execution.safe_text(action.value)
                if action.value is not None
                else None,
                rationale=state.last_action.rationale,
            ),
        )
    )
    return context.sync(state)
