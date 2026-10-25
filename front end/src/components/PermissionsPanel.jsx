import React from "react";

export const DEFAULT_PERMISSIONS = Object.freeze({ domains: "", blockSubmit: false, downloads: false, send: true, steps: "", cost: "" });

export function permissionOverrides(value = DEFAULT_PERMISSIONS) {
  const domains = value.domains.split(",").map(s => s.trim().toLowerCase()).filter(Boolean);
  if (domains.some(d => d !== "*" && (d.length > 253 || !d.split(".").every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))))) {
    throw new Error("Use hostnames only, without schemes, paths or ports.");
  }
  const result = {};
  if (domains.length) result.allowed_domains = domains;
  if (value.blockSubmit) result.allow_form_submit = false;
  if (value.downloads) result.allow_downloads = true;
  if (!value.send) result.allow_send_message = false;
  if (value.steps !== "") {
    if (!Number.isInteger(Number(value.steps)) || Number(value.steps) < 1) throw new Error("Max steps must be a positive integer.");
    result.max_steps = Number(value.steps);
  }
  if (value.cost !== "") {
    if (!Number.isFinite(Number(value.cost)) || Number(value.cost) < .01) throw new Error("Max cost must be at least $0.01.");
    result.max_cost_usd = Number(value.cost);
  }
  return Object.keys(result).length ? result : undefined;
}

export default function PermissionsPanel({ value = DEFAULT_PERMISSIONS, onChange, hidden }) {
  if (hidden) return null;
  const change = (key, next) => onChange?.({ ...value, [key]: next });
  let error = "";
  try { permissionOverrides(value); } catch (e) { error = e.message; }
  const field = "w-full rounded-md border border-[#AFC1DD] bg-white px-2 py-1";
  return <details className="mt-3 text-xs text-[#3F5B88]">
    <summary className="cursor-pointer">Advanced permissions</summary>
    <div className="mt-2 grid gap-2">
      <label>Allowed domains<input aria-label="Allowed domains" className={field} value={value.domains} onChange={e => change("domains", e.target.value)} placeholder="e.g. google.com, wikipedia.org; leave empty to allow all" /></label>
      <label><input type="checkbox" checked={value.blockSubmit} onChange={e => change("blockSubmit", e.target.checked)} /> Block form submissions</label>
      <label><input type="checkbox" checked={value.downloads} onChange={e => change("downloads", e.target.checked)} /> Allow downloads</label>
      <label><input type="checkbox" checked={value.send} onChange={e => change("send", e.target.checked)} /> Allow message sending</label>
      <label>Max steps<input type="number" min="1" className={field} value={value.steps} onChange={e => change("steps", e.target.value)} placeholder="Server default" /></label>
      <label>Max cost USD<input type="number" min="0.01" step="0.01" className={field} value={value.cost} onChange={e => change("cost", e.target.value)} placeholder="Server default" /></label>
      {error && <p role="alert">{error}</p>}
    </div>
  </details>;
}
