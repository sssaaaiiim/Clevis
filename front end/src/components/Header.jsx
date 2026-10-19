import React from "react";
import { Globe2, History } from "lucide-react";
import StatusPill from "./StatusPill";
import ConstellationLogo from "./ConstellationLogo";

export default function Header({
  status,
  url,
  historyCount,
  commandOpen,
  onToggleCommand,
  onOpenHistory,
  developerMode,
  onToggleDeveloperMode,
  onOpenIntent,
  onOpenMonitor,
}) {
  return (
    <header className="relative z-30 border-b border-[#5B9BE6]/20 bg-[#F4F8FE]/85 backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-420 items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            aria-label={commandOpen ? "Close CLEVIS command" : "Open CLEVIS command"}
            aria-expanded={commandOpen}
            onClick={onToggleCommand}
            className="group flex min-w-0 items-center gap-3 rounded-lg text-left focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#2F7BD6]"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[#5B9BE6]/35 bg-[#14305E] transition-colors group-hover:border-[#5B9BE6]/70">
              <ConstellationLogo size={28} />
            </span>
            <span className="flex min-w-0 items-center gap-2.5">
              <span className="truncate font-sans text-[18px] font-bold tracking-[0.14em] text-[#12305E]">CLEVIS</span>
              <span className="rounded-full border border-[#5B9BE6]/20 bg-[#5B9BE6]/[0.08] px-2 py-1 font-sans text-[9px] font-semibold tracking-[0.12em] text-[#3F5B88]/80">
                AGENT CONTROL
              </span>
            </span>
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-pressed={developerMode}
            onClick={onToggleDeveloperMode}
            className={`inline-flex h-9 shrink-0 self-center items-center gap-2.5 rounded-full border py-1.5 pl-3 pr-4 font-sans text-[11px] font-medium leading-none transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2F7BD6] ${
              developerMode
                ? "border-[#0F766E]/50 bg-[#0F766E]/10 text-[#115E59]"
                : "border-[#5B9BE6]/30 bg-white/35 text-[#2C4F82] hover:bg-white/70"
            }`}
          >
            <span>Developer mode</span>
            <span
              aria-hidden="true"
              className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
                developerMode ? "bg-[#0F766E]" : "bg-[#9CAEC5]"
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-[left] duration-200 ${
                  developerMode ? "left-4" : "left-0.5"
                }`}
              />
            </span>
          </button>
        </div>
      </div>
      {developerMode && (
        <div className="border-t border-[#5B9BE6]/15 bg-white/35">
          <div className="mx-auto flex w-full max-w-420 flex-wrap items-center justify-between gap-2 px-4 py-2 sm:px-6">
            <div className="flex min-w-0 flex-1 items-center gap-1.5 rounded-md border border-[#5B9BE6]/20 bg-white/50 px-2.5 py-1.5 font-mono text-[10px] text-[#3F5B88] sm:max-w-xl">
              <Globe2 size={12} className="shrink-0" />
              <span className="truncate">{url || "auto-select start page"}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={onOpenIntent}
                className="rounded-md border border-[#5B9BE6]/25 bg-white/55 px-2.5 py-1.5 font-sans text-[10px] font-medium text-[#2C4F82] transition-colors hover:bg-white"
              >
                Intent
              </button>
              <button
                onClick={onOpenMonitor}
                className="rounded-md border border-[#5B9BE6]/25 bg-white/55 px-2.5 py-1.5 font-sans text-[10px] font-medium text-[#2C4F82] transition-colors hover:bg-white"
              >
                Agent Monitor
              </button>
              <button
                onClick={onOpenHistory}
                className="inline-flex items-center gap-1.5 rounded-md border border-[#5B9BE6]/25 bg-white/55 px-2.5 py-1.5 font-sans text-[10px] font-medium text-[#2C4F82] transition-colors hover:bg-white"
                aria-label={`Open run history, ${historyCount} stored runs`}
              >
                <History size={12} />
                History <span className="font-mono text-[10px]">{historyCount}</span>
              </button>
              <StatusPill status={status} />
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
