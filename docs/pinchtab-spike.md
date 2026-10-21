# PinchTab attach spike: PASS — OPTIONAL

Recommendation: **OPTIONAL**, never required. PinchTab 0.15.2 can attach to Chromium launched
and owned through Playwright's pipe. It controls the same isolated context's tabs while the
existing CDP screencast and input sessions keep working. Small snapshot savings on two pages did
not outweigh mixed latency/size results or the extra local privileged server. Playwright remains
the default; an optional adapter must be explicitly selected.

## Version and evidence sources

Installed `pinchtab --version`: **pinchtab 0.15.2**; Playwright **1.64.0**, Chromium build **1248**.
PinchTab was already installed via the global npm wrapper at `~/.local/bin/pinchtab`; its installed
README explains that it downloads/checksums the versioned native binary. No Node backend or
PinchTab package dependency was added to this repository.

Read installed README, `pinchtab --help`, `server --help`, `bridge --help`, `snap --help`,
`instance --help`, and bundled `pinchtab config schema --print`. Cross-checked exact release docs:

- [v0.15.2 README](https://github.com/pinchtab/pinchtab/blob/v0.15.2/README.md)
- [Configuration](https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/config.md)
- [Instances/attach](https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/instances.md)
- [Tabs/routes](https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/tabs.md)
- [Snapshot](https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/snapshot.md)
- [Fill](https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/fill.md),
  [Click](https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/click.md)
- [Security](https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/guides/security.md)

The tagged checkout resolved to commit `96d1508b44721674e3bff2f3bbd21401ec270a63` during inspection.
The HTTP paths used are `/health`, `/instances`, `/instances/attach`,
`/instances/{id}/tabs`, `/tabs/{id}/snapshot`, `/tabs/{id}/action`, `/instances/{id}/stop`.
No endpoint spelling was inferred from older examples.

## Reproduction and security

With backend dependencies installed and its environment active, from the repo root:

```bash
python scripts/spike_pinchtab_attach.py
```

The script starts/stops its own static test site, loopback PinchTab orchestrator and Chromium.
It uses PINCHTAB_URL/PINCHTAB_TOKEN for an explicitly provided existing loopback server, or
otherwise generates a RAM-only token and disposable PINCHTAB_CONFIG/state directory. PINCHTAB_BIN
can select the optional executable. It validates the installed/reported version before proceeding.
Its wall-clock bound is 180 seconds; it stops at a hard failed check and always attempts cleanup.
It prints only statuses, numeric measurements and error key names; no tokens/page text/input/frames.

Managed server invocation: `pinchtab server --bind 127.0.0.1 --port <ephemeral> --log-level error`.
Config uses explicit allocation (no automatic browser), loopback bind, activity recording disabled,
network-body retention disabled, no extensions, and default local-only domain/IDPI restrictions.
**Only `security.attach.enabled=true` is enabled temporarily**, with allowHosts=[127.0.0.1],
allowSchemes=[http,ws], forwardProxyAuth=false. Evaluate, macro, PinchTab screencast, downloads,
uploads, cookies, clipboard and file scheme remain disabled. The disposable config is removed and
owned server/bridge shut down after the experiment; the operator's config is untouched.

A spike-only driver subclass adds `--remote-debugging-address=127.0.0.1` and an allocated numeric
`--remote-debugging-port`; the normal driver's launch/defaults are untouched. Listener inspection
rejects wildcard/non-loopback binds. `/json/version` discovers the debugger without logging it.
Early instrumentation attempts used optional Browser.getBrowserCommandLine on page/browser
sessions and hit a CDP Error; this was not an attach failure. The final script uses the known port
and documented HTTP discovery. Form/caret assertions were corrected against actual fake-site
behavior before recording the final results. No Chrome-control workaround/default flags were removed.

## Ordered checks

| # | Result | Evidence |
|---|---|---|
| 1 | PASS | `/instances` without auth 401; Bearer auth 200; server health version 0.15.2; loopback listener. |
| 2 | PASS | Pipe-controlled launch returned; loopback `/json/version` 200; attach returned 201 and attached=true. No pipe/port conflict observed. |
| 3 | PASS | Same unique target/URL maps to PinchTab tab; JSON snapshot 200; Name, Email, Project and Submit form have refs. |
| 4 | PASS | Two fill actions and click by ref returned 200; Playwright confirmed field change and actual form confirmation. |
| 5 | PASS | Existing CDP channel delivered/acked frames; independent CDP mouse/text altered the expected field; sequence continued increasing. No observed focus/duplicate-input/stall interference. |
| 6 | PASS | Popup was seen and mapped to a different PinchTab ID and active Playwright Page. |
| 7 | PASS | Fresh form snapshot, navigation without re-snapshot, then old ref: HTTP 500, JSON keys `[code,error,retryable]`. The stale action failed without acting. Raw error text is not retained. |
| 8 | PASS | Attached instance stopped, browser/server children closed, owned PID/start-time identities absent after cleanup. |

## Rough measurements

Single local samples, interactive compact format for PinchTab; actual `Observation.to_prompt_text()`
for Playwright. Estimated tokens=ceil(characters/4), not model tokenizer measurements. Navigation
latency is excluded; JSON envelopes/format differences affect comparisons. No snapshot text saved.

| Page | PinchTab chars | Est tokens | Snapshot ms | Playwright chars | Est tokens | Observe ms |
|---|---:|---:|---:|---:|---:|---:|
| index.html | 279 | 70 | 609.41 | 407 | 102 | 34.22 |
| form.html | 415 | 104 | 17.59 | 531 | 133 | 22.73 |
| table.html | 735 | 184 | 105.61 | 450 | 113 | 15.94 |

PinchTab action ms: fill 11.58, fill 11.55, click 18.13. These numbers are diagnostic samples,
not a performance claim; cold caches and accessibility/tree content differ. In particular, the
interactive table output costs more than the current capped Playwright prompt.

## Risks and decision

PinchTab has another privileged bearer-token HTTP control plane, experimental attach and evolving
payloads. A stale ref returns 500 rather than a dedicated HTTP conflict. Accessibility nodes alone
cannot establish the full hidden/secret-field policy: the optional adapter must reconcile against
Playwright's visibility/redaction observation before exposing values/refs. Input privacy, budgets,
pause handling and browser ownership must stay with the existing runner/driver. Fail explicitly on
PinchTab outage instead of silently switching observation/action sources. Keep endpoint/payload
assumptions in one version-pinned module and test mismatched versions.

All final checks passed, so Part B is permitted. The findings justify an **optional experiment**,
not changing the default browser path or making PinchTab/Docker an installation requirement.
