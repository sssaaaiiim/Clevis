import { useEffect, useState } from "react";
import { BACKEND_URL } from "../constants/theme";
import { previewWebSocketUrl } from "./protocol";
import { keyMessage, mapPointer, modifiers, sendTextChunks, wheelPixels } from "./input";

export default function useInputControl(session, active, canvasRef, editorRef, frameRef) {
  const [state, setState] = useState({ accepting: false, controller: false, otherWindow: false });
  useEffect(() => {
    setState({ accepting: false, controller: false, otherWindow: false });
    if (!active || !session?.controlToken) return;
    const canvas = canvasRef.current, editor = editorRef.current;
    let alive = true, accepting = false, composing = false, lastMove = -Infinity;
    const socket = new WebSocket(previewWebSocketUrl(session.runId, BACKEND_URL).replace(/\/preview$/, "/input"));
    const send = message => {
      if (alive && accepting && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
    };
    socket.onopen = () => socket.send(JSON.stringify({ type: "auth", token: session.controlToken }));
    socket.onmessage = ({ data }) => {
      if (!alive || typeof data !== "string") return;
      try {
        const message = JSON.parse(data);
        if (message.type === "state") {
          const wasAccepting = accepting;
          accepting = message.accepting === true;
          setState({ accepting, controller: message.controller === true, otherWindow: false });
          if (accepting && !wasAccepting) { canvas.focus({ preventScroll: true }); editor.focus({ preventScroll: true }); }
        }
      } catch { /* Private socket messages are never sent to logs or error reports. */ }
    };
    socket.onclose = event => {
      accepting = false;
      if (alive) setState({ accepting: false, controller: false, otherWindow: event.code === 4409 });
    };
    socket.onerror = () => socket.close();
    const heartbeat = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
    }, 20000);
    const listeners = [];
    function on(element, type, handler, options) {
      element.addEventListener(type, handler, options); listeners.push(() => element.removeEventListener(type, handler, options));
    }
    function point(event) { return mapPointer(event.clientX, event.clientY, canvas.getBoundingClientRect(), frameRef.current); }
    for (const [type, action] of [["pointerdown", "down"], ["pointerup", "up"], ["pointermove", "move"]]) {
      on(canvas, type, event => {
        if (!accepting || ![0, 1, 2].includes(event.button) && action !== "move") return;
        if (action === "move") {
          const now = performance.now(); if (now - lastMove < 1000 / 60) return; lastMove = now;
        }
        const xy = point(event); if (!xy) return;
        event.preventDefault();
        if (action === "down") {
          canvas.setPointerCapture?.(event.pointerId);
          editor.focus({ preventScroll: true });
        }
        send({ type: "mouse", action, ...xy, button: ["left", "middle", "right"][Math.max(0, event.button)] || "left", clickCount: Math.min(3, Math.max(1, event.detail)), modifiers: modifiers(event) });
      });
    }
    on(canvas, "contextmenu", event => { if (accepting) event.preventDefault(); });
    on(canvas, "wheel", event => {
      if (!accepting) return;
      const xy = point(event); if (!xy) return;
      event.preventDefault();
      send({ type: "wheel", ...xy, ...wheelPixels(event, frameRef.current.viewportHeight) });
    }, { passive: false });
    for (const element of [canvas, editor]) {
      for (const [type, action] of [["keydown", "down"], ["keyup", "up"]]) on(element, type, event => {
        if (!accepting) return;
        const message = keyMessage(event, action);
        if (!message) return;
        // Tab reaches the remote form AND remains available to leave the preview for Resume.
        if (event.key !== "Tab") event.preventDefault();
        send(message);
      });
      on(element, "paste", event => {
        if (!accepting) return;
        event.preventDefault(); sendTextChunks(event.clipboardData.getData("text/plain"), send); editor.value = "";
      });
    }
    on(canvas, "focus", () => { if (accepting) editor.focus({ preventScroll: true }); });
    on(editor, "compositionstart", () => { composing = true; });
    on(editor, "compositionend", event => {
      composing = false;
      if (accepting && event.data) sendTextChunks(event.data, send);
      editor.value = "";
    });
    on(editor, "beforeinput", event => {
      if (!accepting || composing || event.isComposing) return;
      if (event.inputType === "insertFromComposition") { event.preventDefault(); editor.value = ""; return; }
      if (event.inputType === "insertText" && event.data) {
        event.preventDefault(); sendTextChunks(event.data, send); editor.value = "";
      }
    });
    on(editor, "input", event => {
      if (composing || event.isComposing) return;
      if (accepting && editor.value && event.inputType !== "insertFromComposition") sendTextChunks(editor.value, send);
      editor.value = "";
    });
    return () => {
      alive = false; accepting = false;
      listeners.forEach(remove => remove()); clearInterval(heartbeat); socket.close(); editor.value = "";
    };
  }, [session?.runId, session?.controlToken, active, canvasRef, editorRef, frameRef]);
  return state;
}
