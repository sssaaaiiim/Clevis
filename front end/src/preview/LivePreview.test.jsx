import React from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  ["fallback", "", "Using low-frame-rate mode"], ["ended", "", "Run ended before a preview became available."],
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
  expect(screen.getByRole("status").textContent).toBe("Frame could not be displayed; waiting for another frame.");
  act(() => sockets[0].onmessage({ data: packet() }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Using low-frame-rate mode"));
});


it("relays private preview-only input and clears its editor without logging or storage", async () => {
  const error = vi.spyOn(console, "error"), log = vi.spyOn(console, "log");
  const storage = vi.spyOn(Storage.prototype, "setItem");
  const controlled = { ...session, controlToken: "separate-control-token" };
  const { container, rerender } = render(<LivePreview session={controlled} control={{ active: true, reason: "handoff", message: "Please sign in, then click Resume" }} />);
  const input = sockets.find(s => s.url.endsWith("/input")), preview = sockets.find(s => s.url.endsWith("/preview"));
  act(() => input.onopen());
  expect(input.sent[0]).toEqual({ type: "auth", token: controlled.controlToken });
  expect(input.url).not.toContain(controlled.controlToken);
  act(() => preview.onmessage({ data: packet() }));
  await waitFor(() => expect(draw).toHaveBeenCalled());
  act(() => input.onmessage({ data: JSON.stringify({ type: "state", accepting: true, controller: true }) }));
  expect(screen.getByText("You are in control. The agent is paused")).toBeTruthy();
  expect(screen.getByText(/The agent needs you:/).textContent).toContain("Please sign in");
  const editor = screen.getByLabelText("Private browser typing"), canvas = container.querySelector("canvas");
  canvas.getBoundingClientRect = () => ({ left: 100, top: 50, width: 640, height: 360 });
  fireEvent.wheel(canvas, { clientX: 420, clientY: 230, deltaY: 3, deltaMode: 1 });
  expect(input.sent.at(-1)).toEqual({ type: "wheel", x: 640, y: 360, dx: 0, dy: 48 });
  fireEvent.input(editor, { target: { value: "CANARY-PASSWORD-9137" }, inputType: "insertText" });
  expect(input.sent.at(-1)).toEqual({ type: "text", value: "CANARY-PASSWORD-9137" });
  expect(editor.value).toBe("");
  fireEvent.paste(editor, { clipboardData: { getData: () => "demo paste" } });
  expect(input.sent.at(-1)).toEqual({ type: "text", value: "demo paste" });
  fireEvent.compositionStart(editor);
  fireEvent.input(editor, { target: { value: "非" }, isComposing: true });
  fireEvent.compositionEnd(editor, { data: "非" });
  expect(input.sent.at(-1)).toEqual({ type: "text", value: "非" });
  const committed = input.sent.length;
  fireEvent.input(editor, { target: { value: "非" }, inputType: "insertCompositionText", isComposing: false });
  expect(input.sent).toHaveLength(committed);
  expect(editor.value).toBe("");
  const length = input.sent.length;
  fireEvent.keyDown(document.body, { key: "Enter", code: "Enter" });
  expect(input.sent).toHaveLength(length);
  fireEvent.keyDown(editor, { key: "Enter", code: "Enter" });
  expect(input.sent.at(-1)).toMatchObject({ type: "key", key: "Enter" });
  fireEvent.keyDown(editor, { key: "w", code: "KeyW", ctrlKey: true });
  expect(input.sent.at(-1)).toMatchObject({ key: "Enter" });
  expect(error).not.toHaveBeenCalled(); expect(log).not.toHaveBeenCalled(); expect(storage).not.toHaveBeenCalled();
  rerender(<LivePreview session={controlled} control={{ active: false }} />);
  expect(input.readyState).toBe(3);
});

it("shows nonaccepting and another-window controller states", () => {
  render(<LivePreview session={{ ...session, controlToken: "control" }} control={{ active: true }} />);
  expect(screen.getByText("Browser is not accepting input")).toBeTruthy();
  const input = sockets.find(s => s.url.endsWith("/input"));
  act(() => input.onclose({ code: 4409 }));
  expect(screen.getByText("Control taken by another window")).toBeTruthy();
});


it("keeps first-frame feedback when live arrives before any successful paint", async () => {
  render(<LivePreview session={session} />);
  act(() => sockets[0].onmessage({ data: JSON.stringify({ type: "status", status: "live", message: "Preview paused: page is idle" }) }));
  expect(screen.getByRole("status").textContent).toBe("Waiting for browser preview…");
  act(() => sockets[0].onmessage({ data: packet() }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Preview paused: page is idle"));
});

it("retries a previously failed frame when it is resent with the same sequence", async () => {
  createImageBitmap.mockRejectedValueOnce(new Error("Decoder unavailable"));
  vi.stubGlobal("Image", class { set src(value) { queueMicrotask(() => this.onerror()); } });
  const { container } = render(<LivePreview session={session} />);
  act(() => sockets[0].onmessage({ data: packet({ seq: 7 }) }));
  await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Frame could not be displayed"));
  expect(draw).not.toHaveBeenCalled();
  act(() => sockets[0].onmessage({ data: packet({ seq: 7 }) }));
  await waitFor(() => expect(draw).toHaveBeenCalledTimes(1));
  expect(container.querySelector("canvas").style.display).toBe("block");
});

it.each([
  [4401, "Preview authorization expired. Start a new run."],
  [4403, "Preview blocked: frontend address does not match server settings."],
  [4404, "Run not found. Start a new run."],
])("explains permanent close %i without reconnecting", (code, message) => {
  vi.useFakeTimers();
  try {
    render(<LivePreview session={session} />);
    act(() => sockets[0].onclose({ code }));
    expect(screen.getByRole("status").textContent).toBe(message);
    act(() => vi.advanceTimersByTime(30000));
    expect(sockets).toHaveLength(1);
  } finally { vi.useRealTimers(); }
});

it("keeps its last painted frame visible during reconnect and ignores stale socket events", async () => {
  const { container } = render(<LivePreview session={session} />);
  const original = sockets[0];
  act(() => original.onmessage({ data: packet() }));
  await waitFor(() => expect(draw).toHaveBeenCalled());
  act(() => original.onclose({ code: 1006 }));
  expect(container.querySelector("canvas").style.display).toBe("block");
  expect(screen.getByRole("status").textContent).toBe("Preview disconnected; reconnecting…");
  await waitFor(() => expect(sockets).toHaveLength(2));
  act(() => original.onclose({ code: 4401 }));
  act(() => sockets[1].onmessage({ data: packet({ seq: 2 }) }));
  await waitFor(() => expect(draw).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole("status")).toBeNull();
});

it("waits for nonzero bounds before painting, then recovers after resize", async () => {
  let resize;
  vi.stubGlobal("ResizeObserver", class {
    constructor(callback) { resize = callback; }
    observe() { resize([{ contentRect: { width: 0, height: 0 } }]); }
    disconnect() {}
  });
  render(<LivePreview session={session} />);
  act(() => {
    sockets[0].onmessage({ data: JSON.stringify({ type: "status", status: "live" }) });
    sockets[0].onmessage({ data: packet() });
  });
  expect(draw).not.toHaveBeenCalled();
  expect(screen.getByRole("status").textContent).toBe("Waiting for browser preview…");
  act(() => resize([{ contentRect: { width: 640, height: 360 } }]));
  await waitFor(() => expect(draw).toHaveBeenCalledTimes(1));
});

it("paints the final pending frame even when ended arrives before image decoding", async () => {
  const { container } = render(<LivePreview session={session} />);
  act(() => {
    sockets[0].onmessage({ data: packet() });
    sockets[0].onmessage({ data: JSON.stringify({ type: "status", status: "ended" }) });
  });
  await waitFor(() => expect(draw).toHaveBeenCalledTimes(1));
  expect(container.querySelector("canvas").style.display).toBe("block");
  expect(screen.getByRole("status").textContent).toBe("Run ended");
});


it("clears reconnect feedback when an idle page resends its already painted frame", async () => {
  render(<LivePreview session={session} />);
  act(() => sockets[0].onmessage({ data: packet({ seq: 8 }) }));
  await waitFor(() => expect(draw).toHaveBeenCalledTimes(1));
  act(() => sockets[0].onclose({ code: 1006 }));
  await waitFor(() => expect(sockets).toHaveLength(2));
  act(() => {
    sockets[1].onmessage({ data: JSON.stringify({ type: "status", status: "live", message: "page idle" }) });
    sockets[1].onmessage({ data: packet({ seq: 8 }) });
  });
  expect(draw).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("status").textContent).toBe("Preview paused: page is idle");
});
