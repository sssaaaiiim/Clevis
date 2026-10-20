// Coordinates use the actual drawn canvas rect, excluding its letterboxed surroundings.
export function mapPointer(clientX, clientY, rect, frame) {
  if (!frame || rect.width <= 0 || rect.height <= 0) return null;
  return {
    x: Math.min(frame.viewportWidth - 1, Math.max(0, (clientX - rect.left) * frame.viewportWidth / rect.width)),
    y: Math.min(frame.viewportHeight - 1, Math.max(0, (clientY - rect.top) * frame.viewportHeight / rect.height)),
  };
}
export function modifiers(event) {
  return (event.altKey ? 1 : 0) | (event.ctrlKey ? 2 : 0) | (event.metaKey ? 4 : 0) | (event.shiftKey ? 8 : 0);
}
export function keyMessage(event, action) {
  const shortcut = event.ctrlKey || event.metaKey;
  if (["F5", "F12"].includes(event.key) || (shortcut && ["w", "t", "l", "r"].includes(event.key.toLowerCase()))) return null;
  if (event.isComposing || event.key === "Process" || event.key === "Dead") return null;
  if (Array.from(event.key).length === 1 && !shortcut) return null;
  // Browser paste is relayed as text from its paste event, never from a server clipboard.
  if (shortcut && event.key.toLowerCase() === "v") return null;
  return { type: "key", action, key: event.key, code: event.code, modifiers: modifiers(event) };
}
export function wheelPixels(event, viewportHeight) {
  const factor = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewportHeight : 1;
  return { dx: Math.max(-10000, Math.min(10000, event.deltaX * factor)), dy: Math.max(-10000, Math.min(10000, event.deltaY * factor)) };
}
// Callback emission avoids accumulating a second array of private paste/IME contents.
export function sendTextChunks(text, send, maxLength = 2000, maxBytes = 8192) {
  const encoder = new TextEncoder();
  const overhead = encoder.encode(JSON.stringify({ type: "text", value: "" })).length;
  let chunk = "", count = 0, bytes = overhead;
  for (const char of text) {
    const charBytes = encoder.encode(JSON.stringify(char).slice(1, -1)).length;
    if (count && (count >= maxLength || bytes + charBytes > maxBytes)) {
      send({ type: "text", value: chunk }); chunk = ""; count = 0; bytes = overhead;
    }
    chunk += char; count += 1; bytes += charBytes;
  }
  if (chunk) send({ type: "text", value: chunk });
}

// Chromium PointerEvent.detail is zero; retain only transient click timing/position as fallback.
export function nextClick(event, previous, now) {
  const repeat = previous && now - previous.time < 500 && previous.button === event.button &&
    Math.abs(previous.x - event.clientX) <= 4 && Math.abs(previous.y - event.clientY) <= 4;
  const count = event.detail > 0 ? Math.min(3, event.detail) : repeat ? Math.min(3, previous.count + 1) : 1;
  return { count, time: now, x: event.clientX, y: event.clientY, button: event.button };
}
