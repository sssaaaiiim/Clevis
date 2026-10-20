import { expect, it } from "vitest";
import { keyMessage, mapPointer, modifiers, nextClick, sendTextChunks, wheelPixels } from "./input";
it.each([1, 2])("maps frame scale %i in a resized, letterboxed canvas", scale => {
  const frame = { width: 1280 * scale, height: 720 * scale, deviceScaleFactor: scale, viewportWidth: 1280, viewportHeight: 720 };
  for (const rect of [{ left: 150, top: 70, width: 640, height: 360 }, { left: 300, top: 200, width: 1280, height: 720 }]) {
    expect(mapPointer(rect.left + rect.width / 2, rect.top + rect.height / 2, rect, frame)).toEqual({ x: 640, y: 360 });
    expect(mapPointer(-100, -100, rect, frame)).toEqual({ x: 0, y: 0 });
    expect(mapPointer(9000, 9000, rect, frame)).toEqual({ x: 1279, y: 719 });
  }
  expect(mapPointer(0, 0, { width: 0, height: 0 }, frame)).toBeNull();
});
it("builds keys without stealing browser shortcuts or printable/IME input", () => {
  const event = { key: "Enter", code: "Enter", altKey: true, ctrlKey: true, metaKey: true, shiftKey: true };
  expect(modifiers(event)).toBe(15);
  expect(keyMessage(event, "down")).toEqual({ type: "key", action: "down", key: "Enter", code: "Enter", modifiers: 15 });
  for (const key of ["w", "t", "l", "r", "v", "F5", "F12"]) expect(keyMessage({ ...event, key }, "down")).toBeNull();
  expect(keyMessage({ key: "非", code: "KeyA" }, "down")).toBeNull();
  expect(keyMessage({ key: "Process", code: "KeyA", isComposing: true }, "down")).toBeNull();
  expect(keyMessage({ key: "a", code: "KeyA", ctrlKey: true }, "down")).toMatchObject({ key: "a", modifiers: 2 });
});
it("normalizes wheel deltas and chunks Unicode paste without splitting characters", () => {
  expect(wheelPixels({ deltaMode: 1, deltaX: 1, deltaY: 3 }, 720)).toEqual({ dx: 16, dy: 48 });
  expect(wheelPixels({ deltaMode: 2, deltaX: 0, deltaY: 2 }, 720)).toEqual({ dx: 0, dy: 1440 });
  const chunks = [];
  sendTextChunks("🙂".repeat(2001), m => chunks.push(m));
  expect(chunks.map(m => Array.from(m.value).length)).toEqual([2000, 1]);
});

it("respects advertised text and UTF-8 message byte limits", () => {
  const messages = [];
  sendTextChunks("🙂".repeat(100), message => messages.push(message), 10, 128);
  expect(messages).toHaveLength(10);
  for (const message of messages) expect(new TextEncoder().encode(JSON.stringify(message)).length).toBeLessThanOrEqual(128);
});

it("relays double-click counts when Chromium pointer events report detail zero", () => {
  const event = { detail: 0, clientX: 250, clientY: 210, button: 0 };
  const first = nextClick(event, null, 100);
  expect(first.count).toBe(1);
  expect(nextClick(event, first, 220).count).toBe(2);
  expect(nextClick(event, first, 800).count).toBe(1);
  expect(nextClick({ ...event, button: 2 }, first, 220).count).toBe(1);
  expect(nextClick({ ...event, detail: 2 }, null, 100).count).toBe(2);
});
