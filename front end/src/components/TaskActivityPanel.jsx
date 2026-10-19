import React, { useEffect, useRef } from "react";
import { Check, Circle, LoaderCircle, X } from "lucide-react";

function stepState(index, activeIndex, status) {
  if (status === "Completed" || index < activeIndex) return "complete";
  if (index === activeIndex && ["Planning", "Running", "Validating"].includes(status)) return "active";
  if (status === "Failed" && index === activeIndex) return "failed";
  return "pending";
}

function StepIcon({ state }) {
  if (state === "complete") return <Check size={13} />;
  if (state === "active") return <LoaderCircle size={13} className="animate-spin" />;
  if (state === "failed") return <X size={13} />;
  return <Circle size={11} />;
}

export default function TaskActivityPanel({
  task,
  status,
  plan,
  activeIndex,
  logs,
  result,
}) {
  const activityRef = useRef(null);

  useEffect(() => {
    activityRef.current?.scrollTo({ top: activityRef.current.scrollHeight, behavior: "smooth" });
  }, [logs]);

  const running = ["Planning", "Running", "Validating"].includes(status);

  return (
    <aside className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-[#5B9BE6]/30 bg-[#F4F8FE]/95 shadow-xl">
      <header className="shrink-0 border-b border-[#5B9BE6]/20 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-sans text-xs font-semibold uppercase tracking-[0.12em] text-[#2C4F82]">
            Task activity
          </h2>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-2 py-1 font-mono text-[10px] text-[#3F5B88]">
            <span className={`size-1.5 rounded-full ${running ? "animate-pulse bg-[#2F7BD6]" : status === "Failed" ? "bg-[#E0786B]" : "bg-[#7B8DA8]"}`} />
            {status}
          </span>
        </div>
        <p className="mt-3 line-clamp-3 font-sans text-xs leading-relaxed text-[#334F77]">
          {task || "Enter a task to see its progress here."}
        </p>
      </header>

      <section className="max-h-[38%] shrink-0 overflow-y-auto border-b border-[#5B9BE6]/20 px-4 py-4 md:max-h-none">
        <h3 className="font-sans text-[10px] font-semibold uppercase tracking-wide text-[#667994]">
          Execution steps
        </h3>
        {!plan.length ? (
          <p className="mt-3 font-sans text-[11px] leading-relaxed text-[#667994]">
            {running ? "Preparing the browser and planning the task…" : "The agent’s plan will appear when a task starts."}
          </p>
        ) : (
          <ol className="mt-3 space-y-3">
            {plan.map((step, index) => {
              const state = stepState(index, activeIndex, status);
              const color =
                state === "complete" ? "text-[#2873BD]" :
                state === "active" ? "text-[#1F4F8F]" :
                state === "failed" ? "text-[#A94D42]" :
                "text-[#71819A]";
              return (
                <li key={step.id} className={`flex items-start gap-2.5 ${color}`}>
                  <span className="mt-0.5 shrink-0"><StepIcon state={state} /></span>
                  <span className={`font-sans text-[11px] leading-relaxed ${state === "active" ? "font-semibold" : ""}`}>
                    {step.label}
                  </span>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section className="flex min-h-0 flex-1 flex-col px-4 py-4">
        <h3 className="mb-3 shrink-0 font-sans text-[10px] font-semibold uppercase tracking-wide text-[#667994]">
          Live updates
        </h3>
        <div ref={activityRef} className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {!logs.length ? (
            <p className="font-sans text-[11px] leading-relaxed text-[#667994]">
              Browser and agent updates will show here as the task runs.
            </p>
          ) : (
            logs.slice(-80).map((log, index) => (
              <article
                key={`${log.time}-${index}`}
                className="rounded-md border border-[#5B9BE6]/15 bg-white px-2.5 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-sans text-[10px] font-semibold text-[#2C4F82]">{log.t}</span>
                  <time className="font-mono text-[9px] text-[#8391A7]">{log.time}</time>
                </div>
                <p className="mt-1 break-words font-sans text-[11px] leading-relaxed text-[#405B80]">{log.m}</p>
              </article>
            ))
          )}
        </div>
        {result && (
          <div className={`mt-3 shrink-0 rounded-md border px-3 py-2 text-[11px] leading-relaxed ${
            result.status === "success"
              ? "border-[#2F7BD6]/30 bg-[#E1EEFC] text-[#1B4A8A]"
              : "border-[#E0786B]/35 bg-[#F9E9E5] text-[#7C332B]"
          }`}>
            <span className="font-semibold">{result.status === "success" ? "Result" : "Task failed"}: </span>
            {result.message}
          </div>
        )}
      </section>
    </aside>
  );
}
