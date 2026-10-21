// @vitest-environment node
import { expect, it } from "vitest";
import config from "../../vite.config";

it("keeps the authenticated frontend origin stable and proxies both WebSockets", () => {
  expect(config.server.port).toBe(5173);
  expect(config.server.strictPort).toBe(true);
  expect(config.server.proxy["/api"].ws).toBe(true);
  expect(config.server.proxy["/api"].target).toBe("http://127.0.0.1:8000");
});
