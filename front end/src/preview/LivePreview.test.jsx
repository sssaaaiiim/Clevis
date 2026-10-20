import React from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import LivePreview from "./LivePreview";
import { packet } from "./preview.fixtures";

let sockets, draw, bitmapSize;
class MockSocket {
  static OPEN = 1;
  readyState = 1;
  sent = [];
  constructor(url) { this.url = url; sockets.push(this); }
  send(text) { this.sent.push(JSON.parse(text)); }
  close() { this.readyState = 3; }
}
beforeEach(() => {
  sockets = []; draw = vi.fn(); bitmapSize = [1280, 720];
  vi.spyOn(document, "hidden", "get").mockReturnValue(false);
  vi.stubGlobal("WebSocket", MockSocket);
  vi.stubGlobal("ResizeObserver", class { constructor(cb) { this.cb = cb; } observe() { this.cb([{ contentRect: { width: 2000, height: 1000 } }]); } disconnect() {} });
  vi.stubGlobal("createImageBitmap", vi.fn(async () => ({ width: bitmapSize[0], height: bitmapSize[1], close: vi.fn() })));
  vi.stubGlobal("requestAnimationFrame", cb => setTimeout(cb, 0));
  vi.stubGlobal("cancelAnimationFrame", clearTimeout);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: draw });
});
afterEach(() => { window.history.replaceState({}, "", "/"); cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const session = { runId: "demo", previewToken: "fake-in-memory-token" };

it.each([1, 2])("authenticates and draws native pixels at scale %i", async (scale) => {
  bitmapSize = [1280 * scale, 720 * scale];
  const { container } = render(<LivePreview session={session} url="demo.test" />);
  expect(screen.getByRole("status").textContent).toBe("Starting browser…");
  act(() => sockets[0].onopen());
  expect(sockets[0].sent[0]).toEqual({ type: "auth", token: session.previewToken });
  expect(sockets[0].url).not.toContain(session.previewToken);
  act(() => sockets[0].onmessage({ data: packet({ width: bitmapSize[0], height: bitmapSize[1], deviceScaleFactor: scale }) }));
  await waitFor(() => expect(draw).toHaveBeenCalledTimes(1));
  const canvas = container.querySelector("canvas");
  expect(canvas.width).toBe(1280 * scale); expect(canvas.height).toBe(720 * scale);
  expect(canvas.style.width).toBe("1280px");
});

it.each([
  ["waiting", "", "Starting browser…"], ["stalled", "", "Waiting for the page…"],
  ["fallback", "", "Using low-frame-rate mode"], ["ended", "", "Run ended"],
  ["live", "Preview paused: page is idle", "Preview paused: page is idle"],
])("renders the %s overlay", (status, message, expected) => {
  render(<LivePreview session={session} />);
  act(() => sockets[0].onmessage({ data: JSON.stringify({ type: "status", status, message }) }));
  expect(screen.getByRole("status").textContent).toBe(expected);
});

it("drops intermediate frames and delays bitmap decoding while hidden", async () => {
  const hidden = vi.spyOn(document, "hidden", "get").mockReturnValue(true);
  render(<LivePreview session={session} />);
  act(() => {
    sockets[0].onmessage({ data: packet({ seq: 1 }) });
    sockets[0].onmessage({ data: packet({ seq: 2 }) });
  });
  expect(createImageBitmap).not.toHaveBeenCalled();
  hidden.mockReturnValue(false);
  act(() => document.dispatchEvent(new Event("visibilitychange")));
  await waitFor(() => expect(createImageBitmap).toHaveBeenCalledTimes(1));
});

it("reconnects with backoff but keeps ended connections closed", () => {
  vi.useFakeTimers();
  render(<LivePreview session={session} />);
  act(() => sockets[0].onclose());
  act(() => vi.advanceTimersByTime(250));
  expect(sockets).toHaveLength(2);
  act(() => sockets[1].onmessage({ data: JSON.stringify({ type: "status", status: "ended" }) }));
  act(() => sockets[1].onclose());
  act(() => vi.advanceTimersByTime(5000));
  expect(sockets).toHaveLength(2);
  vi.useRealTimers();
});


it("shows dev debug readings only when requested", async () => {
  window.history.replaceState({}, "", "/?debug=1");
  render(<LivePreview session={session} />);
  act(() => sockets[0].onmessage({ data: packet() }));
  await waitFor(() => expect(screen.getByTestId("preview-debug").textContent).toContain("Canvas: 1280 × 720"));
  expect(screen.getByTestId("preview-debug").textContent).toContain("CSS: 1280.0 × 720.0");
  expect(screen.getByTestId("preview-debug").textContent).toContain("Bytes: 4");
});


it("continues drawing when new frames arrive during a slow bitmap decode", async () => {
  let finishDecode;
  createImageBitmap.mockImplementationOnce(() => new Promise(resolve => { finishDecode = resolve; }));
  render(<LivePreview session={session} />);
  act(() => sockets[0].onmessage({ data: packet({ seq: 1 }) }));
  await waitFor(() => expect(finishDecode).toBeTypeOf("function"));
  act(() => sockets[0].onmessage({ data: packet({ seq: 2 }) }));
  await act(async () => finishDecode({ width: 1280, height: 720, close: vi.fn() }));
  await waitFor(() => expect(draw.mock.calls.length).toBeGreaterThanOrEqual(1));
});


it("recovers from an invalid frame without losing the server's fallback status", async () => {
  render(<LivePreview session={session} />);
  act(() => {
    sockets[0].onmessage({ data: JSON.stringify({ type: "status", status: "fallback" }) });
    sockets[0].onmessage({ data: new ArrayBuffer(0) });
  });
  expect(screen.getByRole("status").textContent).toBe("Waiting for the page…");
  act(() => sockets[0].onmessage({ data: packet() }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Using low-frame-rate mode"));
});
