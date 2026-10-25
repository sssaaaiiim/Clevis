import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import useTaskOrchestrator from "./useTaskOrchestrator";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });
it.each([false, true])("sends permissions only for explicit overrides (%s)", async changed => {
  const events = [{ type: "run.started", data: {} }, { type: "run.finished", data: { result: "Done" } }];
  const fetch = vi.fn(async url => url.endsWith("/api/runs")
    ? { ok: true, json: async () => ({ runId: "run", approvalToken: "private", previewToken: "preview", controlToken: "control" }) }
    : { ok: true, body: new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode(events.map(e => `data: ${JSON.stringify(e)}\n\n`).join(""))); controller.close(); } }) });
  vi.stubGlobal("fetch", fetch);
  const { result } = renderHook(() => useTaskOrchestrator());
  act(() => {
    result.current.setTask("Read demo");
    if (changed) result.current.setPermissions({ ...result.current.permissions, domains: "localhost", steps: "5" });
  });
  await act(async () => { await result.current.runTask(); });
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  if (changed) expect(body.permissions).toEqual({ allowed_domains: ["localhost"], max_steps: 5 });
  else expect(body).not.toHaveProperty("permissions");
  expect(result.current.permissionsLocked).toBe(true);
});
it("blocks an invalid domain before sending any request", async () => {
  const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
  const { result } = renderHook(() => useTaskOrchestrator());
  act(() => { result.current.setTask("Read"); result.current.setPermissions({ ...result.current.permissions, domains: "http://google.com/search" }); });
  await act(async () => { await result.current.runTask(); });
  expect(fetch).not.toHaveBeenCalled();
  expect(result.current.result.message).toContain("hostnames only");
});
