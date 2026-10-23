import React from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import TaskActivityPanel from "./TaskActivityPanel";

beforeEach(() => { Element.prototype.scrollTo = vi.fn(); });
afterEach(() => { cleanup(); delete Element.prototype.scrollTo; });

it("shows a task failure at the top before execution steps and scrolling updates", () => {
  render(<TaskActivityPanel task="Open a page" status="Failed" plan={[]} activeIndex={0}
    logs={[{ time: "11:40", t: "System", m: "Run ended" }]}
    result={{ status: "error", message: "Loop detected: no page progress." }} />);
  const error = screen.getByRole("alert");
  expect(error.textContent).toContain("Loop detected: no page progress.");
  expect(error.previousElementSibling.tagName).toBe("HEADER");
  expect(error.nextElementSibling.textContent).toContain("Execution steps");
  expect(error.querySelector("article")).toBeNull();
});

it("keeps successful results in the same visible summary position", () => {
  render(<TaskActivityPanel task="Read" status="Completed" plan={[]} activeIndex={0} logs={[]}
    result={{ status: "success", message: "Page loaded" }} />);
  expect(screen.getByRole("status").textContent).toContain("Result: Page loaded");
  expect(screen.queryByRole("alert")).toBeNull();
});
