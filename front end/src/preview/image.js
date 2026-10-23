// Decoding stays in memory; callers release the bitmap/object URL after drawing.
export async function decodeFrameImage(frame) {
  const blob = new Blob([frame.image], { type: `image/${frame.metadata.format}` });
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(blob);
      return { source: bitmap, width: bitmap.width, height: bitmap.height, close: () => bitmap.close() };
    } catch { /* Try the browser's image decoder before reporting a bad frame. */ }
  }
  const url = URL.createObjectURL(blob);
  const source = new Image();
  try {
    await new Promise((resolve, reject) => {
      source.onload = resolve;
      source.onerror = () => reject(new Error("Unable to decode preview image"));
      source.src = url;
    });
    return { source, width: source.naturalWidth, height: source.naturalHeight, close: () => URL.revokeObjectURL(url) };
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
}
