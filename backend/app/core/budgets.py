from dataclasses import dataclass

from app.core.events import BudgetData


@dataclass
class Budget:
    max_steps: int = 30
    max_seconds: float = 300
    max_tokens: int = 200_000
    steps_used: int = 0
    seconds_used: float = 0
    tokens_used: int = 0

    def event_data(self) -> BudgetData:
        return BudgetData(
            stepsUsed=self.steps_used, maxSteps=self.max_steps,
            secondsUsed=self.seconds_used, maxSeconds=self.max_seconds,
            tokensUsed=self.tokens_used, maxTokens=self.max_tokens,
        )
