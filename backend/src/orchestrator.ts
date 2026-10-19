import { randomUUID } from "node:crypto";
import type { AgentAction, RunEventType, RunStatus } from "./contracts.js";
import { makeRunEvent } from "./contracts.js";
import { ActionLoopDetector, BudgetExceededError, RunBudget } from "./budget.js";
import type { ActionValidator, BrowserDriver, SkillProvider } from "./browser-driver.js";
import type { AgentModel } from "./model.js";
import type { RunRecord, RunStore } from "./run-store.js";
import { transitionRun } from "./run-state.js";
import { logger } from "./logger.js";

export interface OrchestratorOptions {
  maxSteps: number;
  maxSeconds: number;
  maxTokens: number;
  maxCostUsd: number;
}

export type DriverFactory = () => BrowserDriver;

export class Orchestrator {
  constructor(
    private readonly store: RunStore,
    private readonly driverFactory: DriverFactory,
    private readonly model: AgentModel,
    private readonly validator: ActionValidator,
    private readonly skills: SkillProvider,
    private readonly options: OrchestratorOptions
  ) {}

  create(input: {
    goal: string;
    mode: "headed" | "headless";
    startUrl?: string;
    maxSteps?: number;
    maxSeconds?: number;
  }): RunRecord {
    return this.store.create({ id: randomUUID(), ...input });
  }

  start(runId: string): void {
    const run = this.requireRun(runId);
    void this.execute(run).catch((error: unknown) => {
      const current = this.requireRun(runId);
      if (current.status !== "stopped" && !isTerminal(current.status)) {
        this.fail(current, messageOf(error));
      }
    });
  }

  stop(runId: string): RunRecord {
    const run = this.requireRun(runId);
    if (isTerminal(run.status)) return run;
    run.controller.abort(new DOMException("Run stopped by operator.", "AbortError"));
    transitionRun(run, "stopped");
    run.error = "Run stopped by operator.";
    this.emit(run, "run.stopped", { reason: run.error });
    this.log(run, "Run stopped by operator.");
    return run;
  }

  private async execute(run: RunRecord): Promise<void> {
    const runLogger = logger.child({ runId: run.id });
    const budget = new RunBudget({
      maxSteps: Math.min(run.maxSteps ?? this.options.maxSteps, this.options.maxSteps),
      maxSeconds: Math.min(run.maxSeconds ?? this.options.maxSeconds, this.options.maxSeconds),
      maxTokens: this.options.maxTokens,
      maxCostUsd: this.options.maxCostUsd,
    });
    const driver = this.driverFactory();
    let previewController: AbortController | undefined;
    let previewTask: Promise<void> | undefined;
    let abortPreview: (() => void) | undefined;
    const deadlineTimer = setTimeout(() => {
      if (!isTerminal(run.status) && !run.controller.signal.aborted) {
        run.controller.abort(new BudgetExceededError(`Time budget exceeded (${budget.limits.maxSeconds} seconds).`));
      }
    }, budget.limits.maxSeconds * 1000);
    try {
      if (run.status !== "created") return;
      transitionRun(run, "planning");
      this.emit(run, "run.started", { goal: run.goal, mode: run.mode });
      await driver.startSession(run.mode, run.controller.signal);
      if (currentRunStatus(run) === "stopped") return;

      const plan = await this.model.createPlan(run.goal, run.startUrl, run.controller.signal, this.modelHooks(run, budget));
      this.emitBudget(run, budget);
      if (currentRunStatus(run) === "stopped") return;
      const steps = plan.steps.map((label, index) => ({ id: index + 1, label }));
      this.emit(run, "plan.created", { steps });
      transitionRun(run, "running");

      const startingUrl =
        run.startUrl ?? plan.startUrl ?? `https://www.google.com/search?q=${encodeURIComponent(run.goal)}`;
      await driver.navigate(startingUrl, run.controller.signal);
      if (currentRunStatus(run) === "stopped") return;
      previewController = new AbortController();
      abortPreview = () => previewController?.abort();
      run.controller.signal.addEventListener("abort", abortPreview, { once: true });
      previewTask = this.streamPreview(run, driver, previewController);

      const loopDetector = new ActionLoopDetector();
      let finalResult = "Task completed.";
      let completed = false;
      for (let stepIndex = 0; stepIndex < budget.limits.maxSteps; stepIndex += 1) {
        this.assertRunning(run);
        budget.startStep();
        this.emitBudget(run, budget);
        const step = steps[stepIndex % steps.length]!;
        const snapshot = await driver.snapshot(run.controller.signal);
        this.emit(run, "observation.summary", {
          summary: `Captured a fresh interactive page snapshot for step ${step.id}.`,
        });
        const action = await this.model.proposeAction(
          { goal: run.goal, step: step.label, stepId: step.id, snapshot },
          run.controller.signal,
          this.modelHooks(run, budget)
        );
        this.emitBudget(run, budget);
        this.assertRunning(run);
        loopDetector.observe(action);
        this.emit(run, "step.proposed", {
          goal: run.goal,
          step: step.label,
          action: actionSummary(action),
          why: action.rationale,
        });

        if (action.action === "done") {
          finalResult = action.value?.trim() || action.rationale;
          this.emit(run, "step.executed", { result: "Task completion confirmed." });
          completed = true;
          break;
        }

        const result = await this.executeAction(action, driver, run);
        this.emit(run, "step.executed", { result });
      }
      if (!completed) {
        throw new BudgetExceededError(`Step budget exceeded (${budget.limits.maxSteps}).`);
      }
      this.assertRunning(run);
      budget.assertWithinLimits();
      previewController.abort();
      await previewTask;
      transitionRun(run, "finished");
      run.result = finalResult;
      this.emit(run, "run.finished", { result: finalResult });
      runLogger.info({ status: run.status }, "Run finished.");
    } catch (error) {
      if (run.status === "stopped") return;
      if (run.controller.signal.aborted && !(run.controller.signal.reason instanceof BudgetExceededError)) return;
      const reason =
        run.controller.signal.reason instanceof BudgetExceededError
          ? run.controller.signal.reason.message
          : error instanceof BudgetExceededError
            ? error.message
            : messageOf(error);
      this.fail(run, reason);
      runLogger.error({ status: run.status, errorName: error instanceof Error ? error.name : "UnknownError" }, "Run failed.");
    } finally {
      clearTimeout(deadlineTimer);
      previewController?.abort();
      if (abortPreview) run.controller.signal.removeEventListener("abort", abortPreview);
      if (previewTask) await previewTask.catch(() => undefined);
      try {
        await driver.close();
      } catch (error) {
        runLogger.error({ errorName: error instanceof Error ? error.name : "UnknownError" }, "Browser cleanup failed.");
      }
    }
  }

  private async executeAction(action: AgentAction, driver: BrowserDriver, run: RunRecord): Promise<string> {
    this.assertRunning(run);
    if (action.action === "navigate") {
      const decision = await this.validator.validate(action);
      if (!decision.allowed) throw new Error(decision.reason ?? "Action was rejected.");
      await driver.navigate(action.value!, run.controller.signal);
      return "Navigated to the requested page.";
    }
    if (action.action === "extract") {
      const decision = await this.validator.validate(action);
      if (!decision.allowed) throw new Error(decision.reason ?? "Action was rejected.");
      const text = await driver.getText(run.controller.signal);
      return `Extracted page text (${text.length} characters): ${text.slice(0, 4000)}`;
    }
    if (action.action === "wait") {
      await abortableDelay(800, run.controller.signal);
      return "Waited for the page to settle.";
    }
    const decision = await this.validator.validate(action);
    if (!decision.allowed) throw new Error(decision.reason ?? "Action was rejected.");
    return driver.act(action, run.controller.signal);
  }

  private async streamPreview(run: RunRecord, driver: BrowserDriver, controller: AbortController): Promise<void> {
    try {
      for await (const frame of driver.previewStream(controller.signal)) {
        if (run.status !== "running") break;
        this.emit(run, "preview.frame", {
          mimeType: frame.mimeType,
          dataUrl: `data:${frame.mimeType};base64,${frame.data.toString("base64")}`,
        });
      }
    } catch (error) {
      if (!controller.signal.aborted && run.status === "running") {
        logger.child({ runId: run.id }).warn(
          { errorName: error instanceof Error ? error.name : "UnknownError" },
          "Browser preview capture failed."
        );
      }
    }
  }

  private modelHooks(run: RunRecord, budget: RunBudget) {
    return {
      beforeRequest: () => {
        this.assertRunning(run);
        budget.assertWithinLimits();
      },
      onUsage: (usage: { tokens: number; costUsd: number }) => {
        budget.addUsage(usage);
        this.emitBudget(run, budget);
      },
    };
  }

  private emitBudget(run: RunRecord, budget: RunBudget): void {
    this.emit(run, "budget.update", budget.snapshot());
  }

  private emit<T extends RunEventType>(run: RunRecord, type: T, data: Parameters<typeof makeRunEvent<T>>[3]): void {
    const event = makeRunEvent(run.id, run.nextSeq++, type, data);
    this.store.appendEvent(event);
  }

  private fail(run: RunRecord, reason: string): void {
    if (isTerminal(run.status)) return;
    transitionRun(run, "failed");
    run.error = reason;
    this.emit(run, "run.failed", { reason });
  }

  private assertRunning(run: RunRecord): void {
    if (run.status === "stopped" || run.controller.signal.aborted) {
      throw run.controller.signal.reason ?? new DOMException("Run stopped.", "AbortError");
    }
  }

  private requireRun(runId: string): RunRecord {
    const run = this.store.get(runId);
    if (!run) throw new Error(`Run ${runId} does not exist.`);
    return run;
  }

  private log(run: RunRecord, message: string): void {
    logger.child({ runId: run.id }).info(message);
  }
}

function actionSummary(action: AgentAction): string {
  if (action.target) return `${action.action} ${action.target.description}`;
  if (action.action === "navigate") return "navigate to a new page";
  if (action.action === "done") return "finish the task";
  return action.action;
}

function isTerminal(status: RunRecord["status"]): boolean {
  return ["finished", "failed", "stopped"].includes(status);
}

function currentRunStatus(run: RunRecord): RunStatus {
  return run.status;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "An unknown orchestration error occurred.";
}

function abortableDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason);
    const onAbort = () => {
        clearTimeout(timer);
        reject(signal.reason);
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, milliseconds);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}
