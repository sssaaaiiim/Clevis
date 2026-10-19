import React from "react";
import { Activity, Clock3, Coins, Goal, Layers3, X } from "lucide-react";

function fmt(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function Stat({ icon: Icon, label, value, accent = "#5B9BE6" }) {
  const mono = label === "Tokens Used" || label === "Execution Duration";
  return (
    <div className="rounded-lg border border-[#5B9BE6]/25 bg-white/45 p-3">
      <p className="font-sans text-[10px] font-semibold uppercase tracking-wide text-[#667994]">
        <Icon size={11} className="mr-1 inline-block" style={{ color: accent }} />
        {label}
      </p>
      <p className={`mt-1 text-[13px] text-[#12305E] ${mono ? "font-mono" : "font-sans"}`}>{value}</p>
    </div>
  );
}

export default function IntentPanel({
  task,
  status,
  plan,
  activeIndex,
  logs,
  elapsedSeconds,
  tokens,
  onToggleCollapsed,
}) {
  const stepText = plan.length ? `${Math.min(activeIndex + 1, plan.length)}/${plan.length}` : "–";

  return (
    <section className="h-full min-w-0 overflow-y-auto rounded-xl border border-[#5B9BE6]/30 bg-[#F4F8FE]/95 p-4 shadow-2xl backdrop-blur-xl">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="font-sans text-[12px] font-semibold uppercase tracking-[0.12em] text-[#2C4F82]">Intent</h2>
          <p className="mt-1 font-sans text-[10px] text-[#667994]">{status}</p>
        </div>
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label="Close intent panel"
          className="rounded-md p-2 text-[#3F5B88] transition-colors hover:bg-white focus-visible:outline-2 focus-visible:outline-[#2F7BD6]"
        >
          <X size={16} />
        </button>
      </div>

      <div className="space-y-3">
        <div className="rounded-lg border border-[#5B9BE6]/25 bg-white/65 p-4">
          <p className="font-sans text-[10px] font-semibold uppercase tracking-wide text-[#667994]">Current Objective</p>
          <p className="mt-2 line-clamp-6 font-sans text-[13px] leading-relaxed text-[#12305E]">
            {task?.trim() || "No objective loaded yet. Use a quick template or write a goal from the command bar."}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-2">
          <Stat icon={Goal} label="Step" value={stepText} accent="#2F7BD6" />
          <Stat icon={Coins} label="Tokens Used" value={tokens ? tokens.toLocaleString() : "–"} accent="#5B9BE6" />
          <Stat icon={Clock3} label="Execution Duration" value={fmt(elapsedSeconds)} accent="#2F7BD6" />
          <Stat icon={Layers3} label="Plan Items" value={String(plan.length)} accent="#5B9BE6" />
          <Stat icon={Activity} label="Live Activity Rate" value={`${logs.length} events`} accent="#2F7BD6" />
        </div>
      </div>
    </section>
  );
}
