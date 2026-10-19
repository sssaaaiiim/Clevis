import { createServer } from "node:http";
import path from "node:path";
import express, { type Request, type Response } from "express";
import { StartRunSchema } from "./contracts.js";
import { config } from "./config.js";
import { AllowAllActionValidator, EmptySkillProvider } from "./browser-driver.js";
import { logger } from "./logger.js";
import { OpenRouterClient } from "./model.js";
import { Orchestrator } from "./orchestrator.js";
import { PinchtabDriver } from "./pinchtab/pinchtab-driver.js";
import { InMemoryRunStore } from "./run-store.js";

const app = express();
const store = new InMemoryRunStore();
const orchestrator = new Orchestrator(
  store,
  () =>
    new PinchtabDriver({
      baseUrl: config.PINCHTAB_URL,
      token: config.PINCHTAB_TOKEN,
      allowScreencast: config.allowScreencast,
    }),
  new OpenRouterClient({
    apiKey: config.OPENROUTER_API_KEY,
    primaryModel: config.OPENROUTER_MODEL,
    fallbackModel: config.OPENROUTER_FALLBACK_MODEL,
    baseUrl: config.OPENROUTER_BASE_URL,
  }),
  new AllowAllActionValidator(),
  new EmptySkillProvider(),
  {
    maxSteps: config.MAX_STEPS,
    maxSeconds: config.MAX_SECONDS,
    maxTokens: config.MAX_LLM_TOKENS,
    maxCostUsd: config.MAX_LLM_COST_USD,
  }
);

app.disable("x-powered-by");
app.use((request, response, next) => {
  const origin = request.get("origin");
  if (origin && origin !== config.FRONTEND_ORIGIN) {
    response.status(403).json({ error: "Origin is not allowed." });
    return;
  }
  if (origin) {
    response.setHeader("Access-Control-Allow-Origin", config.FRONTEND_ORIGIN);
    response.setHeader("Vary", "Origin");
    response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    response.setHeader("Access-Control-Allow-Headers", "Content-Type, Last-Event-ID");
  }
  if (request.method === "OPTIONS") {
    response.sendStatus(204);
    return;
  }
  next();
});
app.use(express.json({ limit: "16kb" }));
app.use(express.static(path.resolve(process.cwd(), "public"), { index: false }));

app.post("/api/runs", (request, response) => {
  const parsed = StartRunSchema.safeParse(request.body);
  if (!parsed.success) {
    response.status(400).json({ error: "Invalid run request.", details: parsed.error.flatten() });
    return;
  }
  if (parsed.data.mode === "headed" && !config.allowHeaded) {
    response.status(400).json({ error: "Headed mode is available only when ALLOW_HEADED=true on a local desktop." });
    return;
  }
  const { startUrl, maxSteps, maxSeconds, ...requiredFields } = parsed.data;
  const run = orchestrator.create({
    ...requiredFields,
    ...(startUrl === undefined ? {} : { startUrl }),
    ...(maxSteps === undefined ? {} : { maxSteps }),
    ...(maxSeconds === undefined ? {} : { maxSeconds }),
  });
  logger.child({ runId: run.id }).info("Run created.");
  orchestrator.start(run.id);
  response.status(202).json({ runId: run.id });
});

app.get("/api/runs/:id", (request, response) => {
  const run = store.get(request.params.id!);
  if (!run) {
    response.status(404).json({ error: "Run not found." });
    return;
  }
  response.json({
    runId: run.id,
    goal: run.goal,
    mode: run.mode,
    status: run.status,
    result: run.result,
    error: run.error,
    createdAt: run.createdAt,
    updatedAt: run.updatedAt,
  });
});

app.post("/api/runs/:id/stop", (request, response) => {
  const run = store.get(request.params.id!);
  if (!run) {
    response.status(404).json({ error: "Run not found." });
    return;
  }
  orchestrator.stop(run.id);
  response.json({ runId: run.id, status: run.status });
});

app.get("/api/runs/:id/events", async (request, response) => {
  const run = store.get(request.params.id!);
  if (!run) {
    response.status(404).json({ error: "Run not found." });
    return;
  }

  response.status(200);
  response.setHeader("Content-Type", "text/event-stream");
  response.setHeader("Cache-Control", "no-cache, no-transform");
  response.setHeader("Connection", "keep-alive");
  response.setHeader("X-Accel-Buffering", "no");
  response.flushHeaders();

  const headerCursor = Number(request.get("last-event-id") ?? 0);
  let cursor = Number.isInteger(headerCursor) && headerCursor > 0 ? headerCursor : 0;
  const sendAvailable = () => {
    for (const event of run.events) {
      if (event.seq <= cursor) continue;
      response.write(`id: ${event.seq}\nevent: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`);
      cursor = event.seq;
    }
  };
  const keepAlive = setInterval(() => response.write(": keep-alive\n\n"), 15000);
  const pump = setInterval(() => {
    sendAvailable();
    if (["finished", "failed", "stopped"].includes(run.status) && cursor >= run.events.length) {
      clearInterval(pump);
      clearInterval(keepAlive);
      response.end();
    }
  }, 100);
  sendAvailable();
  response.on("close", () => {
    clearInterval(pump);
    clearInterval(keepAlive);
  });
});

app.use((error: unknown, _request: Request, response: Response, _next: express.NextFunction) => {
  const message = error instanceof Error ? error.message : "Unexpected backend error.";
  void _next;
  logger.child({ runId: "system" }).error(
    { errorName: error instanceof Error ? error.name : "UnknownError" },
    "HTTP request failed."
  );
  response.status(500).json({ error: message });
});

const server = createServer(app);
server.listen(config.PORT, "0.0.0.0", () => {
  logger.child({ runId: "system" }).info({ port: config.PORT }, "Backend listening.");
});
