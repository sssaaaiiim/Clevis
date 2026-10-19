import type { RunEvent, RunMode, RunStatus } from "./contracts.js";

export interface RunRecord {
  readonly id: string;
  readonly goal: string;
  readonly mode: RunMode;
  readonly startUrl?: string;
  readonly maxSteps?: number;
  readonly maxSeconds?: number;
  status: RunStatus;
  result: string | null;
  error: string | null;
  readonly createdAt: string;
  updatedAt: string;
  events: RunEvent[];
  nextSeq: number;
  controller: AbortController;
}

export interface RunStore {
  create(input: {
    id: string;
    goal: string;
    mode: RunMode;
    startUrl?: string;
    maxSteps?: number;
    maxSeconds?: number;
  }): RunRecord;
  get(id: string): RunRecord | undefined;
  appendEvent(event: RunEvent): void;
}

export class InMemoryRunStore implements RunStore {
  private readonly runs = new Map<string, RunRecord>();

  create(input: {
    id: string;
    goal: string;
    mode: RunMode;
    startUrl?: string;
    maxSteps?: number;
    maxSeconds?: number;
  }): RunRecord {
    const now = new Date().toISOString();
    const run: RunRecord = {
      ...input,
      status: "created",
      result: null,
      error: null,
      createdAt: now,
      updatedAt: now,
      events: [],
      nextSeq: 1,
      controller: new AbortController(),
    };
    this.runs.set(run.id, run);
    return run;
  }

  get(id: string): RunRecord | undefined {
    return this.runs.get(id);
  }

  appendEvent(event: RunEvent): void {
    const run = this.runs.get(event.runId);
    if (!run) throw new Error(`Run ${event.runId} does not exist.`);
    if (event.type === "preview.frame") {
      run.events = run.events.filter((existing) => existing.type !== "preview.frame");
    }
    run.events.push(event);
    run.updatedAt = event.ts;
  }
}
