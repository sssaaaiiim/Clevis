import React from "react";
import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import PermissionsPanel, { DEFAULT_PERMISSIONS, permissionOverrides } from "./PermissionsPanel";

afterEach(cleanup);
it("is collapsed by default and expands, and hides after run starts", () => {
  const { container, rerender } = render(<PermissionsPanel />);
  expect(container.querySelector("details").open).toBe(false);
  fireEvent.click(screen.getByText("Advanced permissions"));
  expect(container.querySelector("details").open).toBe(true);
  rerender(<PermissionsPanel hidden />);
  expect(screen.queryByText("Advanced permissions")).toBeNull();
});
it("omits defaults and sends only changed overrides", () => {
  expect(permissionOverrides()).toBeUndefined();
  expect(permissionOverrides({ ...DEFAULT_PERMISSIONS, domains: "localhost", blockSubmit: true, steps: "8" })).toEqual({ allowed_domains: ["localhost"], allow_form_submit: false, max_steps: 8 });
});
it.each(["http://google.com", "google.com/search", "google.com:80"])("rejects invalid domains %s", domains => {
  expect(() => permissionOverrides({ ...DEFAULT_PERMISSIONS, domains })).toThrow("hostnames only");
});
