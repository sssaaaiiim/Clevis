export function packet(overrides = {}, image = new Uint8Array([255, 216, 255, 217])) {
  const metadata = { format: "jpeg", width: 1280, height: 720, deviceScaleFactor: 1,
    viewportWidth: 1280, viewportHeight: 720, seq: 1, tabId: "tab", ...overrides };
  const header = new TextEncoder().encode(JSON.stringify(metadata));
  const bytes = new Uint8Array(4 + header.length + image.length);
  new DataView(bytes.buffer).setUint32(0, header.length, false);
  bytes.set(header, 4); bytes.set(image, 4 + header.length);
  return bytes.buffer;
}

