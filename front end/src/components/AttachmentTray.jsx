import React from "react";
import { File, FileImage, X } from "lucide-react";
import { humanSize } from "../hooks/useTaskOrchestrator";

function AttachmentChip({ item, onRemove }) {
  const icon = item.type?.startsWith("image/") ? <FileImage size={13} /> : <File size={13} />;
  return (
    <div className="inline-flex items-center gap-2 rounded-md border border-[#5B9BE6]/30 bg-white/50 px-2 py-1 font-mono text-[11px] text-[#2C4F82] transition-all duration-300">
      {icon}
      <span className="max-w-35 truncate">{item.name}</span>
      <span className="text-[#506C99]">{humanSize(item.size)}</span>
      <button
        onClick={() => onRemove(item.id)}
        className="rounded p-0.5 text-[#7C332B] hover:bg-[#F3DED8] active:scale-95"
        aria-label={`Remove ${item.name}`}
      >
        <X size={12} />
      </button>
    </div>
  );
}

export default function AttachmentTray({ attachments, onRemove }) {
  return (
    <div className="border-b border-[#5B9BE6]/25 px-4 py-2.5">
      <div className="flex flex-wrap items-center gap-2">
        {attachments.length === 0 && <p className="font-mono text-[11px] text-[#506C99]">No attachments added.</p>}
        {attachments.map((f) => (
          <AttachmentChip key={f.id} item={f} onRemove={onRemove} />
        ))}
      </div>
    </div>
  );
}
