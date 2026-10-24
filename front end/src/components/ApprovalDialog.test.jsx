import React from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ApprovalDialog from "./ApprovalDialog";

const request = { approval_id: "request-1", action_summary: "Submit the contact form", risk: "medium", page_domain: "example.com" };
beforeEach(() => {
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: { configurable: true, value: vi.fn(function () { this.setAttribute("open", ""); }) },
    close: { configurable: true, value: vi.fn(function () { this.removeAttribute("open"); }) },
  });
});
afterEach(() => { cleanup(); delete HTMLDialogElement.prototype.showModal; delete HTMLDialogElement.prototype.close; vi.restoreAllMocks(); });

it("shows only the summary, risk and domain, and retains an active Stop button", async () => {
  const onStop = vi.fn();
  const onDecision = vi.fn(() => new Promise(() => {}));
  render(<ApprovalDialog request={{ ...request, action: { value: "PRIVATE", target: { ref: "e123" } } }} onDecision={onDecision} onDismiss={vi.fn()} onStop={onStop} />);
  expect(screen.getByRole("dialog")).toBeTruthy();
  expect(screen.getByText(/The agent wants to: Submit the contact form/)).toBeTruthy();
  expect(screen.getByText("medium risk")).toBeTruthy();
  expect(screen.getByText("example.com")).toBeTruthy();
  expect(document.body.textContent).not.toContain("PRIVATE");
  expect(document.body.textContent).not.toContain("e123");
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  expect(onDecision).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Approve" }).disabled).toBe(true);
  expect(screen.getByRole("button", { name: "Deny" }).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Stop run" }));
  expect(onStop).toHaveBeenCalledTimes(1);
});

it.each(["", "Please use a different destination"])("sends an optional denial reason: %s", async reason => {
  const onDecision = vi.fn().mockResolvedValue({ ok: true });
  render(<ApprovalDialog request={request} onDecision={onDecision} onDismiss={vi.fn()} onStop={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Reason for denial (optional)"), { target: { value: reason } });
  fireEvent.click(screen.getByRole("button", { name: "Deny" }));
  await waitFor(() => expect(onDecision).toHaveBeenCalledWith("deny", reason));
  expect(screen.getByLabelText("Reason for denial (optional)").maxLength).toBe(200);
});

it("shows the stale request message then dismisses that request", async () => {
  const onDismiss = vi.fn();
  render(<ApprovalDialog request={request} onDecision={vi.fn().mockResolvedValue({ expired: true })} onDismiss={onDismiss} onStop={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("This approval request has expired"));
  await waitFor(() => expect(onDismiss).toHaveBeenCalledWith("request-1"), { timeout: 2200 });
});
