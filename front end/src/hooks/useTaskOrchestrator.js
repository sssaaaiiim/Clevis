import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BACKEND_URL } from "../constants/theme";

const HISTORY_KEY = "wto_history";

function now() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
}

function readHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function humanSize(bytes) {
  if (!bytes && bytes !== 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function useTaskOrchestrator() {
  const [status, setStatus] = useState("Idle");

  // URL is optional: when blank the backend picks a starting page from the task.
  const [url, setUrl] = useState("");
  const [timeoutVal, setTimeoutVal] = useState("30");
  const [maxSteps, setMaxSteps] = useState("10");
  const [headless, setHeadless] = useState(true);
  const [task, setTask] = useState("");

  const [paramOpen, setParamOpen] = useState(false);
  const [attachments, setAttachments] = useState([]);

  const [plan, setPlan] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [logs, setLogs] = useState([]);
  const [result, setResult] = useState(null);

  // Live signals streamed from the backend
  const [tokens, setTokens] = useState(0);
  const [targetUrl, setTargetUrl] = useState("");
  const [screenshotUrl, setScreenshotUrl] = useState("");
  const [previewSession, setPreviewSession] = useState(null);
  const [screenshotError, setScreenshotError] = useState("");

  const [runStartedAt, setRunStartedAt] = useState(null);
  const [runEndedAt, setRunEndedAt] = useState(null);
  const [tick, setTick] = useState(0);

  const [history, setHistory] = useState(readHistory);

  const abortRef = useRef(null);
  const runIdRef = useRef(null);
  const stopRequestedRef = useRef(false);
  const planRef = useRef([]);
  const planLenRef = useRef(0);
  const isRunning = ["Planning", "Running", "Validating"].includes(status);

  // 1s heartbeat so the duration timer ticks while a run is active
  useEffect(() => {
    if (!runStartedAt || runEndedAt) return;
    const id = setInterval(() => setTick((v) => v + 1), 1000);
    return () => clearInterval(id);
  }, [runStartedAt, runEndedAt]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    []
  );

  const activeStepLabel = useMemo(() => {
    if (!plan.length) return "";
    return plan[Math.min(activeIndex, plan.length - 1)]?.label ?? "";
  }, [plan, activeIndex]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const elapsedSeconds = useMemo(() => {
    if (!runStartedAt) return 0;
    const end = runEndedAt ?? Date.now();
    return Math.max(0, Math.floor((end - runStartedAt) / 1000));
  }, [runStartedAt, runEndedAt, tick]);

  const pushLog = useCallback((actor, msg) => {
    setLogs((prev) => [...prev, { t: actor || "System", m: msg || "", time: now() }]);
  }, []);

  const applyTemplate = useCallback((tpl) => {
    setTask(tpl.task);
    setUrl(tpl.url);
  }, []);

  const addFiles = useCallback((fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setAttachments((prev) => [
      ...prev,
      ...files.map((f) => ({ id: `${Date.now()}-${Math.random()}`, name: f.name, size: f.size, type: f.type, file: f })),
    ]);
  }, []);

  const removeFile = useCallback((id) => {
    setAttachments((prev) => prev.filter((f) => f.id !== id));
  }, []);

  const persistRun = useCallback(
    (evtResult, snapshot) => {
      try {
        const existing = readHistory();
        existing.unshift({
          id: `run-${Date.now()}`,
          task: snapshot.task,
          url: snapshot.url || "(auto)",
          status: evtResult.status === "success" ? "Completed" : "Failed",
          when: new Date().toLocaleString(),
          steps: planLenRef.current || Number(snapshot.maxSteps) || 0,
          detail: evtResult.message || "",
        });
        const trimmed = existing.slice(0, 50);
        localStorage.setItem(HISTORY_KEY, JSON.stringify(trimmed));
        setHistory(trimmed);
      } catch {
        // localStorage unavailable -> graceful fallback
      }
    },
    []
  );

  const clearHistory = useCallback(() => {
    try {
      localStorage.removeItem(HISTORY_KEY);
    } catch {
      // ignore
    }
    setHistory([]);
  }, []);

  const reuseHistoryItem = useCallback((item) => {
    setTask(item.task || "");
    setUrl(item.url && item.url !== "(auto)" ? item.url : "");
  }, []);

  const stopRun = useCallback(() => {
    const runId = runIdRef.current;
    if (!runId && !abortRef.current) return;
    stopRequestedRef.current = true;
    if (runId) {
      void fetch(`${BACKEND_URL}/api/runs/${encodeURIComponent(runId)}/stop`, { method: "POST" }).catch((error) => {
        pushLog("System", error?.message || "Could not contact the backend to stop the run.");
      });
      abortRef.current?.abort();
      abortRef.current = null;
      runIdRef.current = null;
    }
    setRunEndedAt(Date.now());
    setStatus("Stopped");
    setResult({ status: "error", message: "Run stopped by operator." });
    pushLog("System", "Run stopped by operator. Browser instance is being released.");
  }, [pushLog]);

  const runTask = useCallback(async () => {
    if (!task.trim()) return;

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    stopRequestedRef.current = false;

    const snapshot = { task, url, maxSteps };
    let gotTerminalEvent = false;
    planLenRef.current = 0;

    setResult(null);
    setPlan([]);
    setLogs([]);
    setActiveIndex(0);
    setTokens(0);
    setTargetUrl(url.trim());
    setScreenshotUrl("");
    setPreviewSession(null);
    setScreenshotError("");
    setStatus("Planning");
    setRunEndedAt(null);
    setRunStartedAt(Date.now());

    pushLog("Planner", "Task accepted. Initializing browser orchestration session.");

    try {
      const startUrl = url.trim()
        ? /^https?:\/\//i.test(url.trim())
          ? url.trim()
          : `https://${url.trim()}`
        : undefined;
      const res = await fetch(`${BACKEND_URL}/api/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: startUrl ? `${task}\nStart at: ${startUrl}` : task,
          mode: headless ? "headless" : "headed",
        }),
        signal: ctrl.signal,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const message = body.error?.message || (typeof body.error === "string" ? body.error : "") || `Backend request failed (${res.status}).`;
        setStatus("Failed");
        setRunEndedAt(Date.now());
        setResult({ status: "error", message });
        pushLog("System", message);
        return;
      }

      const { runId, previewToken } = await res.json();
      setPreviewSession({ runId, previewToken });
      runIdRef.current = runId;
      if (stopRequestedRef.current) {
        void fetch(`${BACKEND_URL}/api/runs/${encodeURIComponent(runId)}/stop`, { method: "POST" }).catch((error) => {
          pushLog("System", error?.message || "Could not contact the backend to stop the run.");
        });
        ctrl.abort();
        return;
      }
      const eventsResponse = await fetch(
        `${BACKEND_URL}/api/runs/${encodeURIComponent(runId)}/events`,
        { signal: ctrl.signal, headers: { Accept: "text/event-stream" } }
      );
      if (!eventsResponse.ok || !eventsResponse.body) {
        throw new Error(`Could not connect to run events (${eventsResponse.status}).`);
      }

      const reader = eventsResponse.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const handleEvent = (block) => {
        const data = block.split("\n").find((line) => line.startsWith("data:"))?.slice(5).trim();
        if (!data) return;
        let evt;
        try {
          evt = JSON.parse(data);
        } catch {
          pushLog("System", "The backend sent an invalid event.");
          return;
        }
        switch (evt.type) {
          case "run.started":
            setStatus("Planning");
            break;
          case "plan.created": {
            const steps = Array.isArray(evt.data?.steps) ? evt.data.steps : [];
            planLenRef.current = steps.length;
            const nextPlan = steps.map((step) => ({ id: step.id, label: step.label }));
            planRef.current = nextPlan;
            setPlan(nextPlan);
            setStatus("Running");
            break;
          }
          case "step.proposed": {
            const rationale = evt.data || {};
            const stepIndex = planRef.current.findIndex((step) => step.label === rationale.step);
            if (stepIndex >= 0) setActiveIndex(stepIndex);
            pushLog(
              "Agent",
              `${rationale.goal || task} → ${rationale.step || "Step"}: ${rationale.action || "Action"}. ${rationale.why || ""}`
            );
            break;
          }
          case "step.executed":
            pushLog("Browser", evt.data?.result || "Action executed.");
            break;
          case "observation.summary":
            pushLog("Browser", evt.data?.summary || "Observed the current page.");
            break;
          case "budget.update":
            setTokens(Number(evt.data?.tokens) || 0);
            break;
          case "run.finished": {
            gotTerminalEvent = true;
            const r = { status: "success", message: evt.data?.result || "Task finished." };
            setResult(r);
            setStatus("Completed");
            setRunEndedAt(Date.now());
            runIdRef.current = null;
            persistRun(r, snapshot);
            break;
          }
          case "run.failed": {
            gotTerminalEvent = true;
            const message = evt.data?.reason || "The run failed.";
            const r = { status: "error", message };
            setResult(r);
            setStatus("Failed");
            setRunEndedAt(Date.now());
            runIdRef.current = null;
            pushLog("System", message);
            persistRun(r, snapshot);
            break;
          }
          case "run.stopped":
            gotTerminalEvent = true;
            setStatus("Stopped");
            setRunEndedAt(Date.now());
            setResult({ status: "error", message: evt.data?.reason || "Run stopped by operator." });
            runIdRef.current = null;
            break;
          default:
            break;
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || "";
        for (const block of blocks) {
          handleEvent(block);
        }
      }

      if (buffer.trim()) handleEvent(buffer);
      if (!gotTerminalEvent && !ctrl.signal.aborted) {
        setStatus("Failed");
        setRunEndedAt(Date.now());
        const message = "Connection closed before the agent reported a result.";
        setResult({ status: "error", message });
        pushLog("System", "Stream ended unexpectedly.");
      }
    } catch (err) {
      if (err?.name === "AbortError") return; // stopRun() already updated the UI
      const msg = err?.message || "Unexpected execution error.";
      setStatus("Failed");
      setRunEndedAt(Date.now());
      setResult({ status: "error", message: msg });
      pushLog("System", msg);
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
    }
  }, [task, url, maxSteps, timeoutVal, headless, pushLog, persistRun]);

  return {
    status,
    url,
    setUrl,
    timeoutVal,
    setTimeoutVal,
    maxSteps,
    setMaxSteps,
    headless,
    setHeadless,
    task,
    setTask,
    paramOpen,
    setParamOpen,
    attachments,
    addFiles,
    removeFile,
    plan,
    activeIndex,
    logs,
    result,
    activeStepLabel,
    isRunning,
    applyTemplate,
    runTask,
    stopRun,
    elapsedSeconds,
    tokens,
    targetUrl,
    screenshotUrl,
    screenshotError,
    previewSession,
    history,
    clearHistory,
    reuseHistoryItem,
  };
}
