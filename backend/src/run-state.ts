import type { RunRecord } from "./run-store.js";
import type { RunStatus } from "./contracts.js";

const transitions: Record<RunStatus, readonly RunStatus[]> = {
  created: ["planning", "stopped", "failed"],
  planning: ["running", "stopped", "failed"],
  running: ["finished", "stopped", "failed"],
  finished: [],
  failed: [],
  stopped: [],
};

export function transitionRun(run: RunRecord, next: RunStatus): void {
  if (!transitions[run.status].includes(next)) {
    throw new Error(`Invalid run state transition: ${run.status} -> ${next}`);
  }
  run.status = next;
  run.updatedAt = new Date().toISOString();
}
