import "dotenv/config";
import { z } from "zod";

const EnvironmentSchema = z.object({
  PORT: z.coerce.number().int().positive().default(8000),
  FRONTEND_ORIGIN: z.string().url().default("http://localhost:5173"),
  OPENROUTER_API_KEY: z.string().min(1),
  OPENROUTER_BASE_URL: z.string().url().default("https://openrouter.ai/api/v1"),
  OPENROUTER_MODEL: z.string().min(1).default("openai/gpt-4o-mini"),
  OPENROUTER_FALLBACK_MODEL: z.string().min(1).default("anthropic/claude-3.5-haiku"),
  PINCHTAB_URL: z.string().url().default("http://127.0.0.1:9867"),
  PINCHTAB_TOKEN: z.string().min(1),
  ALLOW_SCREENCAST: z.enum(["true", "false"]).default("false"),
  ALLOW_HEADED: z.enum(["true", "false"]).default("false"),
  MAX_STEPS: z.coerce.number().int().positive().default(20),
  MAX_SECONDS: z.coerce.number().positive().default(180),
  MAX_LLM_TOKENS: z.coerce.number().int().positive().default(30000),
  MAX_LLM_COST_USD: z.coerce.number().positive().default(1),
  LOG_LEVEL: z.enum(["fatal", "error", "warn", "info", "debug", "trace", "silent"]).default("info"),
});

const parsedEnvironment = EnvironmentSchema.safeParse(process.env);
if (!parsedEnvironment.success) {
  const variables = parsedEnvironment.error.issues.map((issue) => issue.path.join(".")).join(", ");
  throw new Error(`Invalid or missing environment variables: ${variables}`);
}

export const config = {
  ...parsedEnvironment.data,
  allowScreencast: parsedEnvironment.data.ALLOW_SCREENCAST === "true",
  allowHeaded: parsedEnvironment.data.ALLOW_HEADED === "true",
};
