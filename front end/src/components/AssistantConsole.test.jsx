import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import AssistantConsole from "./AssistantConsole";

afterEach(cleanup);
it("does not offer unsupported per-run budget overrides", () => {
  render(<AssistantConsole visible open task="Demo" url="" attachments={[]}
    setTask={vi.fn()} setOpen={vi.fn()} setUrl={vi.fn()} setHeadless={vi.fn()} />);
  for (const label of ["Timeout", "Max steps"]) {
    const field = screen.getByRole("textbox", { name: label });
    expect(field.disabled).toBe(true);
    expect(field.value).toBe("Server configured");
  }
  expect(screen.getByRole("button", { name: /Headless/ }).disabled).toBe(false);
});
