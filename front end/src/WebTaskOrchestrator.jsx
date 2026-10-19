import React, { useState } from "react";
import { MessageSquareText } from "lucide-react";
import Header from "./components/Header";
import IntentPanel from "./components/IntentPanel";
import ViewportCanvas from "./components/ViewportCanvas";
import TelemetryLedger from "./components/TelemetryLedger";
import AssistantConsole from "./components/AssistantConsole";
import HistoryDrawer from "./components/HistoryDrawer";
import useTaskOrchestrator from "./hooks/useTaskOrchestrator";
import { PALETTE } from "./constants/theme";

export default function WebTaskOrchestrator() {
  const o = useTaskOrchestrator();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [intentOpen, setIntentOpen] = useState(false);
  const [monitorOpen, setMonitorOpen] = useState(false);
  const [developerMode, setDeveloperMode] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);

  const shownUrl = o.targetUrl || o.url;

  const closeDeveloperPanels = () => {
    setIntentOpen(false);
    setMonitorOpen(false);
  };

  return (
    <div className="flex h-[100dvh] min-h-[520px] flex-col overflow-hidden" style={{ background: PALETTE.bg }}>
      <Header
        status={o.status}
        url={shownUrl}
        historyCount={o.history.length}
        commandOpen={commandOpen}
        onToggleCommand={() => setCommandOpen((open) => !open)}
        onOpenHistory={() => setHistoryOpen(true)}
        developerMode={developerMode}
        onToggleDeveloperMode={() => {
          setDeveloperMode((enabled) => !enabled);
          closeDeveloperPanels();
        }}
        onOpenIntent={() => setIntentOpen((open) => !open)}
        onOpenMonitor={() => setMonitorOpen((open) => !open)}
      />

      <main className="relative flex min-h-0 flex-1">
        <ViewportCanvas
          status={o.status}
          url={shownUrl}
          onTemplatePick={o.applyTemplate}
          screenshotUrl={o.screenshotUrl}
          screenshotError={o.screenshotError}
          task={o.task}
          plan={o.plan}
          activeIndex={o.activeIndex}
          logs={o.logs}
          result={o.result}
        />

        {developerMode && (intentOpen || monitorOpen) && (
          <button
            type="button"
            aria-label="Close developer panels"
            onClick={closeDeveloperPanels}
            className="fixed inset-0 z-30 cursor-default bg-[#10213A]/10 backdrop-blur-[1px]"
          />
        )}

        {developerMode && intentOpen && (
          <div className="absolute inset-y-3 left-3 z-40 w-[min(300px,calc(100vw-1.5rem))] animate-in slide-in-from-left-2 duration-200">
            <IntentPanel
              task={o.task}
              status={o.status}
              plan={o.plan}
              activeIndex={o.activeIndex}
              logs={o.logs}
              elapsedSeconds={o.elapsedSeconds}
              tokens={o.tokens}
              onToggleCollapsed={() => setIntentOpen(false)}
            />
          </div>
        )}

        {developerMode && monitorOpen && (
          <div className="absolute inset-y-3 right-3 z-40 w-[min(340px,calc(100vw-1.5rem))] animate-in slide-in-from-right-2 duration-200">
            <TelemetryLedger
              logs={o.logs}
              plan={o.plan}
              activeIndex={o.activeIndex}
              result={o.result}
              onToggleCollapsed={() => setMonitorOpen(false)}
            />
          </div>
        )}

        <AssistantConsole
          visible={commandOpen}
          onClose={() => setCommandOpen(false)}
          open={o.paramOpen}
          setOpen={o.setParamOpen}
          url={o.url}
          setUrl={o.setUrl}
          timeoutVal={o.timeoutVal}
          setTimeoutVal={o.setTimeoutVal}
          maxSteps={o.maxSteps}
          setMaxSteps={o.setMaxSteps}
          headless={o.headless}
          setHeadless={o.setHeadless}
          task={o.task}
          setTask={o.setTask}
          onRun={o.runTask}
          onStop={o.stopRun}
          isRunning={o.isRunning}
          attachments={o.attachments}
          onAddFiles={o.addFiles}
          onRemoveFile={o.removeFile}
        />
        <button
          type="button"
          aria-expanded={commandOpen}
          aria-controls="clevis-command-panel"
          onClick={() => setCommandOpen((open) => !open)}
          className={`fixed bottom-6 left-5 z-[60] inline-flex items-center gap-2.5 rounded-2xl border px-4 py-3 font-sans text-[12px] font-semibold tracking-wide shadow-[0_12px_36px_rgba(13,28,58,0.28)] backdrop-blur-xl transition-all duration-200 hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5B9BE6] active:translate-y-0 sm:left-7 ${
            commandOpen
              ? "border-[#7187AA] bg-[#243B5E]/95 text-white"
              : "border-white/20 bg-[#172B4D]/95 text-white hover:border-[#8FB9EB]/50 hover:bg-[#203960]"
          }`}
        >
          <MessageSquareText size={16} className={commandOpen ? "text-[#C6DDF7]" : "text-[#9DC5F3]"} />
          <span>CLEVIS COMMAND</span>
          <span aria-hidden="true" className={`ml-1 size-2 rounded-full ${commandOpen ? "bg-[#70D8B2]" : "bg-[#8FA2BD]"}`} />
        </button>
      </main>

      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        history={o.history}
        onReuse={o.reuseHistoryItem}
        onClear={o.clearHistory}
      />
    </div>
  );
}
