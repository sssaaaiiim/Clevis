import React, { useEffect, useRef } from "react";
import { ChevronDown, Globe2, Loader2, Paperclip, Play, Square } from "lucide-react";
import AttachmentTray from "./AttachmentTray";
import {
  PromptInput,
  PromptInputActions,
  PromptInputTextarea,
} from "@/components/ui/prompt-input";

const LABEL = "mb-1 block font-sans text-[10px] font-semibold uppercase tracking-wide text-[#667994]";
const FIELD =
  "w-full rounded-md border border-[#5B9BE6]/30 bg-white/60 px-2.5 py-2 font-sans text-[12px] text-[#12305E] outline-none transition-colors focus:border-[#2F7BD6]";

export default function AssistantConsole({
  visible,
  open,
  setOpen,
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
  onRun,
  onStop,
  isRunning,
  attachments,
  onAddFiles,
  onRemoveFile,
}) {
  const taRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!taRef.current) return;
    taRef.current.style.height = "auto";
    taRef.current.style.height = `${Math.min(160, taRef.current.scrollHeight)}px`;
  }, [task]);

  const canRun = task.trim().length > 0 && !isRunning;

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && canRun) {
      e.preventDefault();
      onRun();
    }
  };

  return (
    <div
      aria-hidden={!visible}
      inert={!visible}
      id="clevis-command-panel"
      className={`fixed bottom-20 left-1/2 z-50 w-[calc(100%-1.5rem)] max-w-3xl -translate-x-1/2 transition-[opacity,visibility] duration-200 sm:bottom-8 ${
        visible ? "visible opacity-100" : "invisible pointer-events-none opacity-0"
      }`}
    >
      <div
        className={`rounded-2xl border border-white/60 bg-[#F4F8FE]/90 shadow-[0_20px_60px_rgba(13,28,58,0.32)] backdrop-blur-2xl transition-transform duration-200 ease-out ${
          visible ? "translate-y-0 scale-100" : "translate-y-4 scale-[0.98]"
        }`}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[#5B9BE6]/20 px-4 py-2">
          <div className="min-w-0">
            <p className="truncate font-sans text-[11px] font-semibold tracking-wide text-[#2C4F82]">CLEVIS COMMAND</p>
            <p className="truncate font-sans text-[10px] text-[#667994]">Describe a workflow and Clevis will take it from here.</p>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={() => setOpen((v) => !v)}
              className="inline-flex items-center gap-1.5 rounded-md border border-[#5B9BE6]/30 bg-white/45 px-2.5 py-1 font-sans text-[11px] font-medium text-[#2C4F82] transition-all duration-300 hover:border-[#5B9BE6] active:scale-95"
            >
              Parameters
              <ChevronDown size={13} className={`transition-transform duration-300 ${open ? "rotate-180" : ""}`} />
            </button>
          </div>
        </div>

        <div className={`grid transition-all duration-300 ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
          <div className="overflow-hidden">
            <div className="grid grid-cols-1 gap-3 border-b border-[#5B9BE6]/25 p-3.5 md:grid-cols-4">
              <div className="md:col-span-2">
                <label className={LABEL}>
                  Starting URL <span className="normal-case text-[#506C99]">(optional)</span>
                </label>
                <div className="flex items-center gap-2 rounded-md border border-[#5B9BE6]/30 bg-white/60 px-2.5 py-2 focus-within:border-[#2F7BD6]">
                  <Globe2 size={13} className="shrink-0 text-[#3F5B88]" />
                  <input
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="Blank = agent picks a start page"
                    className="w-full bg-transparent font-mono text-[12px] text-[#12305E] outline-none placeholder:text-[#5F7AA3]"
                  />
                </div>
              </div>

              <div>
                <label className={LABEL}>Timeout</label>
                <select value={timeoutVal} onChange={(e) => setTimeoutVal(e.target.value)} className={FIELD}>
                  <option value="15">15s</option>
                  <option value="30">30s</option>
                  <option value="60">60s</option>
                  <option value="120">120s</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-2 md:grid-cols-1">
                <div>
                  <label className={LABEL}>Max steps</label>
                  <input
                    value={maxSteps}
                    onChange={(e) => setMaxSteps(e.target.value.replace(/[^0-9]/g, ""))}
                    className={FIELD}
                  />
                </div>
                <button
                  onClick={() => setHeadless((v) => !v)}
                  className="mt-auto flex items-center justify-between rounded-md border border-[#5B9BE6]/30 bg-white/60 px-2.5 py-2 font-sans text-[12px] font-medium text-[#2C4F82] transition-all duration-300 hover:border-[#5B9BE6] active:scale-95"
                >
                  Headless
                  <span
                    className={`ml-2 rounded px-1.5 py-0.5 font-sans text-[10px] font-semibold ${
                      headless ? "bg-[#2B5BA8] text-[#F4F8FE]" : "bg-[#F3DED8] text-[#7C332B]"
                    }`}
                  >
                    {headless ? "ON" : "OFF"}
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <AttachmentTray attachments={attachments} onRemove={onRemoveFile} />

        <div className="p-3.5">
          <PromptInput
            value={task}
            onValueChange={setTask}
            disabled={isRunning}
            maxHeight={160}
            className="rounded-2xl border-[#AFC1DD]/60 bg-white/85 p-3 shadow-[inset_0_1px_2px_rgba(28,48,82,0.04)] transition-all duration-200 focus-within:border-[#4F46E5]/60 focus-within:bg-white focus-within:ring-4 focus-within:ring-[#4F46E5]/10"
          >
            <PromptInputTextarea
              ref={taRef}
              rows={2}
              submitOnEnter={false}
              onKeyDown={handleKeyDown}
              placeholder="Let Clevis handle the workflow."
              className="max-h-40 min-h-14 overflow-auto px-1 py-1 font-sans text-[14px] leading-6 text-[#12305E] placeholder:text-[#71819A]"
            />
            <PromptInputActions className="mt-2 flex-wrap justify-between border-t border-[#DCE5F2] pt-2">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="inline-flex size-9 items-center justify-center rounded-xl border border-[#D7E1EF] bg-white text-[#466184] transition-colors hover:border-[#9BB1D1] hover:bg-[#F4F7FC] active:scale-95"
                  aria-label="Attach files"
                >
                  <Paperclip size={15} />
                </button>
                <span className="font-sans text-[10px] text-[#8190A6]">
                  {typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform)
                    ? "⌘ + Enter to run"
                    : "Ctrl + Enter to run"}
                </span>
              </div>

              {isRunning ? (
                <button
                  type="button"
                  onClick={onStop}
                  className="inline-flex h-9 items-center gap-2 rounded-xl border border-[#7C332B]/30 bg-[#F9EAE7] px-4 font-sans text-[12px] font-semibold text-[#7C332B] transition-colors hover:bg-[#F3DED8] active:scale-95"
                >
                  <Square size={13} className="fill-current" />
                  Stop
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onRun}
                  disabled={!canRun}
                  className={`inline-flex h-9 items-center gap-2 rounded-xl border px-4 font-sans text-[12px] font-semibold transition-all duration-200 active:scale-95 ${
                    canRun
                      ? "border-[#4338CA] bg-[#4F46E5] text-white shadow-[0_4px_14px_rgba(79,70,229,0.24)] hover:border-[#3730A3] hover:bg-[#4338CA]"
                      : "cursor-not-allowed border-[#C9D0E8] bg-[#E6E8F2] text-[#75809A]"
                  }`}
                >
                  <Play size={14} />
                  Run Task
                </button>
              )}
            </PromptInputActions>
          </PromptInput>

          {isRunning && (
            <p className="mt-2 flex items-center gap-1.5 font-mono text-[10px] text-[#2C4F82]">
              <Loader2 size={11} className="animate-spin" /> Agent is working. Press Stop to release the browser.
            </p>
          )}
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          onAddFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
