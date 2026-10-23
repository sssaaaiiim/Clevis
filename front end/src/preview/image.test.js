import { afterEach, expect, it, vi } from "vitest";
import { decodeFrameImage } from "./image";

afterEach(() => { vi.unstubAllGlobals(); });

it.each(["missing", "rejected"])("uses and releases the native image decoder when bitmap decoding is %s", async mode => {
  const revoke = vi.fn(), create = vi.fn(() => "blob:memory-only-preview");
  const BrowserURL = URL;
  vi.stubGlobal("URL", class extends BrowserURL {
    static createObjectURL = create;
    static revokeObjectURL = revoke;
  });
  vi.stubGlobal("createImageBitmap", mode === "missing" ? undefined : vi.fn().mockRejectedValue(new Error("Decode failed")));
  vi.stubGlobal("Image", class {
    naturalWidth = 2560;
    naturalHeight = 1440;
    set src(value) { queueMicrotask(() => this.onload()); }
  });
  const image = await decodeFrameImage({ image: new ArrayBuffer(4), metadata: { format: "jpeg" } });
  expect(image.width).toBe(2560); expect(image.height).toBe(1440);
  expect(revoke).not.toHaveBeenCalled();
  image.close();
  expect(create).toHaveBeenCalledTimes(1);
  expect(revoke).toHaveBeenCalledWith("blob:memory-only-preview");
});

it("releases the object URL when native decoding fails", async () => {
  const revoke = vi.fn(), BrowserURL = URL;
  vi.stubGlobal("URL", class extends BrowserURL {
    static createObjectURL = () => "blob:bad-preview";
    static revokeObjectURL = revoke;
  });
  vi.stubGlobal("createImageBitmap", undefined);
  vi.stubGlobal("Image", class { set src(value) { queueMicrotask(() => this.onerror()); } });
  await expect(decodeFrameImage({ image: new ArrayBuffer(4), metadata: { format: "jpeg" } })).rejects.toThrow("Unable to decode preview image");
  expect(revoke).toHaveBeenCalledWith("blob:bad-preview");
});
