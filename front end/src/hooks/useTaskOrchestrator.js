import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BACKEND_URL, KNOWN_STATUS } from "../constants/theme";

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
  const [browserTabId, setBrowserTabId] = useState("");
  const [screenshotUrl, setScreenshotUrl] = useState("");
  const [screenshotError, setScreenshotError] = useState("");

  const [runStartedAt, setRunStartedAt] = useState(null);
  const [runEndedAt, setRunEndedAt] = useState(null);
  const [tick, setTick] = useState(0);

  const [history, setHistory] = useState(readHistory);

  const abortRef = useRef(null);
  const planLenRef = useRef(0);
  const screenshotObjectUrlRef = useRef("");
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
      if (screenshotObjectUrlRef.current) {
        URL.revokeObjectURL(screenshotObjectUrlRef.current);
      }
    },
    []
  );

  useEffect(() => {
    if (!isRunning || !browserTabId) return undefined;

    let stopped = false;
    let timeoutId;
    let requestController;

    const capture = async () => {
      requestController = new AbortController();
      try {
        const response = await fetch(
          `${BACKEND_URL}/api/screenshot?tab_id=${encodeURIComponent(browserTabId)}`,
          { signal: requestController.signal, cache: "no-store" }
        );
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(body.detail || `Screenshot request failed (${response.status}).`);
        }

        const nextObjectUrl = URL.createObjectURL(await response.blob());
        if (stopped) {
          URL.revokeObjectURL(nextObjectUrl);
          return;
        }
        if (screenshotObjectUrlRef.current) {
          URL.revokeObjectURL(screenshotObjectUrlRef.current);
        }
        screenshotObjectUrlRef.current = nextObjectUrl;
        setScreenshotUrl(nextObjectUrl);
        setScreenshotError("");
      } catch (error) {
        if (!stopped && error?.name !== "AbortError") {
          setScreenshotError(error?.message || "Browser screenshot unavailable.");
        }
      } finally {
        if (!stopped) timeoutId = setTimeout(capture, 900);
      }
    };

    capture();
    return () => {
      stopped = true;
      clearTimeout(timeoutId);
      requestController?.abort();
    };
  }, [isRunning, browserTabId]);

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
    if (!abortRef.current) return;
    abortRef.current.abort();
    abortRef.current = null;
    setRunEndedAt(Date.now());
    setStatus("Idle");
    pushLog("System", "Run stopped by operator. Browser instance is being released.");
  }, [pushLog]);

  const runTask = useCallback(async () => {
    if (!task.trim()) return;

    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const snapshot = { task, url, maxSteps };
    let gotResult = false;
    planLenRef.current = 0;

    setResult(null);
    setPlan([]);
    setLogs([]);
    setActiveIndex(0);
    setTokens(0);
    setTargetUrl(url.trim());
    setBrowserTabId("");
    if (screenshotObjectUrlRef.current) {
      URL.revokeObjectURL(screenshotObjectUrlRef.current);
      screenshotObjectUrlRef.current = "";
    }
    setScreenshotUrl("");
    setScreenshotError("");
    setStatus("Planning");
    setRunEndedAt(null);
    setRunStartedAt(Date.now());

    pushLog("Planner", "Task accepted. Initializing browser orchestration session.");

    try {
      const payload = {
        url: url.trim(),
        task,
        max_steps: Math.max(1, Number(maxSteps) || 10),
        timeout: Math.max(10, Number(timeoutVal) || 30),
        headless,
      };

      const res = await fetch(`${BACKEND_URL}/api/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: ctrl.signal,
      });

      if (!res.ok) {
        const text = await res.text();
        setStatus("Failed");
        setRunEndedAt(Date.now());
        setResult({ status: "error", message: `Backend ${res.status}: ${text}` });
        pushLog("System", `Backend error ${res.status}.`);
        return;
      }

      if (!res.body) {
        setStatus("Failed");
        setRunEndedAt(Date.now());
        setResult({ status: "error", message: "No response stream body." });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const t = line.trim();
          if (!t) continue;

          let evt;
          try {
            evt = JSON.parse(t);
          } catch {
            pushLog("System", `Malformed stream chunk: ${t.slice(0, 80)}...`);
            continue;
          }

          switch (evt.event) {
            case "status": {
              const next = KNOWN_STATUS.includes(evt.status) ? evt.status : null;
              if (next) setStatus(next);
              break;
            }
            case "log":
              pushLog(evt.actor ?? "System", evt.msg ?? "");
              break;
            case "plan": {
              const steps = Array.isArray(evt.steps) ? evt.steps : [];
              planLenRef.current = steps.length;
              setPlan(
                steps.map((s, i) => ({
                  id: i + 1,
                  label: typeof s === "string" ? s : s?.label ?? `Step ${i + 1}`,
                }))
              );
              break;
            }
            case "step":
              setActiveIndex(typeof evt.index === "number" ? evt.index : 0);
              break;
            case "usage":
              if (typeof evt.tokens === "number") setTokens(evt.tokens);
              break;
            case "layout_comparison":
              {
                const direction = evt.reduction_percent >= 0 ? "smaller" : "larger";
                const tokenDirection = evt.tokens_saved_estimate >= 0 ? "saved" : "more";
                pushLog(
                  "Telemetry",
                  `Layout baseline: HTML ${evt.html_bytes} B → snapshot ${evt.snapshot_bytes} B (${Math.abs(evt.reduction_percent)}% ${direction}; ~${Math.abs(evt.tokens_saved_estimate)} tokens ${tokenDirection}).`
                );
                break;
              }
            case "target":
              if (typeof evt.url === "string") setTargetUrl(evt.url);
              break;
            case "browser_tab":
              if (typeof evt.tab_id === "string") setBrowserTabId(evt.tab_id);
              break;
            case "result": {
              gotResult = true;
              const r = { status: evt.status ?? "error", message: evt.message ?? "Task finished." };
              setResult(r);
              setStatus(r.status === "success" ? "Completed" : "Failed");
              setRunEndedAt(Date.now());
              persistRun(r, snapshot);
              break;
            }
            default:
              break;
          }
        }
      }

      // Stream closed without a result event (backend crash / proxy drop)
      if (!gotResult && !ctrl.signal.aborted) {
        setStatus("Failed");
        setRunEndedAt(Date.now());
        setResult({ status: "error", message: "Connection closed before the agent reported a result." });
        pushLog("System", "Stream ended unexpectedly.");
      }
    } catch (err) {
      if (err?.name === "AbortError") return; // stopRun() already updated the UI
      const msg = err?.message || "Unexpected execution error.";
      setStatus("Failed");
      setRunEndedAt(Date.now());
      setResult({ status: "error", message: msg });
      pushLog("System", msg);
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
    history,
    clearHistory,
    reuseHistoryItem,
  };
}
