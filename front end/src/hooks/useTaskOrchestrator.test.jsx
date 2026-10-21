import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";
import useTaskOrchestrator from "./useTaskOrchestrator";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

it("renders the Python event contract without displaying proposed typed values", async () => {
  const events = [
    { type: "run.started", data: { goal: "Demo", mode: "headless" } },
    { type: "plan.created", data: { steps: [{ id: 1, text: "Open form" }, { id: 2, text: "Submit form" }] } },
    { type: "step.proposed", data: { stepId: 1, planStepId: 2, action: "type", target: { ref: "e4" }, value: "PRIVATE-VALUE", rationale: "Fill the requested field." } },
    { type: "step.executed", data: { stepId: 1, ok: true, resultSummary: "Typed into field" } },
    { type: "budget.update", data: { tokensUsed: 123 } },
    { type: "run.finished", data: { result: "Form submitted" } },
  ];
  const text = events.map((e, i) => `id: ${i + 1}\r\nevent: ${e.type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`).join("");
  const bytes = new TextEncoder().encode(text);
  let sent = false;
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ runId: "test", previewToken: "preview", controlToken: "control" }) }).mockResolvedValueOnce({
    ok: true, body: { getReader: () => ({ read: async () => sent ? { done: true } : (sent = true, { done: false, value: bytes }) }) },
  });
  vi.stubGlobal("fetch", fetch);
  const { result } = renderHook(() => useTaskOrchestrator());
  act(() => result.current.setTask("Demo"));
  await act(() => result.current.runTask());
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ goal: "Demo", mode: "headless" });
  expect(result.current.plan.map(s => s.label)).toEqual(["Open form", "Submit form"]);
  expect(result.current.activeIndex).toBe(1);
  expect(result.current.tokens).toBe(123);
  expect(result.current.logs.map(l => l.m)).toContain("type: Fill the requested field.");
  expect(result.current.logs.map(l => l.m)).toContain("Typed into field");
  expect(JSON.stringify(result.current.logs)).not.toContain("PRIVATE-VALUE");
  expect(result.current.status).toBe("Completed");
});
