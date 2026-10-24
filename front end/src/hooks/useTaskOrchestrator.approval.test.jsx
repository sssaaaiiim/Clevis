import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import useTaskOrchestrator from "./useTaskOrchestrator";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear(); });

it.each([["approve", 200], ["deny", 200], ["approve", 422]])("authenticates %s (%s) without persisting capabilities and dismisses on resumed", async (decision, apiStatus) => {
  let read;
  const token = "PRIVATE-APPROVAL-CAPABILITY";
  const storage = vi.spyOn(Storage.prototype, "setItem");
  const log = vi.spyOn(console, "log");
  const fetch = vi.fn().mockImplementation(async url => {
    if (url.endsWith("/events")) return { ok: true, body: { getReader: () => ({ read: () => new Promise(resolve => { read = resolve; }) }) } };
    if (url.endsWith("/api/runs")) return { ok: true, json: async () => ({ runId: "run-1", previewToken: "preview", controlToken: "control", approvalToken: token }) };
    return { ok: apiStatus === 200, status: apiStatus };
  });
  vi.stubGlobal("fetch", fetch);
  const { result } = renderHook(() => useTaskOrchestrator());
  act(() => result.current.setTask("Submit demo"));
  let running;
  act(() => { running = result.current.runTask(); });
  await waitFor(() => expect(read).toBeTypeOf("function"));
  const send = async events => {
    await act(async () => { read({ done: false, value: new TextEncoder().encode(events.map(e => `data: ${JSON.stringify(e)}\n\n`).join("")) }); });
  };
  await send([
    { type: "approval.required", data: { approval_id: "request-1", action_summary: "Submit form", risk: "medium", page_domain: "example.com", action: { value: "HIDDEN-ACTION-VALUE", target: { ref: "e999" } } } },
    { type: "run.paused", data: { reason: "approval" } },
  ]);
  expect(result.current.approval.action_summary).toBe("Submit form");
  expect(JSON.stringify(result.current.approval)).not.toContain("HIDDEN-ACTION-VALUE");
  expect(result.current.control.active).toBe(false);
  let answer;
  await act(async () => { answer = await result.current.submitApproval(decision, "Use another destination"); });
  if (apiStatus === 422) {
    expect(answer.expired).toBe(true);
    act(() => result.current.dismissApproval("request-1"));
    expect(result.current.approval).toBeNull();
  }
  const request = fetch.mock.calls.find(([url]) => url.endsWith(`/${decision}`));
  expect(request[1].headers.Authorization).toBe(`Bearer ${token}`);
  expect(request[0]).not.toContain(token);
  expect(JSON.parse(request[1].body)).toEqual({ approval_id: "request-1", ...(decision === "deny" ? { reason: "Use another destination" } : {}) });
  await send([{ type: "run.resumed", data: { reason: decision === "approve" ? "approved" : "denied" } }]);
  expect(result.current.approval).toBeNull();
  await send([{ type: "run.finished", data: { result: "Done" } }]);
  await act(async () => { read({ done: true }); await running; });
  expect(JSON.stringify(storage.mock.calls)).not.toContain(token);
  expect(JSON.stringify(log.mock.calls)).not.toContain(token);
  expect(JSON.stringify(result.current)).not.toContain(token);
  const requestsBefore = fetch.mock.calls.length;
  await act(async () => { await result.current.submitApproval("approve"); });
  expect(fetch.mock.calls.length).toBe(requestsBefore);
});
