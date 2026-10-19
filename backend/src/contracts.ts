import { z } from "zod";

export const RunModeSchema = z.enum(["headed", "headless"]);
export type RunMode = z.infer<typeof RunModeSchema>;

export const StartRunSchema = z.object({
  goal: z.string().trim().min(1).max(4000),
  mode: RunModeSchema,
  startUrl: z.string().url().optional(),
  maxSteps: z.number().int().positive().max(100).optional(),
  maxSeconds: z.number().positive().max(600).optional(),
});
export type StartRunRequest = z.infer<typeof StartRunSchema>;

export const RunStatusSchema = z.enum([
  "created",
  "planning",
  "running",
  "finished",
  "failed",
  "stopped",
]);
export type RunStatus = z.infer<typeof RunStatusSchema>;

const PlanStepSchema = z.object({
  id: z.number().int().positive(),
  label: z.string().min(1).max(240),
});
export type PlanStep = z.infer<typeof PlanStepSchema>;

export const PlanSchema = z.object({
  startUrl: z.string().url().optional(),
  steps: z.array(z.string().trim().min(1).max(240)).min(1).max(20),
});
export type Plan = z.infer<typeof PlanSchema>;

export const ActionSchema = z
  .object({
    action: z.enum(["click", "type", "navigate", "scroll", "extract", "wait", "done"]),
    target: z
      .object({
        ref: z.string().min(1).max(80),
        description: z.string().min(1).max(240),
      })
      .optional(),
    value: z.string().max(4000).nullable().default(null),
    rationale: z.string().trim().min(1).max(300),
    plan_step_id: z.number().int().positive(),
  })
  .superRefine((action, context) => {
    if (["click", "type", "scroll", "extract"].includes(action.action) && !action.target) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: `${action.action} requires a target`,
        path: ["target"],
      });
    }
    if (action.action === "navigate" && !action.value) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "navigate requires a URL in value",
        path: ["value"],
      });
    }
    if (action.action === "type" && action.value === null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        message: "type requires a value",
        path: ["value"],
      });
    }
  })
  .transform((action) => ({ ...action, value: action.value ?? null }));
export type AgentAction = z.infer<typeof ActionSchema>;

const RationaleSchema = z.object({
  goal: z.string(),
  step: z.string(),
  action: z.string(),
  why: z.string().min(1).max(300),
});

const EventBase = {
  runId: z.string().uuid(),
  seq: z.number().int().positive(),
  ts: z.string().datetime(),
};

export const RunEventSchema = z.discriminatedUnion("type", [
  z.object({ ...EventBase, type: z.literal("run.started"), data: z.object({ goal: z.string(), mode: RunModeSchema }) }),
  z.object({ ...EventBase, type: z.literal("plan.created"), data: z.object({ steps: z.array(PlanStepSchema) }) }),
  z.object({ ...EventBase, type: z.literal("step.proposed"), data: RationaleSchema }),
  z.object({ ...EventBase, type: z.literal("step.executed"), data: z.object({ result: z.string() }) }),
  z.object({ ...EventBase, type: z.literal("observation.summary"), data: z.object({ summary: z.string() }) }),
  z.object({ ...EventBase, type: z.literal("preview.frame"), data: z.object({ mimeType: z.string(), dataUrl: z.string() }) }),
  z.object({
    ...EventBase,
    type: z.literal("budget.update"),
    data: z.object({
      steps: z.number().int().nonnegative(),
      elapsedSeconds: z.number().nonnegative(),
      tokens: z.number().int().nonnegative(),
      costUsd: z.number().nonnegative(),
      limits: z.object({ maxSteps: z.number(), maxSeconds: z.number(), maxTokens: z.number(), maxCostUsd: z.number() }),
    }),
  }),
  z.object({ ...EventBase, type: z.literal("run.finished"), data: z.object({ result: z.string() }) }),
  z.object({ ...EventBase, type: z.literal("run.failed"), data: z.object({ reason: z.string() }) }),
  z.object({ ...EventBase, type: z.literal("run.stopped"), data: z.object({ reason: z.string() }) }),
  z.object({ ...EventBase, type: z.literal("step.validated"), data: z.object({ stepId: z.number().int() }) }),
  z.object({ ...EventBase, type: z.literal("approval.required"), data: z.object({ stepId: z.number().int() }) }),
]);
export type RunEvent = z.infer<typeof RunEventSchema>;

export type RunEventType = RunEvent["type"];
export type EventData<T extends RunEventType> = Extract<RunEvent, { type: T }>["data"];

export function makeRunEvent<T extends RunEventType>(
  runId: string,
  seq: number,
  type: T,
  data: EventData<T>
): RunEvent {
  return RunEventSchema.parse({ runId, seq, ts: new Date().toISOString(), type, data });
}
