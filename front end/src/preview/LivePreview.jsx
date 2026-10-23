import React, { useEffect, useRef, useState } from "react";
import useInputControl from "./useInputControl";
import { decodeFrameImage } from "./image";
import { BACKEND_URL } from "../constants/theme";
import { decodePreviewPacket, frameSizing, previewWebSocketUrl } from "./protocol";

export default function LivePreview({ session, url, control }) {
  const canvasRef = useRef(null);
  const editorRef = useRef(null);
  const frameRef = useRef(null);
  const inputState = useInputControl(session, Boolean(control?.active), canvasRef, editorRef, frameRef);
  const containerRef = useRef(null);
  const [signal, setSignal] = useState({ status: "waiting", message: "" });
  const [hasFrame, setHasFrame] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [debug, setDebug] = useState(null);
  const debugEnabled = import.meta.env.DEV && (
    new URLSearchParams(window.location.search).get("debug") === "1" || import.meta.env.VITE_PREVIEW_DEBUG === "1"
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    let alive = true, socket, retryTimer, raf = null, decoding = false, ended = false, blocked = false;
    let latest = null, pending = null, displayed = null, attempts = 0;
    let wireStatus = { status: "waiting", message: "" };
    let bounds = container.getBoundingClientRect();
    let draws = 0, fps = 0, fpsAt = performance.now();
    setSignal({ status: "waiting", message: "" });
    setHasFrame(false);
    setPreviewError("");
    canvas.width = 0;
    canvas.height = 0;

    function size(frame) {
      const sizing = frameSizing(frame, bounds.width, bounds.height);
      canvas.style.width = `${sizing.cssWidth}px`;
      canvas.style.height = `${sizing.cssHeight}px`;
      if (debugEnabled && displayed) setDebug({
        frameWidth: frame.width, frameHeight: frame.height,
        canvasWidth: canvas.width, canvasHeight: canvas.height,
        cssWidth: sizing.cssWidth, cssHeight: sizing.cssHeight,
        deviceScaleFactor: frame.deviceScaleFactor, devicePixelRatio: window.devicePixelRatio,
        fps, bytes: displayed.bytes, seq: frame.seq, tabId: frame.tabId,
      });
    }
    function schedule() {
      if (!alive || document.hidden || decoding || raf !== null || !pending || bounds.width <= 0 || bounds.height <= 0) return;
      raf = requestAnimationFrame(async () => {
        raf = null;
        const frame = pending;
        pending = null;
        decoding = true;
        let bitmap;
        try {
          bitmap = await decodeFrameImage(frame);
          if (!alive || document.hidden) return;
          if (bounds.width <= 0 || bounds.height <= 0) { pending = latest; return; }
          if (bitmap.width !== frame.metadata.width || bitmap.height !== frame.metadata.height) throw new Error("Image dimensions differ");
          if (canvas.width !== bitmap.width) canvas.width = bitmap.width;
          if (canvas.height !== bitmap.height) canvas.height = bitmap.height;
          canvas.getContext("2d").drawImage(bitmap.source, 0, 0);
          displayed = frame;
          frameRef.current = frame.metadata;
          draws += 1;
          size(frame.metadata);
          setHasFrame(true);
          setPreviewError("");
          setSignal(wireStatus.status === "waiting" ? { status: "live", message: "" } : wireStatus);
        } catch {
          if (alive) {
            setSignal({ status: "stalled", message: "" });
            setPreviewError("Frame could not be displayed; waiting for another frame.");
          }
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
      if (displayed) size(displayed.metadata);
      schedule();
    });
    observer.observe(container);
    document.addEventListener("visibilitychange", visible);

    function connect() {
      if (!session?.runId || !session?.previewToken || ended || blocked || !alive) return;
      const connection = new WebSocket(previewWebSocketUrl(session.runId, BACKEND_URL));
      socket = connection;
      connection.binaryType = "arraybuffer";
      connection.onopen = () => {
        if (alive && connection === socket) connection.send(JSON.stringify({ type: "auth", token: session.previewToken }));
      };
      connection.onmessage = ({ data }) => {
        if (!alive || connection !== socket) return;
        if (typeof data === "string") {
          try {
            const message = JSON.parse(data);
            if (message.type === "ping") socket.send(JSON.stringify({ type: "ping" }));
            if (message.type === "status") {
              attempts = 0;
              wireStatus = message;
              setSignal(message);
              if (message.status === "ended") { ended = true; setPreviewError(""); socket.close(); }
            }
          } catch { /* Invalid control messages do not enter logs or persistent state. */ }
          return;
        }
        try {
          const frame = decodePreviewPacket(data);
          attempts = 0;
          if (displayed?.metadata.seq === frame.metadata.seq && displayed.metadata.tabId === frame.metadata.tabId) {
            setPreviewError("");
            setSignal(wireStatus.status === "waiting" ? { status: "live", message: "" } : wireStatus);
            return;
          }
          latest = frame;
          pending = frame;
          schedule();
        } catch {
          setSignal({ status: "stalled", message: "" });
          setPreviewError("Frame could not be displayed; waiting for another frame.");
        }
      };
      connection.onclose = (event = {}) => {
        if (!alive || ended || connection !== socket) return;
        const errors = {
          4401: "Preview authorization expired. Start a new run.",
          4403: "Preview blocked: frontend address does not match server settings.",
          4404: "Run not found. Start a new run.",
        };
        blocked = Boolean(errors[event.code]);
        setSignal({ status: "stalled", message: "" });
        setPreviewError(errors[event.code] || "Preview disconnected; reconnecting…");
        if (!blocked) retryTimer = setTimeout(connect, Math.min(5000, 250 * 2 ** Math.min(attempts++, 5)));
      };
      connection.onerror = () => connection.close();
    }
    connect();
    const fpsTimer = debugEnabled ? setInterval(() => {
      const now = performance.now();
      fps = draws * 1000 / Math.max(1, now - fpsAt);
      draws = 0; fpsAt = now;
      if (displayed) size(displayed.metadata);
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
      latest = pending = displayed = null;
      frameRef.current = null;
      canvas.width = canvas.height = 0;
    };
  }, [session?.runId, session?.previewToken, debugEnabled]);

  const overlay = previewError || (signal.status === "ended" ? (hasFrame ? "Run ended" : "Run ended before a preview became available.")
    : signal.status === "waiting" ? "Starting browser…"
    : signal.status === "stalled" ? "Waiting for the page…"
    : signal.status === "fallback" ? "Using low-frame-rate mode"
    : !hasFrame ? "Waiting for browser preview…"
    : signal.message?.includes("idle") ? "Preview paused: page is idle" : "");
  return (
    <div ref={containerRef} data-preview-status={signal.status} className="relative h-full w-full overflow-hidden rounded-xl border border-[#5B9BE6]/35 bg-white">
      <div className="absolute inset-0 flex items-center justify-center overflow-hidden">
        <canvas ref={canvasRef} tabIndex={control?.active ? 0 : -1} role="img" aria-label={`Live browser page at ${url || "the current URL"}`} style={{ maxWidth: "100%", maxHeight: "100%", display: hasFrame ? "block" : "none" }} />
      </div>
      <textarea ref={editorRef} tabIndex={-1} aria-label="Private browser typing" autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false} data-private="true" data-1p-ignore data-lpignore="true" style={{ position: "absolute", opacity: 0, width: 1, height: 1, left: 0, top: 0, pointerEvents: "none" }} />
      {control?.active && <div role="status" className="pointer-events-none absolute left-3 right-3 top-3 rounded bg-[#14305E]/95 p-3 text-xs text-white" title="Your typing goes straight to the browser; it is not shown to the AI.">
        <p>You are in control. The agent is paused</p>
        {control.reason === "handoff" && <p>The agent needs you: {control.message}</p>}
        {!inputState.accepting && <p>{inputState.error || "Browser is not accepting input"}</p>}
        {inputState.error && <button type="button" className="pointer-events-auto mt-2 rounded border border-white/50 px-2 py-1" onClick={inputState.reconnect}>Reconnect control</button>}
      </div>}
      {debugEnabled && debug && <output data-testid="preview-debug" data-preview-seq={debug.seq} data-preview-tab={debug.tabId} className="pointer-events-none absolute right-3 top-3 rounded bg-black/80 px-3 py-2 font-mono text-[11px] leading-5 text-white">
        <div>Frame: {debug.frameWidth} × {debug.frameHeight} px · scale {debug.deviceScaleFactor}</div>
        <div>Canvas: {debug.canvasWidth} × {debug.canvasHeight} px</div>
        <div>CSS: {debug.cssWidth.toFixed(1)} × {debug.cssHeight.toFixed(1)} px</div>
        <div>DPR: {debug.devicePixelRatio} · FPS: {debug.fps.toFixed(1)} · Bytes: {debug.bytes}</div>
      </output>}
      {overlay && <div role="status" className={hasFrame ? "pointer-events-none absolute bottom-3 left-3 rounded bg-[#14305E]/90 px-3 py-2 font-mono text-xs text-[#D3E3F8]" : "absolute inset-0 flex items-center justify-center bg-[#14305E] p-6 text-center font-mono text-sm text-[#D3E3F8]"}>{overlay}</div>}
    </div>
  );
}
