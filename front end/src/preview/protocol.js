const MAX_HEADER = 64 * 1024;

export function decodePreviewPacket(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < 4) throw new Error("Missing frame header");
  const size = new DataView(buffer).getUint32(0, false);
  if (size > MAX_HEADER || size < 2 || 4 + size >= buffer.byteLength) throw new Error("Invalid frame length");
  const metadata = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(new Uint8Array(buffer, 4, size)));
  if (!metadata || Array.isArray(metadata) || !["jpeg", "png"].includes(metadata.format)) throw new Error("Invalid frame metadata");
  for (const field of ["width", "height", "viewportWidth", "viewportHeight"]) {
    if (!Number.isInteger(metadata[field]) || metadata[field] <= 0 || metadata[field] > 32768) throw new Error("Invalid frame dimensions");
  }
  if (!Number.isFinite(metadata.deviceScaleFactor) || metadata.deviceScaleFactor <= 0 ||
      !Number.isInteger(metadata.seq) || metadata.seq < 1 || typeof metadata.tabId !== "string") throw new Error("Invalid frame metadata");
  return { metadata, image: buffer.slice(4 + size), bytes: buffer.byteLength - 4 - size };
}

export function frameSizing(frame, containerWidth, containerHeight) {
  const naturalWidth = frame.width / frame.deviceScaleFactor;
  const naturalHeight = frame.height / frame.deviceScaleFactor;
  const scale = Math.min(1, Math.max(0, containerWidth) / naturalWidth, Math.max(0, containerHeight) / naturalHeight);
  return { internalWidth: frame.width, internalHeight: frame.height,
    cssWidth: naturalWidth * scale, cssHeight: naturalHeight * scale };
}

export function previewWebSocketUrl(runId, baseUrl = "", location = window.location) {
  const url = new URL(`${baseUrl}/api/runs/${encodeURIComponent(runId)}/preview`, location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}
