import React, { useEffect, useRef, useState } from "react";
import { BACKEND_URL } from "../constants/theme";
import { decodePreviewPacket, frameSizing, previewWebSocketUrl } from "./protocol";

export default function LivePreview({ session, url }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [signal, setSignal] = useState({ status: "waiting", message: "" });
  const [hasFrame, setHasFrame] = useState(false);
  const [debug, setDebug] = useState(null);
  const debugEnabled = import.meta.env.DEV && (
    new URLSearchParams(window.location.search).get("debug") === "1" || import.meta.env.VITE_PREVIEW_DEBUG === "1"
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    let alive = true, socket, retryTimer, raf = null, decoding = false, ended = false;
    let latest = null, pending = null, attempts = 0;
    let wireStatus = { status: "waiting", message: "" };
    let bounds = container.getBoundingClientRect();
    let draws = 0, fps = 0, fpsAt = performance.now();
    setSignal({ status: "waiting", message: "" });
    setHasFrame(false);
    canvas.width = 0;
    canvas.height = 0;

    function size(frame) {
      const sizing = frameSizing(frame, bounds.width, bounds.height);
      canvas.style.width = `${sizing.cssWidth}px`;
      canvas.style.height = `${sizing.cssHeight}px`;
      if (debugEnabled && latest) setDebug({
        frameWidth: frame.width, frameHeight: frame.height,
        canvasWidth: canvas.width, canvasHeight: canvas.height,
        cssWidth: sizing.cssWidth, cssHeight: sizing.cssHeight,
        deviceScaleFactor: frame.deviceScaleFactor, devicePixelRatio: window.devicePixelRatio,
        fps, bytes: latest.bytes,
      });
    }
    function schedule() {
      if (!alive || document.hidden || decoding || raf !== null || !pending) return;
      raf = requestAnimationFrame(async () => {
        raf = null;
        const frame = pending;
        pending = null;
        decoding = true;
        let bitmap;
        try {
          bitmap = await createImageBitmap(new Blob([frame.image], { type: `image/${frame.metadata.format}` }));
          if (!alive || document.hidden) return;
          if (bitmap.width !== frame.metadata.width || bitmap.height !== frame.metadata.height) throw new Error("Image dimensions differ");
          if (canvas.width !== bitmap.width) canvas.width = bitmap.width;
          if (canvas.height !== bitmap.height) canvas.height = bitmap.height;
          canvas.getContext("2d").drawImage(bitmap, 0, 0);
          draws += 1;
          size(frame.metadata);
          setHasFrame(true);
          setSignal(wireStatus.status === "waiting" ? { status: "live", message: "" } : wireStatus);
        } catch {
          if (alive) setSignal({ status: "stalled", message: "" });
        } finally {
          bitmap?.close();
          decoding = false;
          schedule();
        }
      });
    }
    function visible() {
      if (!document.hidden && latest) { pending = latest; schedule(); }
    }
    const observer = new ResizeObserver(([entry]) => {
      bounds = entry.contentRect;
      if (latest) size(latest.metadata);
    });
    observer.observe(container);
    document.addEventListener("visibilitychange", visible);

    function connect() {
      if (!session?.runId || !session?.previewToken || ended || !alive) return;
      socket = new WebSocket(previewWebSocketUrl(session.runId, BACKEND_URL));
      socket.binaryType = "arraybuffer";
      socket.onopen = () => socket.send(JSON.stringify({ type: "auth", token: session.previewToken }));
      socket.onmessage = ({ data }) => {
        if (!alive) return;
        if (typeof data === "string") {
          try {
            const message = JSON.parse(data);
            if (message.type === "ping") socket.send(JSON.stringify({ type: "ping" }));
            if (message.type === "status") {
              attempts = 0;
              wireStatus = message;
              setSignal(message);
              if (message.status === "ended") { ended = true; socket.close(); }
            }
          } catch { /* Invalid control messages do not enter logs or persistent state. */ }
          return;
        }
        try {
          const frame = decodePreviewPacket(data);
          attempts = 0;
          if (latest?.metadata.seq === frame.metadata.seq && latest.metadata.tabId === frame.metadata.tabId) return;
          latest = frame;
          pending = frame;
          schedule();
        } catch { setSignal({ status: "stalled", message: "" }); }
      };
      socket.onclose = () => {
        if (!alive || ended) return;
        setSignal({ status: "stalled", message: "" });
        retryTimer = setTimeout(connect, Math.min(5000, 250 * 2 ** Math.min(attempts++, 5)));
      };
      socket.onerror = () => socket.close();
    }
    connect();
    const fpsTimer = debugEnabled ? setInterval(() => {
      const now = performance.now();
      fps = draws * 1000 / Math.max(1, now - fpsAt);
      draws = 0; fpsAt = now;
      if (latest) size(latest.metadata);
    }, 1000) : null;
    const pingTimer = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
    }, 20000);
    return () => {
      alive = false;
      clearInterval(pingTimer);
      clearInterval(fpsTimer);
      clearTimeout(retryTimer);
      if (raf !== null) cancelAnimationFrame(raf);
      observer.disconnect();
      document.removeEventListener("visibilitychange", visible);
      socket?.close();
      latest = pending = null;
      canvas.width = canvas.height = 0;
    };
  }, [session?.runId, session?.previewToken, debugEnabled]);

  const overlay = signal.status === "waiting" ? "Starting browser…"
    : signal.status === "stalled" ? "Waiting for the page…"
    : signal.status === "fallback" ? "Using low-frame-rate mode"
    : signal.status === "ended" ? "Run ended"
    : signal.message?.includes("idle") ? "Preview paused: page is idle" : "";
  return (
    <div ref={containerRef} data-preview-status={signal.status} className="relative h-full w-full overflow-hidden rounded-xl border border-[#5B9BE6]/35 bg-white">
      <div className="absolute inset-0 flex items-center justify-center overflow-hidden">
        <canvas ref={canvasRef} role="img" aria-label={`Live browser page at ${url || "the current URL"}`} style={{ maxWidth: "100%", maxHeight: "100%", display: hasFrame ? "block" : "none" }} />
      </div>
      {debugEnabled && debug && <output data-testid="preview-debug" className="pointer-events-none absolute right-3 top-3 rounded bg-black/80 px-3 py-2 font-mono text-[11px] leading-5 text-white">
        <div>Frame: {debug.frameWidth} × {debug.frameHeight} px · scale {debug.deviceScaleFactor}</div>
        <div>Canvas: {debug.canvasWidth} × {debug.canvasHeight} px</div>
        <div>CSS: {debug.cssWidth.toFixed(1)} × {debug.cssHeight.toFixed(1)} px</div>
        <div>DPR: {debug.devicePixelRatio} · FPS: {debug.fps.toFixed(1)} · Bytes: {debug.bytes}</div>
      </output>}
      {overlay && <div role="status" className={hasFrame ? "pointer-events-none absolute bottom-3 left-3 rounded bg-[#14305E]/90 px-3 py-2 font-mono text-xs text-[#D3E3F8]" : "absolute inset-0 flex items-center justify-center bg-[#14305E] p-6 text-center font-mono text-sm text-[#D3E3F8]"}>{overlay}</div>}
    </div>
  );
}
