import type { AgentAction, RunMode } from "../contracts.js";
import type { BrowserDriver } from "../browser-driver.js";
import { PINCHTAB_PATHS } from "./paths.js";

interface PinchtabOptions {
  baseUrl: string;
  token: string;
  allowScreencast: boolean;
}

function responseId(body: unknown, fields: string[]): string {
  if (typeof body !== "object" || body === null) throw new Error("PinchTab returned an invalid response.");
  for (const field of fields) {
    const value = (body as Record<string, unknown>)[field];
    if (typeof value === "string" && value.length > 0) return value;
  }
  throw new Error("PinchTab response did not include the expected resource id.");
}

function delay(milliseconds: number, signal: AbortSignal): Promise<void> {
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

export class PinchtabDriver implements BrowserDriver {
  private profileId: string | undefined;
  private instanceId: string | undefined;
  private tabId: string | undefined;

  constructor(private readonly options: PinchtabOptions) {}

  async startSession(mode: RunMode, signal: AbortSignal): Promise<void> {
    const profileResponse = await this.request(PINCHTAB_PATHS.profiles, {
      method: "POST",
      body: JSON.stringify({ name: `clevis-${crypto.randomUUID()}` }),
      signal,
    });
    this.profileId = responseId(await profileResponse.json(), ["id", "profileId"]);

    const instanceResponse = await this.request(PINCHTAB_PATHS.instancesStart, {
      method: "POST",
      body: JSON.stringify({ profileId: this.profileId, mode }),
      signal,
    });
    this.instanceId = responseId(await instanceResponse.json(), ["id", "instanceId"]);

    const tabResponse = await this.request(PINCHTAB_PATHS.instanceTabsOpen(this.instanceId), {
      method: "POST",
      body: JSON.stringify({ url: "about:blank" }),
      signal,
    });
    this.tabId = responseId(await tabResponse.json(), ["tabId", "id"]);
  }

  async navigate(url: string, signal: AbortSignal): Promise<void> {
    const response = await this.request(PINCHTAB_PATHS.tabNavigate(this.tab()), {
      method: "POST",
      body: JSON.stringify({ url }),
      signal,
    });
    await response.arrayBuffer();
  }

  async snapshot(signal: AbortSignal): Promise<string> {
    const response = await this.request(
      `${PINCHTAB_PATHS.tabSnapshot(this.tab())}?filter=interactive&format=compact`,
      { signal }
    );
    return response.text();
  }

  async act(action: AgentAction, signal: AbortSignal): Promise<string> {
    if (!action.target) throw new Error(`The ${action.action} action requires a target.`);
    const payload: Record<string, unknown> = { kind: action.action, ref: action.target.ref };
    if (action.action === "type") payload.text = action.value ?? "";
    if (action.action === "scroll") payload.direction = action.value ?? "down";
    const response = await this.request(PINCHTAB_PATHS.tabAction(this.tab()), {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
    await response.arrayBuffer();
    return `${action.action} completed on ${action.target.description}.`;
  }

  async getText(signal: AbortSignal): Promise<string> {
    const response = await this.request(`${PINCHTAB_PATHS.tabText(this.tab())}?format=text`, { signal });
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const result: unknown = await response.json();
      if (typeof result === "object" && result !== null && typeof (result as { text?: unknown }).text === "string") {
        return (result as { text: string }).text;
      }
      return JSON.stringify(result);
    }
    return response.text();
  }

  async screenshot(signal: AbortSignal): Promise<{ mimeType: string; data: Buffer }> {
    const response = await this.request(
      `${PINCHTAB_PATHS.tabScreenshot(this.tab())}?format=jpeg&quality=65&scale=0.7&raw=true`,
      { signal }
    );
    return {
      mimeType: response.headers.get("content-type")?.split(";")[0] ?? "image/jpeg",
      data: Buffer.from(await response.arrayBuffer()),
    };
  }

  async *previewStream(signal: AbortSignal): AsyncIterable<{ mimeType: string; data: Buffer }> {
    while (!signal.aborted) {
      yield await this.screenshot(signal);
      await delay(700, signal);
    }
  }

  async close(): Promise<void> {
    const failures: string[] = [];
    if (this.instanceId) {
      try {
        await this.request(PINCHTAB_PATHS.instanceClose(this.instanceId), { method: "POST" });
      } catch {
        failures.push("instance");
      }
      this.instanceId = undefined;
    }
    if (this.profileId) {
      try {
        await this.request(PINCHTAB_PATHS.profile(this.profileId), { method: "DELETE" });
      } catch {
        failures.push("profile");
      }
      this.profileId = undefined;
    }
    if (failures.length > 0) throw new Error(`Could not clean up PinchTab ${failures.join(" and ")}.`);
  }

  private tab(): string {
    if (!this.tabId) throw new Error("PinchTab session has not been started.");
    return this.tabId;
  }

  private async request(path: string, init: RequestInit): Promise<Response> {
    let response: Response;
    try {
      response = await fetch(new URL(path, this.options.baseUrl), {
        ...init,
        headers: {
          Authorization: `Bearer ${this.options.token}`,
          "Content-Type": "application/json",
          ...init.headers,
        },
      });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") throw error;
      throw new Error("Could not connect to PinchTab.");
    }
    if (!response.ok) {
      throw new Error(`PinchTab request failed with HTTP ${response.status}.`);
    }
    return response;
  }
}
