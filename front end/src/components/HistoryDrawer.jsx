import React, { useEffect } from "react";
import { Clock3, RotateCcw, Trash2, X } from "lucide-react";

export default function HistoryDrawer({ open, onClose, history, onReuse, onClear }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <div className={`fixed inset-0 z-50 ${open ? "pointer-events-auto" : "pointer-events-none"}`} aria-hidden={!open}>
      <div
        onClick={onClose}
        className={`absolute inset-0 bg-[#14305E]/25 backdrop-blur-[2px] transition-opacity duration-300 ${open ? "opacity-100" : "opacity-0"}`}
      />

      <aside
        className={`absolute right-0 top-0 flex h-full w-full max-w-md flex-col border-l border-[#5B9BE6]/40 bg-[#F4F8FE]/90 backdrop-blur-xl transition-transform duration-300 ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-[#5B9BE6]/30 px-4 py-3">
          <div>
            <h2 className="font-mono text-[12px] uppercase tracking-[0.16em] text-[#2C4F82]">Run History</h2>
            <p className="font-mono text-[10px] text-[#3F5B88]">{history.length} stored locally</p>
          </div>
          <div className="flex items-center gap-1.5">
            {history.length > 0 && (
              <button
                onClick={onClear}
                className="inline-flex items-center gap-1 rounded border border-[#7C332B]/30 px-2 py-1 font-mono text-[10px] text-[#7C332B] transition-all hover:bg-[#F3DED8] active:scale-95"
              >
                <Trash2 size={11} /> Clear
              </button>
            )}
            <button
              onClick={onClose}
              className="rounded border border-[#5B9BE6]/30 p-1 text-[#2C4F82] transition-all hover:bg-white/60 active:scale-95"
              aria-label="Close history"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto p-3">
          {history.length === 0 && (
            <p className="mt-10 text-center font-mono text-[11px] text-[#3F5B88]">No runs yet. Completed runs appear here.</p>
          )}

          {history.map((run) => {
            const ok = run.status === "Completed";
            return (
              <div
                key={run.id}
                className={`rounded-md border-l-2 bg-white/50 p-2.5 ${ok ? "border-l-[#2F7BD6]" : "border-l-[#7C332B]"}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="line-clamp-2 font-mono text-[12px] text-[#12305E]">{run.task}</p>
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] ${
                      ok ? "bg-[#2F7BD6]/12 text-[#1B3F7A]" : "bg-[#7C332B]/10 text-[#7C332B]"
                    }`}
                  >
                    {run.status}
                  </span>
                </div>
                <p className="mt-1 truncate font-mono text-[10px] text-[#3F5B88]">{run.url}</p>
                <p className="mt-1 line-clamp-3 font-mono text-[11px] text-[#2C4F82]">{run.detail}</p>
                <div className="mt-2 flex items-center justify-between">
                  <span className="inline-flex items-center gap-1 font-mono text-[10px] text-[#3F5B88]">
                    <Clock3 size={10} /> {run.when} · {run.steps} steps
                  </span>
                  <button
                    onClick={() => {
                      onReuse(run);
                      onClose();
                    }}
                    className="inline-flex items-center gap-1 rounded border border-[#5B9BE6]/40 px-1.5 py-0.5 font-mono text-[10px] text-[#2C4F82] transition-all hover:bg-white/70 active:scale-95"
                  >
                    <RotateCcw size={10} /> Reuse
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </aside>
    </div>
  );
}
