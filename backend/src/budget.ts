export interface BudgetLimits {
  maxSteps: number;
  maxSeconds: number;
  maxTokens: number;
  maxCostUsd: number;
}

export class BudgetExceededError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BudgetExceededError";
  }
}

export class RunBudget {
  private steps = 0;
  private tokens = 0;
  private costUsd = 0;
  private readonly startedAt = Date.now();

  constructor(readonly limits: BudgetLimits) {}

  elapsedSeconds(): number {
    return (Date.now() - this.startedAt) / 1000;
  }

  startStep(): void {
    this.assertWithinLimits();
    if (this.steps >= this.limits.maxSteps) {
      throw new BudgetExceededError(`Step budget exceeded (${this.limits.maxSteps}).`);
    }
    this.steps += 1;
  }

  addUsage(usage: { tokens: number; costUsd: number }): void {
    this.tokens += usage.tokens;
    this.costUsd += usage.costUsd;
    this.assertWithinLimits();
  }

  assertWithinLimits(): void {
    if (this.elapsedSeconds() >= this.limits.maxSeconds) {
      throw new BudgetExceededError(`Time budget exceeded (${this.limits.maxSeconds} seconds).`);
    }
    if (this.tokens > this.limits.maxTokens) {
      throw new BudgetExceededError(`Token budget exceeded (${this.limits.maxTokens} tokens).`);
    }
    if (this.costUsd > this.limits.maxCostUsd) {
      throw new BudgetExceededError(`LLM cost budget exceeded ($${this.limits.maxCostUsd.toFixed(2)}).`);
    }
  }

  snapshot() {
    return {
      steps: this.steps,
      elapsedSeconds: Number(this.elapsedSeconds().toFixed(2)),
      tokens: this.tokens,
      costUsd: Number(this.costUsd.toFixed(6)),
      limits: this.limits,
    };
  }
}

export class ActionLoopDetector {
  private readonly counts = new Map<string, number>();

  observe(action: { action: string; target?: { ref: string } | undefined }): void {
    if (!action.target) return;
    const key = `${action.action}:${action.target.ref}`;
    const count = (this.counts.get(key) ?? 0) + 1;
    this.counts.set(key, count);
    if (count >= 3) {
      throw new Error(`Loop detected: ${action.action} on ${action.target.ref} repeated 3 times.`);
    }
  }
}
