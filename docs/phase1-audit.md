# Phase 1 compliance audit

Scope: current branch reachable history plus tracked/unignored working files. Protected .agents/,
.codex/, .aws/ and unrelated home files are excluded. Scripts print paths/counts only. Local ignored
backend/.env is intentionally retained as the operator's private configuration; no values are printed.

## Rules

| Item | Status | Evidence |
|---|---|---|
| No Node/TypeScript backend, dependency manifests or server tooling outside frontend | PASS | git ls-files: only front end/package.json/lock and frontend Vite/Vitest configs. backend/app/browser/observe.js executes inside Chromium, not Node; testsite/site.js is static browser code. Optional external PinchTab executable is not a repo Node dependency. |
| No credential material in branch history or distributable files | PASS | `python scripts/audit_repo.py`: 365 reachable blobs and 161 working files scanned at audit time; zero credential findings, including exact local key matches and API/token/private-key patterns. Later documentation commits are re-scanned before completion. |
| Private configuration ignored and example complete | PASS | backend/.gitignore:1 and root .gitignore:2 protect .env/.env.*; no .env tracked. AST comparison: all 47 Settings fields have exactly one matching .env.example name, no extras. |
| Logging excludes page/input/frame/credential data | PASS | app/logging.py JSON formatter and transport filter; runner/state errors log constant event/type and runId, never raw exceptions. OpenRouter disables verbose SDK/HTTP logs. PinchTab uses sanitized errors and logs numeric release version only. Canary/privacy tests include all log levels and model bodies. |
| Structured application run logs have runId | PASS | app/core/state.py transition and app/agent/runner.py failures/cleanup; app/main.py request errors; PinchTab version warning passes runId derived from tracked run task (startup checks use unassigned). |
| Tokens stay out of URLs/logs; WebSocket origins checked | PASS | app/api/preview.py and app/api/ws.py compare exact FRONTEND_ORIGIN, authenticate first message with constant-time comparison and private per-run tokens. Frontend keeps tokens in session memory; URLs carry only run IDs. Auth/Origin/run-bound-token unit tests pass. |
| URL schemes and debug/control network exposure | PASS | app/browser/safety.py validate_url; only internal about:blank exception. Default Chrome has pipe control and no debugging TCP port. Optional PinchTab uses literal-loopback URL validation and debug-address=127.0.0.1; spike inspected actual listeners. No Compose or public PinchTab proxy was introduced. |
| Interfaces injected into orchestration | PASS | app/interfaces/{browser,validator,skills,llm}.py and core/{store,emitter}.py Protocols; agent/runner.py receives all dependencies explicitly. Concrete store/emitter/driver/channel composition stays in runtime/factories/main, not agent step logic. |
| Bounded/pinned dependencies; clean installed resolution | PASS | backend/pyproject.toml runtime/dev ranges and Playwright==1.64.0; setuptools build range now >=75,<100. pip check: no broken requirements. All declared dependencies serve current runtime/dev paths; no Node backend/LangChain/agent framework. |
| Page-content trust boundary and private input | PASS | app/agent/prompts.py uses static system rules and random user-message delimiters; runner/driver redaction and input_privacy.py guard. No raw chain-of-thought timeline fields. PinchTab raw values/text never replace visibility/redaction reconciliation. |
| Default path remains independent of PinchTab/Docker | PASS | AGENT_DRIVER defaults playwright, existing BROWSER_DRIVER fake/playwright selection unchanged. Optional imports/health only execute behind pinchtab flag. Default driver source, REST routes and event contract have zero diff from Task 6. Docker omitted deliberately as optional. |

## Small fixes made during audit

- Root .gitignore:2 adds repository-wide credential/cache exclusions; backend already protected its
  local .env, but root credentials and scripts/__pycache__ were not covered.
- .ruff.toml:1 makes root checks inherit the existing backend policy and exclude generated envs;
  no rule or test was weakened.
- backend/pyproject.toml:2 bounds the isolated setuptools build dependency; runtime packages already
  had upper bounds/pins. It need not be installed in the runtime venv (PEP 517 build isolation).
- app/browser/pinchtab_api.py version warning now admits only numeric release versions; unexpected
  server-supplied strings are rendered unknown, preventing payloads from entering warnings.
- AGENTS.md's obsolete “PinchTab planned/no flag” statement is updated to the implemented opt-in.
- Final local-run/acceptance docs replace the missing top-level README in the documentation commit.

## Quality and stress evidence

- Initial parallel offline/live/spike jobs oversubscribed Chromium: the headed first-frame <3 s
  assertion failed once. The assertion and source timeout were retained; final gates run without
  competing browser jobs. Final results are recorded in the acceptance/documentation pass.
- Live gate: **5 passed**, 296 deselected, 239.98 s, DeepSeek V4 Flash selected by the existing
  private configuration. No API key printed or committed. Human billing verification remains open.
- Optional adapter gate: **6 passed**, 310 deselected, 20.86 s: all five fake-model smoke goals plus
  password canary, stale ref, paused action and outage. Uses a disposable authenticated 0.15.2 server.
- Leak/stress script: **PASS** after 10 mixed finished/failed/stopped/takeover-timeout runs and 3
  concurrent real Chromium runs. No owned Chromium/PinchTab processes remained. RSS 51.34 →
  73.09 MiB (+21.75 MiB); last five serial samples 58.65–60.21 MiB. See script output/acceptance.
  Native preview colors, event run IDs/sequences and same-origin cookies stayed isolated.
- pip check: **PASS**, no broken requirements. Ruff, mypy, default/headed pytest, frontend and
  editor diagnostic final results are recorded below after the final gate pass.

## Known gaps / needs human decision

- Three-way concurrency is proven by the automated sample, not unlimited capacity. The verification
  audit added MAX_CONCURRENT_RUNS=3 and an atomic JSON 429 admission limit; deploy one API worker.
  Multi-worker/shared-store scheduling is future work.
- In-memory run history/metadata is retained for the process lifetime; bounded frame queues expire
  and browsers close, but this ten-run sample cannot prove asymptotic memory bounds. A durable
  store plus explicit metadata retention/admission policy needs product decisions in Phase 2.
- This is a local single-operator product. AllowAllValidator/EmptySkillProvider are intentional
  Phase 1 stubs. Domain/private-network policies, approvals and stronger injection defenses remain
  Phase 2; the audit does not claim production multi-tenant security or universal data-loss prevention.
- PinchTab adds a privileged optional server. Its activity/network-body recording must stay disabled
  in the supplied configuration. Its own process lifecycle/security upgrades remain operator-owned;
  never expose it to the frontend or bind it publicly.
- Human sharpness, tactile headed/headless typing/IME and actual account billing remain
  NEEDS HUMAN CHECK in phase1-acceptance.md. Automated equivalents do not constitute human sign-off.
- The verification audit fixed legacy timeline payload mappings. The old UI parameter fields now
  explicitly show "Server configured"; set MAX_STEPS/MAX_SECONDS in backend configuration.

Current rerun evidence supersedes historical results above: see [phase1-verification.md](phase1-verification.md).
