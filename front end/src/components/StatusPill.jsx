import React from "react";
import { Circle, CheckCircle2, CircleDashed, Loader2 } from "lucide-react";
import { STATUS_STYLES } from "../constants/theme";

const ICONS = {
  Idle: Circle,
  Planning: Loader2,
  Running: Loader2,
  Validating: Loader2,
  Completed: CheckCircle2,
  Failed: CircleDashed,
};

export default function StatusPill({ status }) {
  const safe = STATUS_STYLES[status] ? status : "Idle";
  const Icon = ICONS[safe] ?? Circle;
  const spin = ["Planning", "Running", "Validating"].includes(safe);

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 font-sans text-[11px] font-semibold tracking-wide ${STATUS_STYLES[safe].cls}`}
    >
      <Icon size={12} className={spin ? "animate-spin" : ""} />
      {safe}
    </span>
  );
}
