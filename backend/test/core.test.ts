import { describe, expect, it } from "vitest";
import { ActionLoopDetector, BudgetExceededError, RunBudget } from "../src/budget.js";
import { ActionSchema } from "../src/contracts.js";
import type { BrowserDriver } from "../src/browser-driver.js";
import type { AgentAction, Plan } from "../src/contracts.js";
import type { AgentModel } from "../src/model.js";
import { Orchestrator } from "../src/orchestrator.js";
import { transitionRun } from "../src/run-state.js";
import { InMemoryRunStore } from "../src/run-store.js";
import { AllowAllActionValidator, EmptySkillProvider } from "../src/browser-driver.js";

describe("run state machine", () => {
  it("allows only valid transitions", () => {
    const store = new InMemoryRunStore();
    const run = store.create({ id: crypto.randomUUID(), goal: "Search", mode: "headless" });
    transitionRun(run, "planning");
    transitionRun(run, "running");
    transitionRun(run, "finished");
    expect(run.status).toBe("finished");
    expect(() => transitionRun(run, "running")).toThrow("Invalid run state transition");
  });
});

describe("action schema", () => {
  it("accepts a well-formed click and rejects missing targets", () => {
    expect(
      ActionSchema.safeParse({
        action: "click",
        target: { ref: "e12", description: "Search button" },
        value: null,
        rationale: "Submit the query to see matching pages.",
        plan_step_id: 1,
      }).success
    ).toBe(true);
    expect(
      ActionSchema.safeParse({
        action: "click",
        value: null,
        rationale: "Click the button.",
        plan_step_id: 1,
      }).success
    ).toBe(false);
  });
});

describe("budgets and loop detection", () => {
  it("fails when the step budget is exceeded", () => {
    const budget = new RunBudget({ maxSteps: 1, maxSeconds: 10, maxTokens: 100, maxCostUsd: 1 });
    budget.startStep();
    expect(() => budget.startStep()).toThrow(BudgetExceededError);
  });

  it("fails when token usage exceeds its budget", () => {
    const budget = new RunBudget({ maxSteps: 2, maxSeconds: 10, maxTokens: 5, maxCostUsd: 1 });
    expect(() => budget.addUsage({ tokens: 6, costUsd: 0 })).toThrow("Token budget exceeded");
  });

  it("fails after the same action targets the same element three times", () => {
    const detector = new ActionLoopDetector();
    const action = { action: "click", target: { ref: "e4" } };
    detector.observe(action);
    detector.observe(action);
    expect(() => detector.observe(action)).toThrow("repeated 3 times");
  });
});

describe("orchestrator integration", () => {
  it("runs a fake browser and model through the complete event sequence", async () => {
    const store = new InMemoryRunStore();
    const driver = new FakeDriver();
    const model = new FakeModel();
    const orchestrator = new Orchestrator(
      store,
      () => driver,
      model,
      new AllowAllActionValidator(),
      new EmptySkillProvider(),
      { maxSteps: 4, maxSeconds: 10, maxTokens: 1000, maxCostUsd: 1 }
    );
    const run = orchestrator.create({ goal: "Extract the local product names", mode: "headless" });
    orchestrator.start(run.id);
    await waitForTerminal(() => run.status);

    expect(run.status).toBe("finished");
    expect(run.result).toBe("Extracted the product names.");
    expect(driver.closed).toBe(true);
    expect(run.events.map((event) => event.type).filter((type) =>
      ["run.started", "plan.created", "step.proposed", "step.executed", "run.finished"].includes(type)
    )).toEqual([
      "run.started",
      "plan.created",
      "step.proposed",
      "step.executed",
      "step.proposed",
      "step.executed",
      "run.finished",
    ]);
    expect(run.events.map((event) => event.seq)).toEqual(
      [...run.events.map((event) => event.seq)].sort((left, right) => left - right)
    );
  });
});

class FakeDriver implements BrowserDriver {
  closed = false;

  async startSession(): Promise<void> {}
  async navigate(): Promise<void> {}
  async snapshot(): Promise<string> {
    return "UNTRUSTED PAGE: product table";
  }
  async act(action: AgentAction): Promise<string> {
    return `${action.action} completed.`;
  }
  async getText(): Promise<string> {
    return "Field Notes, Travel Mug, Desk Lamp";
  }
  async screenshot(): Promise<{ mimeType: string; data: Buffer }> {
    return { mimeType: "image/jpeg", data: Buffer.from("frame") };
  }
  async *previewStream(signal: AbortSignal): AsyncIterable<{ mimeType: string; data: Buffer }> {
    yield { mimeType: "image/jpeg", data: Buffer.from("frame") };
    await new Promise<void>((resolve) => signal.addEventListener("abort", () => resolve(), { once: true }));
  }
  async close(): Promise<void> {
    this.closed = true;
  }
}

class FakeModel implements AgentModel {
  private actionIndex = 0;

  async createPlan(): Promise<Plan> {
    return { steps: ["Read the product table"] };
  }

  async proposeAction(): Promise<AgentAction> {
    const actions: AgentAction[] = [
      {
        action: "extract",
        target: { ref: "e2", description: "Product table" },
        value: null,
        rationale: "Read the product table to identify its products.",
        plan_step_id: 1,
      },
      {
        action: "done",
        value: "Extracted the product names.",
        rationale: "The requested product names are available.",
        plan_step_id: 1,
      },
    ];
    return actions[this.actionIndex++]!;
  }
}

async function waitForTerminal(getStatus: () => string): Promise<void> {
  const deadline = Date.now() + 2000;
  while (!["finished", "failed", "stopped"].includes(getStatus()) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  expect(["finished", "failed", "stopped"]).toContain(getStatus());
}
