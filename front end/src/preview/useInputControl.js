import { useCallback, useEffect, useState } from "react";
import { BACKEND_URL } from "../constants/theme";
import { previewWebSocketUrl } from "./protocol";
import { keyMessage, mapPointer, modifiers, nextClick, sendTextChunks, wheelPixels } from "./input";

export default function useInputControl(session, active, canvasRef, editorRef, frameRef) {
  const [state, setState] = useState({ accepting: false, controller: false, otherWindow: false });
  const [attempt, setAttempt] = useState(0);
  const reconnect = useCallback(() => setAttempt(value => value + 1), []);
  useEffect(() => {
    setState({ accepting: false, controller: false, otherWindow: false });
    if (!active || !session?.controlToken) return;
    const canvas = canvasRef.current, editor = editorRef.current;
    let alive = true, accepting = false, composing = false, lastMove = -Infinity;
    let maxTextLength = 2000, maxMessageBytes = 8192, lastClick = null, relayError = "";
    const socket = new WebSocket(previewWebSocketUrl(session.runId, BACKEND_URL).replace(/\/preview$/, "/input"));
    const send = message => {
      if (alive && accepting && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
    };
    const sendText = text => sendTextChunks(text, send, maxTextLength, maxMessageBytes);
    socket.onopen = () => socket.send(JSON.stringify({ type: "auth", token: session.controlToken }));
    socket.onmessage = ({ data }) => {
      if (!alive || typeof data !== "string") return;
      try {
        const message = JSON.parse(data);
        if (message.type === "error") {
          relayError = "Browser input could not be delivered. Reconnect control and try again.";
          accepting = false;
          setState({ accepting: false, controller: false, otherWindow: false, error: relayError });
          socket.close();
          return;
        }
        if (message.type === "state") {
          const limits = message.limits;
          if (Number.isInteger(limits?.maxTextLength) && limits.maxTextLength > 0) maxTextLength = limits.maxTextLength;
          if (Number.isInteger(limits?.maxMessageBytes) && limits.maxMessageBytes >= 128) maxMessageBytes = limits.maxMessageBytes;
          const wasAccepting = accepting;
          accepting = message.accepting === true;
          setState({ accepting, controller: message.controller === true, otherWindow: false });
          if (accepting && !wasAccepting) { canvas.focus({ preventScroll: true }); editor.focus({ preventScroll: true }); }
        }
      } catch { /* Private socket messages are never sent to logs or error reports. */ }
    };
    socket.onclose = event => {
      accepting = false;
      const errors = {
        4401: "Control authorization expired. Start a new run.",
        4403: "Control blocked: frontend address does not match server settings.",
        4404: "Run not found. Start a new run.",
        4409: "Control taken by another window",
      };
      if (alive) setState({ accepting: false, controller: false, otherWindow: event.code === 4409,
        error: relayError || errors[event.code] || "Control connection lost. Reconnect control to continue." });
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
          lastClick = nextClick(event, lastClick, performance.now());
          canvas.setPointerCapture?.(event.pointerId);
          editor.focus({ preventScroll: true });
        }
        send({ type: "mouse", action, ...xy, button: ["left", "middle", "right"][event.button] || (event.buttons & 2 ? "right" : event.buttons & 4 ? "middle" : "left"), clickCount: lastClick?.count || 1, modifiers: modifiers(event) });
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
        event.preventDefault(); sendText(event.clipboardData.getData("text/plain")); editor.value = "";
      });
    }
    on(canvas, "focus", () => { if (accepting) editor.focus({ preventScroll: true }); });
    on(editor, "compositionstart", () => { composing = true; });
    on(editor, "compositionend", event => {
      composing = false;
      if (accepting && event.data) sendText(event.data);
      editor.value = "";
    });
    on(editor, "beforeinput", event => {
      if (!accepting || composing || event.isComposing) return;
      if (event.inputType === "insertFromComposition") { event.preventDefault(); editor.value = ""; return; }
      const mobileKey = { deleteContentBackward: "Backspace", deleteContentForward: "Delete", insertLineBreak: "Enter", insertParagraph: "Enter" }[event.inputType];
      if (mobileKey) {
        event.preventDefault();
        for (const action of ["down", "up"]) send({ type: "key", action, key: mobileKey, code: mobileKey, modifiers: 0 });
        editor.value = "";
      }
      if (event.inputType === "insertText" && event.data) {
        event.preventDefault(); sendText(event.data); editor.value = "";
      }
    });
    on(editor, "input", event => {
      if (composing || event.isComposing) return;
      if (accepting && editor.value && !/Composition/.test(event.inputType || "")) sendText(editor.value);
      editor.value = "";
    });
    return () => {
      alive = false; accepting = false; lastClick = null;
      listeners.forEach(remove => remove()); clearInterval(heartbeat); socket.close(); editor.value = "";
    };
  }, [session?.runId, session?.controlToken, active, canvasRef, editorRef, frameRef, attempt]);
  return { ...state, reconnect };
}
