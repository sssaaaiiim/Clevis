import React from "react";
import { Sparkles } from "lucide-react";
import { QUICK_TEMPLATES } from "../constants/theme";
import TaskActivityPanel from "./TaskActivityPanel";

const GRID_IDLE =
  "linear-gradient(to right, rgba(91,155,230,0.12) 1px, transparent 1px), linear-gradient(to bottom, rgba(91,155,230,0.12) 1px, transparent 1px)";

function IdleCanvas({ onTemplatePick }) {
  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl border border-[#5B9BE6]/35 bg-linear-to-br from-[#2B5BA8]/85 to-[#14305E]/95">
      <div
        className="pointer-events-none absolute inset-0 opacity-30"
        style={{ backgroundImage: GRID_IDLE, backgroundSize: "14px 14px" }}
      />
      <div className="pointer-events-none absolute inset-0 bg-radial-[circle_at_30%_20%] from-[#5B9BE6]/22 to-transparent" />

      <div className="relative flex h-full flex-col justify-center gap-8 px-5 pb-44 pt-12 sm:px-8 sm:pb-48 sm:pt-16">
        <div className="mx-auto w-full max-w-6xl">
          <div className="inline-flex items-center gap-2 rounded-md border border-[#5B9BE6]/40 bg-white/10 px-2 py-1 font-sans text-[11px] font-semibold text-[#EAF2FD] backdrop-blur-sm">
            <Sparkles size={13} className="text-[#A9CFF7]" />
            SYSTEM READY · STANDBY MODE
          </div>

          <h3 className="mt-3 font-sans text-[22px] font-semibold tracking-tight text-[#F4F8FE] sm:text-[26px]">Your browser, on task.</h3>
          <p className="mt-2 max-w-2xl font-sans text-[12px] text-[#DCE9FA]">
            Start a workflow with Clevis, or choose a quick-start task.
          </p>
        </div>

        <div className="mx-auto grid w-full max-w-6xl grid-cols-1 gap-3 md:grid-cols-3">
          {QUICK_TEMPLATES.map((tpl) => (
            <button
              key={tpl.title}
              onClick={() => onTemplatePick(tpl)}
              className="group rounded-xl border border-white/5 bg-slate-900/40 p-4 text-left shadow-[0_10px_28px_rgba(8,20,42,0.12)] backdrop-blur-md transition-all duration-300 hover:-translate-y-1 hover:border-[#9CC7F5]/45 hover:bg-slate-900/55 hover:shadow-[0_16px_36px_rgba(8,20,42,0.24)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9CC7F5] active:translate-y-0"
            >
              <p className="font-sans text-[12px] font-semibold text-[#F4F8FE]">{tpl.title}</p>
              <p className="mt-1 line-clamp-2 font-sans text-[11px] text-[#D3E3F8]">{tpl.task}</p>
              <p className="mt-3 truncate font-mono text-[10px] text-[#7CCFC3] transition-colors group-hover:text-[#A2E8DD]">{tpl.url}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ActiveCanvas({ url, screenshotUrl, screenshotError }) {
  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl border border-[#5B9BE6]/35 bg-white">
      {screenshotUrl ? (
        <img
          src={screenshotUrl}
          alt={`Live browser page at ${url || "the current URL"}`}
          className="absolute inset-0 h-full w-full object-contain"
        />
      ) : (
        <div className="flex h-full items-center justify-center bg-[#14305E] p-6 text-center font-mono text-sm text-[#D3E3F8]">
          {screenshotError || "Waiting for the browser preview…"}
        </div>
      )}
    </div>
  );
}

export default function ViewportCanvas({
  url,
  onTemplatePick,
  screenshotUrl,
  screenshotError,
  status,
  task,
  plan,
  activeIndex,
  logs,
  result,
}) {
  const active = ["Planning", "Running", "Validating"].includes(status) || Boolean(screenshotUrl);

  return (
    <section className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(180px,0.8fr)_minmax(240px,1.2fr)] gap-3 p-3 md:grid-cols-[minmax(270px,30vw)_minmax(0,1fr)] md:grid-rows-1">
      <TaskActivityPanel
        task={task}
        status={status}
        plan={plan}
        activeIndex={activeIndex}
        logs={logs}
        result={result}
      />
      <div className="relative min-h-0 min-w-0">
        {active ? (
          <ActiveCanvas
            url={url}
            screenshotUrl={screenshotUrl}
            screenshotError={screenshotError}
          />
        ) : (
          <IdleCanvas onTemplatePick={onTemplatePick} />
        )}
      </div>
    </section>
  );
}
