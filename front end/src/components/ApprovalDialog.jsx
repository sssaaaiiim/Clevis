import React, { useEffect, useRef, useState } from "react";

const BADGES = {
  low: "bg-green-100 text-green-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-red-100 text-red-800",
};

export default function ApprovalDialog({ request, onDecision, onDismiss, onStop }) {
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const container = useRef(null);
  const inFlight = useRef(false);

  useEffect(() => {
    const previous = document.activeElement;
    const dialog = container.current;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    container.current?.querySelector("button")?.focus();
    return () => {
      dialog.close?.();
      if (previous?.isConnected) previous.focus?.();
    };
  }, []);

  useEffect(() => {
    if (!expired) return;
    const timer = setTimeout(() => onDismiss(request.approval_id), 1500);
    return () => clearTimeout(timer);
  }, [expired, onDismiss, request.approval_id]);

  const decide = async (decision) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const response = await onDecision(decision, decision === "deny" ? reason : "");
      setReason("");
      if (response.expired) {
        setExpired(true);
        setError("This approval request has expired");
      } else if (!response.ok) {
        inFlight.current = false;
        setBusy(false);
        setError(response.message || "Could not submit the decision. Please try again.");
      }
      // Success remains disabled until run.resumed removes this request.
    } catch {
      inFlight.current = false;
      setBusy(false);
      setError("Could not submit the decision. Please try again.");
    }
  };

  const trapFocus = (event) => {
    if (event.key !== "Tab") return;
    const controls = [...container.current.querySelectorAll("button:not(:disabled), textarea:not(:disabled)")];
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
  };

  return (
    <dialog ref={container} aria-labelledby="approval-title" aria-modal="true" onKeyDown={trapFocus}
      onCancel={event => event.preventDefault()}
      className="fixed inset-0 m-0 h-dvh max-h-none w-screen max-w-none border-0 bg-transparent p-0 backdrop:bg-[#10213A]/45 backdrop:backdrop-blur-sm">
      <div className="grid min-h-full place-items-center p-4">
      <section
        className="w-full max-w-lg rounded-2xl border border-[#C6DDF7] bg-white p-6 text-[#172B4D] shadow-xl">
        <h2 id="approval-title" className="text-lg font-semibold">Approval required</h2>
        <p className="mt-3 break-words">The agent wants to: {request.action_summary}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
          <span className={`rounded-full px-3 py-1 font-medium ${BADGES[request.risk] || BADGES.medium}`}>{request.risk} risk</span>
          <span className="break-all">{request.page_domain}</span>
        </div>
        <label className="mt-5 block text-sm" htmlFor="approval-denial-reason">Reason for denial (optional)</label>
        <textarea id="approval-denial-reason" maxLength={200} value={reason} disabled={busy}
          onChange={event => setReason(event.target.value)} className="mt-2 w-full rounded-lg border border-[#C6DDF7] p-2" />
        {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
        {busy && !expired && <p role="status" className="mt-3 text-sm">Waiting for agent…</p>}
        <div className="mt-5 flex flex-wrap gap-3">
          <button type="button" disabled={busy} onClick={() => decide("approve")} className="rounded-lg bg-[#243B5E] px-4 py-2 text-white disabled:opacity-50">Approve</button>
          <button type="button" disabled={busy} onClick={() => decide("deny")} className="rounded-lg border border-[#7187AA] px-4 py-2 disabled:opacity-50">Deny</button>
          <button type="button" onClick={onStop} className="ml-auto rounded-lg border border-red-300 px-4 py-2 text-red-700">Stop run</button>
        </div>
      </section>
      </div>
    </dialog>
  );
}
