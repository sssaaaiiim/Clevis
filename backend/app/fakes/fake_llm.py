import asyncio

from app.core.events import Action, Plan, PlanStep, Target
from app.interfaces.llm import LLMResponse, Message, T, Usage


class FakeLLMClient:
    def __init__(
        self, *, actions: list[Action] | None = None, plan: Plan | None = None, delay: float = 0.05
    ) -> None:
        self.delay = delay
        self.plan = plan or Plan(
            steps=[
                PlanStep(id=1, text="Open the sample page."),
                PlanStep(id=2, text="Read the result and finish."),
            ]
        )
        self.actions = (
            actions
            if actions is not None
            else [
                Action(
                    action="navigate",
                    value="https://example.test",
                    rationale="Open the sample page.",
                    plan_step_id=1,
                ),
                Action(
                    action="extract",
                    target=Target(ref="result", description="Sample result"),
                    rationale="Read the result needed for the goal.",
                    plan_step_id=2,
                ),
                Action(
                    action="done",
                    value="Found the sample result.",
                    rationale="The requested information is available.",
                    plan_step_id=2,
                ),
            ]
        )
        self.index = 0

    async def propose(self, messages: list[Message], schema: type[T]) -> LLMResponse[T]:
        await asyncio.sleep(self.delay)
        if schema is Plan:
            data = self.plan.model_dump()
        elif schema is Action:
            if self.index >= len(self.actions):
                raise RuntimeError("Fake action script exhausted without done.")
            data = self.actions[self.index].model_dump()
            self.index += 1
        else:
            raise ValueError("Fake LLM supports only Plan and Action schemas.")
        return LLMResponse(parsed=schema.model_validate(data), tokens_used=10, usage=Usage(prompt_tokens=6, completion_tokens=4))

    async def close(self) -> None:
        return None
