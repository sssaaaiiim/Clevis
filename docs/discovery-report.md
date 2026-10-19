# Repository discovery report — Task 1

Discovery baseline: `a71aba2` on 2026-10-19. This replaces the stale Phase 1 report: the checked-out backend is TypeScript, not Python. No `AGENTS.md` exists in the repository (including nested folders) or its ancestor directories; no additional repository instructions were available. No frontend UI, styling, source, manifest, configuration, or lockfile is changed by this task.

## 1. Frontend

- Folder: `front end/`; React 19, JavaScript/JSX, Vite 6, Tailwind CSS 4, npm with `package-lock.json`. Node v22.22.1 and npm 9.2.0 used for verification.
- Install: `cd "front end" && npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache`.
- Development: `cd "front end" && npm run dev` (port 5173); build: `npm run build` (output `dist/`); serve build: `npm run preview`.
- Entry: `index.html` → `src/main.jsx` → `src/WebTaskOrchestrator.jsx`. Components, hooks, theme, fonts and UI utilities live entirely inside the frontend.
- `src/constants/theme.js:1` sets `BACKEND_URL = ""`. Requests are same-origin; `vite.config.js:17–24` proxies `/api` to `http://localhost:8000`. Production requires an equivalent API routing arrangement. Keep the proxy for the future Python service; its Node-backend comment is stale but harmless.
- Build/start results are recorded under Verification below. API execution is intentionally unavailable after removal.

## 2. Current frontend data sources

All application network calls are in `front end/src/hooks/useTaskOrchestrator.js`. No Axios, XMLHttpRequest, WebSocket, EventSource, screenshot polling or frontend mock service exists. SSE is consumed using streamed `fetch`, not EventSource.

| File and line | URL / operation | Request and expected response |
|---|---|---|
| `front end/src/hooks/useTaskOrchestrator.js:204` | `POST /api/runs` | JSON `{goal, mode: "headless" or "headed", startUrl?, maxSteps, maxSeconds}`; expects success JSON `{runId}` (currently HTTP 202); errors use `{error}`. |
| `front end/src/hooks/useTaskOrchestrator.js:236–238` | `GET /api/runs/{encoded runId}/events` | Accept `text/event-stream`, AbortSignal; expects a readable SSE response whose `data:` lines contain JSON events with `type` and `data`. |
| `front end/src/hooks/useTaskOrchestrator.js:159` | `POST /api/runs/{encoded runId}/stop` | Stop button; no body; response is not parsed or checked for HTTP success. Old server returns `{runId,status}`. |
| `front end/src/hooks/useTaskOrchestrator.js:230` | Same stop endpoint | Race recovery when operator stops before creation responds; same response expectations. |
| `front end/src/components/ViewportCanvas.jsx:53–56` | `<img src={screenshotUrl}>` | Decodes a `data:image/jpeg;base64,…` frame from SSE; no separate screenshot HTTP call. |
| `front end/index.html:7–13`, `front end/src/index.css:1` | Google Fonts CSS and font assets | External font downloads only, unrelated to backend APIs. Geist assets are also bundled locally. |

SSE parser/consumer: hook lines 244–340. It uses the first `data:` line of each blank-line-delimited block, ignores SSE `id:` and `event:` fields, and has no reconnect/replay logic. Fields consumed:

| Event | Expected `data` and UI effect |
|---|---|
| `run.started` | No data consumed; status becomes Planning. |
| `plan.created` | `steps: [{id,label}]`; plan and Running state. |
| `step.proposed` | `goal, step, action, why`; agent log and active step matched by label. |
| `step.executed` | `result`; browser log. |
| `observation.summary` | `summary`; browser log. |
| `preview.frame` | `dataUrl`; replaces preview image and clears screenshot error. |
| `budget.update` | `tokens`; token counter. |
| `run.finished` | `result`; completion, local history. |
| `run.failed` | `reason`; failure, local history. |
| `run.stopped` | `reason`; stopped status. |

Other data is local: `wto_history` localStorage reads at hook line 13, writes at 131, clears at 142 (up to 50 records); attachments are browser File objects held in state at 104–110 and never uploaded; templates in `src/constants/theme.js:35–52` populate fields only (their target URLs are not fetched by the frontend). Form state and one-second elapsed timer are local. No auth, payment, database, remote history or takeover/input calls exist.

## 3. Live preview and likely blurriness

Despite its name, `ViewportCanvas` renders an **img**, with no canvas or iframe. `WebTaskOrchestrator.jsx:46–56` passes screenshot state into it; `ViewportCanvas.jsx:49–64` renders the active view. Its image fills the container with `absolute inset-0 h-full w-full object-contain`. The responsive grid at line 82 determines the display area.

Before removal, `backend/src/pinchtab/pinchtab-driver.ts:109–124` fetched `/tabs/{id}/screenshot?format=jpeg&quality=65&scale=0.7&raw=true` and waited 700 ms between captures (at most about 1.4 fps plus request latency). `backend/src/orchestrator.ts:195–204` base64-encoded those frames into SSE `preview.frame` events. Hook lines 287–290 set the image URL.

Likely blur: explicitly reduced source resolution (`scale=0.7`), lossy JPEG quality 65, then CSS resampling to the container size (possible enlargement and fractional scaling). No native frame dimensions are transmitted, no capture viewport dimensions are explicitly configured in the driver, and no devicePixelRatio-aware capture/display handling exists. Actual frame dimensions and device scale were not measured against a running browser backend. There is no canvas backing-buffer mismatch to fix here. Low capture rate causes stale/choppy updates, separately from spatial blur. Nothing is fixed in this task.

## 4–5. Backend inventory and decisions

REMOVE below refers to the old implementation, including when its product function must be rewritten in Python later. REWRITE rows describe retained documentation or functionality, not permission to leave TypeScript server files behind. The frontend imports no backend source files; its only dependency is the HTTP/SSE contract.

| Path | What it does | Used by frontend? | Decision (KEEP / REMOVE / REWRITE) | Reason in one line |
|---|---|---|---|---|
| backend/src/server.ts | Express HTTP/SSE server, CORS, static fixtures | Indirectly, HTTP | REMOVE | Replace all server implementation with Python in later tasks. |
| backend/src/contracts.ts | Zod request/action/event schemas | Indirectly, response shapes | REMOVE | Recreate required contracts with Python schemas. |
| backend/src/orchestrator.ts | Bounded Planner/Actor loop and SSE preview producer | Indirectly | REMOVE | Rebuild orchestration in Python. |
| backend/src/model.ts | OpenRouter model client, parsing and token accounting | Indirectly | REMOVE | Rebuild model integration in Python. |
| backend/src/browser-driver.ts | Browser/validator/skill interfaces and permissive placeholders | Indirectly | REMOVE | Old TypeScript interfaces are unnecessary. |
| backend/src/pinchtab/paths.ts | PinchTab endpoint constants | Indirectly | REMOVE | Browser integration will be implemented later. |
| backend/src/pinchtab/pinchtab-driver.ts | PinchTab profiles, tabs, actions, JPEG capture and cleanup | Indirectly | REMOVE | Replace browser adapter and frame transport later. |
| backend/src/budget.ts | Step/time/token/cost limits and repeated-action detection | Indirectly | REMOVE | Reimplement applicable limits in Python. |
| backend/src/run-state.ts | Run state transitions | Indirectly | REMOVE | Replace TypeScript state logic. |
| backend/src/run-store.ts | In-memory runs/events; trims old frames | Indirectly | REMOVE | Replace TypeScript storage. |
| backend/src/config.ts | dotenv/Zod environment validation | No direct import | REMOVE | Remove old configuration consumer. |
| backend/src/logger.ts | Pino logging with redaction | No | REMOVE | Replace Node logging. |
| backend/src/ and backend/src/pinchtab/ | Folders containing the files above | Indirectly | REMOVE | No Node/TypeScript backend source remains. |
| backend/test/core.test.ts and backend/test/ | Vitest unit/integration tests using fake browser/model | No | REMOVE | Tests depend exclusively on retired TypeScript implementation. |
| backend/public/test-page.html | Local sample product/form/table/scroll page | No application call; manual smoke only | REMOVE | Fixture belongs only to retired backend smoke flow. |
| backend/public/test-page-two.html and backend/public/ | Second navigation fixture and fixture folder | No application call; manual smoke only | REMOVE | Remove retired backend fixtures. |
| backend/package.json | Node dependencies and dev/build/start/test/lint/format scripts | No | REMOVE | Remove entire backend Node toolchain. |
| backend/package-lock.json | Backend npm dependency lock | No | REMOVE | Not the frontend lockfile; only locks retired backend packages. |
| backend/eslint.config.js | Backend TypeScript lint configuration | No | REMOVE | No backend JavaScript/TypeScript remains. |
| backend/tsconfig.json | Backend compiler configuration | No | REMOVE | No TypeScript backend remains. |
| backend/Dockerfile | Node 22 build/runtime image | No | REMOVE | Old backend-only deployment configuration. |
| backend/pinchtab.config.json | PinchTab bind/allowed-domain configuration | No | REMOVE | Only mounted by retired Compose service. |
| docker-compose.yml | Node backend and PinchTab services/network/data-volume declaration | No frontend service | REMOVE | Entire stack serves retired backend; no Docker volumes are deleted. |
| backend/dist/ (ignored) | Compiled Node server including nested PinchTab code | No | REMOVE | Remove generated server output as well as source. |
| backend/node_modules/ (ignored) | Installed backend Node packages | No | REMOVE | Remove dead installed backend dependencies. |
| backend/README.md | Old Node setup/API documentation | No | REWRITE | Replace with exactly the requested Python/FastAPI placeholder. |
| backend/.env.example | Legacy environment template, placeholder credentials | No | KEEP | Environment examples are explicitly protected; inactive after config removal. |
| backend/.gitignore | Ignores local secrets, generated output and caches | No | KEEP | Continue protecting local credentials and virtualenv artifacts. |
| backend/.env (ignored, local only) | Local legacy settings including credentials | No after removal | KEEP | Preserve local secrets without reading out values or committing them. |
| backend/venv/ (ignored, local only) | Pre-existing Python 3.14 virtualenv and installed packages | No | KEEP | Ownership/reuse uncertain; not tracked backend source; see human decisions. |
| docs/smoke-tasks.md | Manual smoke instructions tied to removed server fixtures/Compose | No | REMOVE | Instructions depend entirely on retired backend. |
| docs/discovery-report.md | Current discovery and removal record | No | KEEP | Required task deliverable; supersedes stale report. |
| front end/ (all tracked files) | React UI, components, utilities, CSS, HTML, package manifests/lock, Vite config and ignores | Yes | KEEP | Preserve frontend source and tooling byte-for-byte. |
| front end/node_modules/ and front end/dist/ (ignored) | Frontend dependencies/build output | Yes | KEEP | Install and regenerate only for required verification. |
| .git/ | Repository history and metadata | No | KEEP | Protected repository metadata; only normal requested commits. |
| .agents/, .codex/, .aws/ | Environment-provided protected directories | No known application use | KEEP | Outside task scope; do not inspect secrets or modify. |
| Run creation, event stream, stop, status, browser/model orchestration, limits and logging (functionality) | Product backend capabilities represented by removed source above | HTTP/SSE subset today | REWRITE | Implement in Python 3.11+/FastAPI in later tasks; no new backend code here. |

Backend runtime dependencies removed: `dotenv ^16.4.7`, `express ^5.1.0`, `pino ^9.7.0`, `zod ^3.25.76`. Backend dev dependencies removed: `@eslint/js ^9.30.1`, `@types/express ^5.0.3`, `@types/node ^22.15.30`, `eslint ^9.30.1`, `prettier ^3.6.2`, `tsx ^4.20.3`, `typescript ^5.8.3`, `typescript-eslint ^8.35.1`, `vitest ^3.2.4`, and their locked transitive dependencies. Identically named frontend tooling/transitive packages stay in the frontend lockfile.

Removed backend scripts: `dev` (tsx watch), `build` (tsc), `start` (node), `test` (vitest), `lint` (eslint), `format` (prettier). Compose's backend and PinchTab services, `browser-control` network and `pinchtab-data` volume declaration are removed; no running container or persistent Docker volume is destroyed.

Legacy environment variables lose their consumers with `config.ts` and Compose: `PORT`, `FRONTEND_ORIGIN`, `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_MODEL`, `OPENROUTER_FALLBACK_MODEL`, `PINCHTAB_URL`, `PINCHTAB_TOKEN`, `ALLOW_SCREENCAST`, `ALLOW_HEADED`, `MAX_STEPS`, `MAX_SECONDS`, `MAX_LLM_TOKENS`, `MAX_LLM_COST_USD`, `LOG_LEVEL`, Docker `NODE_ENV` and `PINCHTAB_CONFIG`. The protected example and local environment remain; they are legacy references, not configuration for a new backend. Node-only ignore patterns can be removed while preserving secret/cache protections.

No tracked Python application, requirements/pyproject, database models/migrations, auth, payment implementation, separate mock server, CI workflows, root README, license file or AGENTS.md exists at this baseline. Python files under the local virtualenv are installed third-party packages, not application source. No frontend dependency or script serves only the old backend.

## 6. Frontend calls to rewire in Task 8

Every existing application API call becomes unavailable after backend removal, even where the URL already matches the future contract. Preserve all call sites in this task.

| Current call site | Later endpoint | Required later work |
|---|---|---|
| Hook line 204, create run | `POST /api/runs` | Same URL; reconcile request names, returned run identifier and error schema with Python contract. |
| Hook lines 236–238, events | `GET /api/runs/{id}/events` (SSE) | Same URL; align event payloads and lifecycle handling; current hook expects the event shapes documented above. |
| Hook lines 159 and 230, stop (both call sites) | `POST /api/runs/{id}/stop` | Same URL; retain stop/race behavior and handle response/failure consistently. |
| Hook lines 287–290 and ViewportCanvas lines 53–56, SSE image handling | `WS /api/runs/{id}/preview` | Move frame reception from SSE to preview WebSocket; feed the existing image view using the future frame format. |
| No current status fetch | `GET /api/runs/{id}` | Add status/recovery integration when specified later. |
| No current takeover call | `POST /api/runs/{id}/takeover` | Add operator takeover lifecycle later. |
| No current resume call | `POST /api/runs/{id}/resume` | Add agent resume lifecycle later. |
| No current input transport | `WS /api/runs/{id}/input` | Add operator browser input forwarding later. |

The frontend currently has no live input forwarding or takeover/resume interaction. The Vite proxy has no explicit WebSocket proxy option; evaluate `ws: true` when WebSocket integration is implemented. Legacy `/api/run` and `/api/screenshot` claims in the previous report do not describe current code.

## Needs human decision

- `backend/venv/`: pre-existing, ignored Python 3.14 environment; retained because ownership/reuse is uncertain. Future backend requires Python 3.11+; choose whether to reuse or recreate it then. No dependency from this environment is introduced into project manifests.
- `backend/.env` and `backend/.env.example`: retained local settings/protected example contain legacy variable names. Decide the Python backend configuration in later tasks; do not assume old credentials/settings should be reused.

## Security findings

- `backend/.env` contains non-placeholder credential assignments. Values were not printed or committed. It stays ignored. No new credential file is created.
- `backend/.env.example` contains placeholder credentials only. Preserve it under the explicit safety rule.
- Security scope was the current working tree, not a complete history audit. Preview images may contain browser content, so the future transport needs the product's session access controls.

## Verification

Baseline, before removal:

| Exact command | Working directory | Result |
|---|---|---|
| `npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache` | `front end/` | Restricted attempt interrupted after stream-fd errors/stall; network-enabled retry reported 355 packages, but Vite was missing afterward. |
| `npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache --include=dev` | `front end/` | Clean retry succeeded, 355 packages installed in 3 seconds; frontend manifests/lockfile unchanged. |
| `npm run build` | `front end/` | Initial attempt before clean retry failed (`vite: not found`); after retry succeeded with Vite 6.4.3, 1,812 modules, 2.23 seconds. |
| `npm run dev -- --host 127.0.0.1 --strictPort` | `front end/` | Initial missing Vite resolved by reinstall; subsequent attempt found port 5173 already occupied; existing service left alone. |
| `npm run dev -- --host 127.0.0.1 --port 5174 --strictPort` | `front end/` | Vite ready in 278 ms at `http://127.0.0.1:5174/`. |
| `/opt/google/chrome/chrome --headless --no-sandbox --disable-gpu --user-data-dir=/tmp/wto-chrome-baseline --timeout=15000 --dump-dom http://127.0.0.1:5174/ > /tmp/wto-baseline-dom.html 2> /tmp/wto-baseline-chrome.log` | Repository root | Exit 0; DOM contains `Your browser, on task.` and `CLEVIS COMMAND`; no `React Error` or `vite-error-overlay`. |

Dependencies, build, dev server and Chrome verification used the network/process-enabled execution environment where needed. No package versions were edited. Browser outputs remain in `/tmp`, outside version control.

Post-removal verification: pending until the separate removal step; results will be appended in that commit.

## PR description

Remove the retired TypeScript/Express backend, OpenRouter/PinchTab implementation, Node dependencies and tooling, generated backend output, Docker/Compose stack and backend-only smoke fixtures/instructions. Preserve the React/Vite frontend and its lockfile, protected environment example, local environment/virtualenv, and secret ignore rules. Replace the backend README with the Python/FastAPI placeholder.

Later tasks will rebuild run orchestration, browser/model integration, state, budgets and API handling in Python 3.11+/FastAPI. Task 8 must reconnect run creation, SSE events and both stop call sites to the Python implementation, move preview frames from SSE to `WS /api/runs/{id}/preview`, and add status, takeover, resume and input integration. Existing run/events/stop URLs already match the endpoint contract; payload compatibility still needs verification.
