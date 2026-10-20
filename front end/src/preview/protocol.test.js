import { describe, expect, it } from "vitest";
import { decodePreviewPacket, frameSizing, previewWebSocketUrl } from "./protocol";

import { packet } from "./preview.fixtures";

describe("binary preview protocol", () => {
  it("decodes a large untouched image", () => {
    const image = new Uint8Array(2_000_000).fill(17);
    const decoded = decodePreviewPacket(packet({}, image));
    expect(new Uint8Array(decoded.image).every(byte => byte === 17)).toBe(true);
    expect(decoded.bytes).toBe(image.length);
  });
  it("rejects missing, empty, malformed metadata and invalid dimensions", () => {
    expect(() => decodePreviewPacket(new ArrayBuffer(0))).toThrow();
    expect(() => decodePreviewPacket(new ArrayBuffer(4))).toThrow();
    expect(() => decodePreviewPacket(packet({ width: 0 }))).toThrow();
    expect(() => decodePreviewPacket(packet({ deviceScaleFactor: 0 }))).toThrow();
    expect(() => decodePreviewPacket(packet({ format: "html" }))).toThrow();
  });
  it.each([1, 2])("keeps native pixels and limits CSS size at scale %i", (scale) => {
    const frame = { width: 1280 * scale, height: 720 * scale, deviceScaleFactor: scale };
    expect(frameSizing(frame, 2000, 2000)).toEqual({ internalWidth: frame.width, internalHeight: frame.height, cssWidth: 1280, cssHeight: 720 });
    expect(frameSizing(frame, 640, 360)).toEqual({ internalWidth: frame.width, internalHeight: frame.height, cssWidth: 640, cssHeight: 360 });
    expect(frameSizing(frame, 2000, 360).cssWidth).toBe(640);
  });
  it("uses wss and never a token query parameter", () => {
    expect(previewWebSocketUrl("a/b", "", { href: "https://demo.test/" })).toBe("wss://demo.test/api/runs/a%2Fb/preview");
  });
});
