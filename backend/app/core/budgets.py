from dataclasses import dataclass

from app.core.events import BudgetData
from app.interfaces.llm import Usage


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_steps: int = 30
    max_seconds: float = 300
    max_tokens: int = 200_000
    max_cost_usd: float = 0.50
    steps_used: int = 0
    seconds_used: float = 0
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0
    cost_estimated: bool = False

    def add_usage(self, usage: Usage, tokens_used: int = 0) -> None:
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        # tokens_used is retained for Task 2 third-party fake implementations.
        self.tokens_used += max(usage.total_tokens, tokens_used)
        self.cost_usd += usage.cost_usd
        self.cost_estimated = self.cost_estimated or usage.cost_estimated

    def check(self) -> None:
        limit = None
        if self.seconds_used >= self.max_seconds:
            limit = "MAX_SECONDS"
        elif self.tokens_used > self.max_tokens:
            limit = "MAX_TOKENS"
        elif self.max_cost_usd and self.cost_usd > self.max_cost_usd:
            limit = "MAX_COST_USD"
        if limit:
            raise BudgetExceeded(
                f"{limit} exceeded after {self.steps_used} steps; "
                f"{self.tokens_used} tokens, ${self.cost_usd:.6f}, {self.seconds_used:.2f}s active."
            )

    def event_data(self) -> BudgetData:
        return BudgetData(
            stepsUsed=self.steps_used,
            maxSteps=self.max_steps,
            secondsUsed=self.seconds_used,
            maxSeconds=self.max_seconds,
            tokensUsed=self.tokens_used,
            maxTokens=self.max_tokens,
            promptTokens=self.prompt_tokens,
            completionTokens=self.completion_tokens,
            costUsd=self.cost_usd,
            maxCostUsd=self.max_cost_usd,
            costEstimated=self.cost_estimated,
        )
