import React from "react";
import { X } from "lucide-react";

function levelFromMessage(msg = "") {
  const m = msg.toLowerCase();
  if (m.includes("fail") || m.includes("error") || m.includes("unexpected")) return "error";
  if (m.includes("success") || m.includes("completed") || m.includes("done")) return "success";
  return "info";
}

export default function TelemetryLedger({ logs, plan, activeIndex, result, onToggleCollapsed }) {
  return (
    <aside className="flex h-full min-w-0 flex-col overflow-hidden rounded-xl border border-[#5B9BE6]/30 bg-[#F4F8FE]/95 p-4 shadow-2xl backdrop-blur-xl">
      <div className="mb-4 flex shrink-0 items-center justify-between">
        <div>
          <h3 className="font-sans text-[12px] font-semibold uppercase tracking-[0.12em] text-[#2C4F82]">Agent Monitor</h3>
          <p className="mt-1 font-mono text-[10px] text-[#667994]">{logs.length} events</p>
        </div>
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label="Close agent monitor panel"
          className="rounded-md p-2 text-[#3F5B88] transition-colors hover:bg-white focus-visible:outline-2 focus-visible:outline-[#2F7BD6]"
        >
          <X size={16} />
        </button>
      </div>

      <div className="mb-3 shrink-0 rounded-lg border border-[#5B9BE6]/25 bg-white/65 p-4">
        <p className="font-sans text-[10px] font-semibold uppercase tracking-wide text-[#667994]">Plan Items</p>
        <ol className="mt-3 space-y-2">
          {plan.length === 0 && <li className="font-sans text-[11px] text-[#667994]">Plan will appear when the agent starts.</li>}
          {plan.map((step, index) => {
            const current = index === activeIndex;
            const done = index < activeIndex;
            return (
              <li key={step.id} className="flex items-start gap-2">
                <span className={`mt-1.25 h-1.5 w-1.5 shrink-0 rounded-full ${done ? "bg-[#2F7BD6]" : current ? "bg-[#5B9BE6]" : "bg-[#AFC3E0]"}`} />
                <span className={`font-sans text-[11px] ${current ? "font-semibold text-[#1F4F8F]" : done ? "text-[#2A5A9A]" : "text-[#506C99]"}`}>
                  {step.label}
                </span>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-[#5B9BE6]/25 bg-[#1E4A8A]/90 p-3">
        {logs.length === 0 && <p className="font-sans text-[11px] text-[#CADCF5]">No telemetry yet.</p>}
        <div className="space-y-1.5">
          {logs.map((log, index) => {
            const level = levelFromMessage(log.m);
            const lineAccent =
              level === "error" ? "border-l-[#E0786B]" : level === "success" ? "border-l-[#5FB0F5]" : "border-l-[#5B9BE6]/60";
            const dotColor = level === "error" ? "bg-[#E0786B]" : level === "success" ? "bg-[#5FB0F5]" : "bg-[#9CC7F5]";

            return (
              <div
                key={`${log.time}-${index}`}
                className={`rounded-sm border-l-2 ${lineAccent} bg-black/10 px-2 py-1 font-mono text-[11px] text-[#F2F7FE]`}
              >
                <div className="flex items-start gap-2">
                  <span className={`mt-1.25 h-1.5 w-1.5 shrink-0 rounded-full ${dotColor}`} />
                  <span className="shrink-0 text-[#BCD3F2]">{log.time}</span>
                  <span className="shrink-0 text-[#A9CFF7]">[{log.t}]</span>
                  <span className="min-w-0 flex-1 wrap-break-word text-[#F2F7FE]">{log.m}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {result && (
        <div
          className={`mt-3 shrink-0 rounded-lg border p-4 ${
            result.status === "success"
              ? "border-[#2F7BD6]/45 bg-[#E1EEFC] text-[#1B4A8A]"
              : "border-[#7C332B]/45 bg-[#F3DED8] text-[#7C332B]"
          }`}
        >
          <p className="font-sans text-[12px] font-semibold">{result.status === "success" ? "Execution completed" : "Execution failed"}</p>
          <p className="mt-1 font-sans text-[12px]">{result.message}</p>
        </div>
      )}
    </aside>
  );
}
