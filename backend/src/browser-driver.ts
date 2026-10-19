import type { AgentAction, RunMode } from "./contracts.js";

export interface BrowserDriver {
  startSession(mode: RunMode, signal: AbortSignal): Promise<void>;
  navigate(url: string, signal: AbortSignal): Promise<void>;
  snapshot(signal: AbortSignal): Promise<string>;
  act(action: AgentAction, signal: AbortSignal): Promise<string>;
  getText(signal: AbortSignal): Promise<string>;
  screenshot(signal: AbortSignal): Promise<{ mimeType: string; data: Buffer }>;
  previewStream(signal: AbortSignal): AsyncIterable<{ mimeType: string; data: Buffer }>;
  close(): Promise<void>;
}

export interface ActionValidator {
  validate(action: AgentAction): Promise<{ allowed: boolean; reason?: string }>;
}

export class AllowAllActionValidator implements ActionValidator {
  async validate(): Promise<{ allowed: boolean }> {
    // TODO Phase 2: policy tiers, domain allowlist, approvals
    return { allowed: true };
  }
}

export interface SkillProvider {
  getSkills(): Promise<readonly string[]>;
}

export class EmptySkillProvider implements SkillProvider {
  async getSkills(): Promise<readonly string[]> {
    return [];
  }
}
