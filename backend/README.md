# Clevis Python backend

An async FastAPI backend for Python 3.11+. Select a fake browser (default) or isolated Playwright Chromium. The LLM remains a scripted fake; no real model requests are made. The runner receives its browser, LLM, validator and skills through interfaces.

From `backend/`, create an environment and install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
cp .env.example .env  # Only for a new local setup; preserve any existing private settings.
uvicorn app.main:app --reload
```

The API defaults to port 8000, matching the unchanged frontend Vite proxy. Use one worker: all runs, events, subscriptions and tasks are in process memory. Restarting loses them. The existing local `venv/` is unrelated to this setup and is left untouched.

Open the repository root in your editor. `pyrightconfig.json` points Python analysis to
`backend/.venv` and adds `backend/` to the import search path so `app.*` imports resolve.
Select `backend/.venv/bin/python` if your editor asks for an interpreter. After installing
dependencies, restart the Python language server if old import errors remain.

Run checks from `backend/` with the environment active:

```bash
pytest -q
ruff check .
mypy .
```

## Configuration

Settings are loaded from the process environment and `backend/.env` when running from this folder. Environment values override the file. No API keys are required or consumed. Unknown legacy settings in an existing `.env` are ignored; known budget/origin values still override defaults.

| Variable | Default | Behavior |
|---|---|---|
| `FRONTEND_ORIGIN` | `http://localhost:5173` | The single allowed CORS origin. |
| `BROWSER_HEADLESS` | `true` | Default preference; the required per-run `mode` always takes precedence. |
| `MAX_STEPS` | `30` | Hard action limit, including the final `done` action. |
| `MAX_SECONDS` | `300` | Hard active-time limit; includes planning and normal cleanup, excludes operator pauses. |
| `MAX_TOKENS` | `200000` | Reported limit and counter only; token enforcement is deferred. |
| `USE_FAKES` | `true` | Must be true in this task; false prevents startup. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `BROWSER_DRIVER` | `fake` | `fake` or `playwright`; selected during app setup, still injected into the runner. |
| `VIEWPORT_WIDTH` | `1280` | Context viewport width in CSS pixels. |
| `VIEWPORT_HEIGHT` | `720` | Context viewport height in CSS pixels. |
| `DEVICE_SCALE_FACTOR` | `1` | Context device pixel ratio. |
| `NAV_TIMEOUT_MS` | `20000` | Navigation timeout, then at most two seconds of bounded network-idle settling. |
| `ACTION_TIMEOUT_MS` | `8000` | Bounded action/locator timeout; explicit wait actions may run up to ten seconds. |
| `MAX_OBSERVED_ELEMENTS` | `150` | Maximum interactive elements per observation. |
| `MAX_OBSERVED_TEXT_CHARS` | `3000` | Maximum excerpt and extraction size. |
| `SLOW_MO_MS` | `0` | Optional delay between Playwright operations, useful for local headed demos. |

Application logs are JSON. Run-related records include `runId`. Goals, model messages, token values, settings dumps and exception text are never logged. Unexpected runner exceptions become a safe error containing only their exception class; budget and loop failures have explicit messages.

## API

| Route | Behavior |
|---|---|
| `GET /health` | `{ "status": "ok" }`. |
| `POST /api/runs` | `{ "goal": "…", "mode": "headless" or "headed" }` → HTTP 201 `{ "runId": "…" }`; starts a tracked async task. |
| `GET /api/runs/{id}` | `{runId,status,goal,mode,result,error,createdAt}`; nullable result/error. |
| `GET /api/runs/{id}/events` | Replay plus live SSE; closes after the terminal event. |
| `POST /api/runs/{id}/stop` | Stop, cancel pending I/O, close resources; repeated stop returns 200, other terminal states return 409. |
| `POST /api/runs/{id}/takeover` | Running → paused, reason `takeover`; invalid state returns 409. |
| `POST /api/runs/{id}/resume` | Paused → running; invalid state returns 409. |
| `WS /api/runs/{id}/preview` | Stub: accepts, verifies the run, then closes 1000; unknown run closes 4404. |
| `WS /api/runs/{id}/input` | Same stub behavior; no meaningful input or frames yet. |

Goals are trimmed, must contain 1–2000 characters, and mode is required. Extra request fields are rejected. Unknown runs return 404. JSON errors consistently use `{ "error": { "code": "…", "message": "…" } }`, including validation errors (422), HTTP errors, CORS preflight rejection and transition conflicts (409).

Create a run, then stream its events (replace the returned identifier):

```bash
curl -sS -X POST http://localhost:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"goal":"Read the scripted sample result","mode":"headless"}'

curl -N http://localhost:8000/api/runs/RUN_ID/events
curl -N -H 'Last-Event-ID: 5' http://localhost:8000/api/runs/RUN_ID/events
curl -N 'http://localhost:8000/api/runs/RUN_ID/events?after=5'
curl -X POST http://localhost:8000/api/runs/RUN_ID/takeover
curl -X POST http://localhost:8000/api/runs/RUN_ID/resume
curl -X POST http://localhost:8000/api/runs/RUN_ID/stop
```

The default fake completes quickly, so control calls must arrive before completion. Tests inject slower drivers to exercise pauses, cancellation and deadlines deterministically. A three-action fake script navigates, extracts a canned result and finishes.

SSE messages carry `id: <seq>`, `event: <type>`, and `data: <JSON event>`. Sequences start at 1 per run and have no gaps. Replay is strictly after the cursor; `?after=` takes precedence over `Last-Event-ID`. An already-completed run replays the remaining events then closes. A cursor at or beyond its terminal event returns an empty stream. Active connections receive a keep-alive comment every 15 seconds. Subscription registration and replay are serialized with publication to avoid replay/live gaps; disconnects remove subscriber queues.

## Events and lifecycle

All events are a Pydantic v2 discriminated union keyed by `type`, serialized as `{runId,seq,ts,type,data}`. Timestamps are ISO 8601 UTC. The application emits:

| Type | Data |
|---|---|
| `run.started` | `{goal,mode}` |
| `plan.created` | `{steps:[{id,text}]}` |
| `step.proposed` | `{stepId,planStepId,action,target,value,rationale}` |
| `step.executed` | `{stepId,ok,resultSummary}` |
| `observation.summary` | `{stepId,summary}` |
| `budget.update` | `{stepsUsed,maxSteps,secondsUsed,maxSeconds,tokensUsed,maxTokens}` |
| `run.paused`, `run.resumed` | `{reason}` |
| `run.finished` | `{result}` |
| `run.failed` | `{error}` |
| `run.stopped` | `{}` |

`step.validated` (`{stepId,verdict,reason}`) and `approval.required` (`{stepId,action,risk}`) are defined and validated, but never emitted in this task. There is no `preview.frame` SSE event.

An action has `action` (`click`, `type`, `navigate`, `scroll`, `extract`, `wait`, `done`), `target:{ref,description}` with nullable fields, nullable `value`, a one-sentence `rationale` up to 300 characters, and nullable `plan_step_id`. The event uses `planStepId`. Extra fields, including raw model chain-of-thought fields, are rejected. Observations and action results on the timeline are limited to short summaries.

The explicit transition table is in `app/core/state.py`: created → planning → running ⇄ paused. Failures and stop are allowed from every non-terminal state; finished is allowed from running or paused. Terminal states accept no transitions. Entering planning emits `run.started`; planning → running emits `plan.created`; paused → running emits `run.resumed`. The runner finishes only while running.

Each successful action emits proposed → executed → observation summary → budget update. Pauses prevent further runner events and budget consumption; pending fake I/O may finish, but its result is deferred until resume. No real browser suspension is implemented. Stop interrupts pending operations and resource cleanup is bounded. Repeating the same action on the same target three consecutive times fails: target reference is primary, description is fallback, and navigation uses its URL when neither exists.

## Code layout and scope

- `app/core/`: event models, explicit state transitions, async store, replay/fan-out emitter, budget counters.
- `app/interfaces/`: browser/preview, validator, skills and generic typed LLM contracts.
- `app/fakes/`: canned browser operations with failure injection and scripted plan/actions with fake usage.
- `app/agent/runner.py`: injected orchestration, cancellation, pause, budgets and loop detection.
- `app/api/`: REST/SSE routes and preview/input WebSocket placeholders.
- `app/runtime.py`: per-run state machines, dependency construction, task registry and shutdown cleanup.

Lifespan shutdown transitions active runs to stopped, cancels tasks and awaits cleanup. No database, authentication, real policy, real LLM or preview streaming implementation is included. History and subscriber queues are unbounded in this initial in-memory implementation.

The unchanged frontend still expects legacy request and event shapes; see [Task 2 PR description](../docs/task-2-pr-description.md) for the exact mismatches and assumptions.


## Playwright browser layer — Task 3

Pinned and tested: **Playwright Python 1.64.0**, bundled **Chromium 156.0.8078.4**, build **1248**. The [API verification record](../docs/playwright-api-verification.md) lists the installed async APIs and their signatures. These were checked against the installed package's generated documentation and official Playwright documentation. The driver never uses `page.accessibility`.

Both modes use the full bundled Chromium (`channel="chromium"`), with `headless` chosen by the explicit run mode. `playwright install chromium` installs everything; `playwright install --no-shell chromium` is sufficient for this driver because it does not use the separate legacy headless shell. Browser binaries are local development dependencies, not repository files.

Each driver is single-use and owns a fresh non-persistent context. It starts with no cookies, no downloads accepted, and an empty permission override that denies geolocation, notifications, camera and microphone. Locale/timezone use browser defaults. `close()` is idempotent and closes pages, context, browser and the Playwright transport. Cleanup also runs when startup or an action is cancelled. Always close standalone drivers in a `finally` block. The runner closes them after success, failure and stop.

### Local test site and scripted HTTP demo

From the repository root, with the environment active:

```bash
python scripts/serve_testsite.py
# Optional: TESTSITE_PORT=9876 python scripts/serve_testsite.py
# Or: python scripts/serve_testsite.py --port 9876
```

This serves only `testsite/` on `127.0.0.1`, default port 8765. Tests start the same static files using an ephemeral localhost port. Pages cover search, form fields, fake login, an eight-row product table, scrolling/load-more, popups/dialogs and hidden text. They use only local HTML/CSS/JS, without frameworks, external requests or CDNs. Login accepts the **fake-only** pair `demo-user` / `demo-pass-only`.

The default Task 2 fake LLM remains a fixed sample script rather than a goal interpreter. For a deterministic form demo, from `backend/` run the test-only app (it uses the existing routes unchanged):

```bash
BROWSER_DRIVER=playwright USE_FAKES=true uvicorn tests.browser_demo:app --reload
# Optional: TESTSITE_URL=http://127.0.0.1:9876
```

Then create a run with either mode and stream the returned ID:

```bash
curl -sS -X POST http://localhost:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"goal":"Fill the local demo form","mode":"headless"}'
curl -N http://localhost:8000/api/runs/RUN_ID/events
```

Use `"mode":"headed"` to open a visible Chromium window. Linux needs a working `DISPLAY` or `WAYLAND_DISPLAY`; a missing display is rejected before launching, and launch failures return a sanitized display/installation message. The demo fills name/email/project, checks a checkbox, submits and finishes with 31 ordered events. Its test-only fake binds scripted target descriptions to the newest observation refs; it makes no model requests.

For the regular app, `BROWSER_DRIVER=playwright USE_FAKES=true uvicorn app.main:app --reload` selects the real driver while retaining the original sample fake LLM. That original fake is not a general browser agent; Task 4 will add real model behavior.

### Browser tests

From `backend/`:

```bash
pytest -q                  # Full suite; headed tests run when a display exists.
pytest -q -m 'not headed'   # Headless tests only.
pytest -q -m headed        # Visible Chromium smoke and scripted form/SSE run.
ruff check .
mypy .
```

Headless browser tests are part of normal runs and require the installed Chromium binary. Headed tests are marked and automatically skipped with a display-specific reason when no display is configured. On a Linux server, install the host libraries if needed with `playwright install --with-deps chromium`. No Xvfb dependency is added by this project.

### Observations, refs and actions

A single DOM evaluation collects visible interactive elements in the active page's **main frame**. It computes names in the order aria-label, aria-labelledby, explicit label, associated label, placeholder, alt, title, visible inner text. Names are capped at 80 characters, ordinary values at 100. Elements are sorted top-to-bottom then left-to-right, capped at the configured count; visible text prefers main/article, collapses whitespace and uses the configured character cap. `truncated` covers either cap.

`Observation` includes `url`, `title`, `generation`, `elements`, `text_excerpt`, `truncated`, plus the existing short `summary` for timeline compatibility. `to_prompt_text()` renders compact lines, for example:

```text
Page 'Demo Login' generation=2
[e12] textbox "Username" value="demo-user"
[e13] textbox "Password" value="[redacted]"
[e14] button "Sign in" value=""
Text: Demo login Use the fake credentials documented in the backend README. Username Password Sign in
```

Each element includes role/name/tag/type/value/href and nullable disabled/checked/expanded/selected/required state. The DOM gets `data-agent-ref="eN"` attributes. Ref numbers never repeat within a driver; they remain usable only until the next observation or an active-page switch. An old ref returns `STALE_REF`; a removed/unknown element returns `NOT_FOUND`; a hidden one returns `NOT_VISIBLE`. Callers must observe again after stale refs. The runner's loop detection compares observed semantic targets because fresh refs change every generation.

Filtering excludes hidden attributes, aria-hidden ancestors, display/visibility hiding, zero-size elements, opacity-zero/transparent text, clipped unreachable elements and tiny text (two pixels or less). Offscreen elements reachable by scrolling remain observable. Hidden label text is also excluded from accessible names. This is a visibility-based prompt-injection reduction, not a policy or content-trust boundary.

Password values are absent when empty and rendered as `[redacted]` when non-empty. Values are also redacted when input name/id/autocomplete/aria-label matches password, otp, one-time, token, secret, cvv, cvc, card, common cc-number/csc/exp, or ssn patterns. Visible extraction removes known sensitive input values. Typed values are never echoed in action summaries, and `step.proposed.value` is `[redacted]` for type actions; the actual value is passed only to the driver. Browser diagnostics are not logged or returned verbatim.

Supported actions:

- `click`: resolve/scroll/click with a bounded timeout; reports navigation and active-page changes.
- `type`: fill inputs/textareas, select by label then value, or clear/type contenteditable. Password results say `typed into password field`.
- Key convention: `type` with an empty target and a recognized exact key (`Enter`, `Tab`, `Escape`, `Backspace`, `Delete`, arrows, `Home`, `End`, `PageUp`, `PageDown`, `Space`) presses that key. The same value with a target is literal text.
- `scroll`: up/down/top/bottom; relative movement is about 80% of viewport height, summary reports whether it moved.
- `navigate`: only HTTP(S) and exact `about:blank`; waits for DOM content then bounded settling. Scheme rejection returns `BLOCKED_URL`.
- `wait`: numeric seconds clamped to 0.5–10; invalid/non-finite numbers return `INVALID_ACTION`.
- `extract`: visible target text, or main/article-first page text if untargeted, capped and redacted.
- `done`: no-op success.

Errors return sanitized `ActionResult` values with `ok`, `summary`, `error_code`, `navigated`. Codes include `STALE_REF`, `NOT_FOUND`, `NOT_VISIBLE`, `TIMEOUT`, `BLOCKED_URL`, `INVALID_ACTION`, `BROWSER_ERROR`, and the reserved hook result `PAUSED`. Cancellation propagates after browser cleanup.

Popups/new tabs become active automatically. Closing the active page falls back to the newest remaining page. JS dialogs are dismissed and reported only by type, never message text. Later tasks can use `get_active_page()`, `get_context()`, `on_active_page_changed(callback)`, `get_viewport()`, `pause_actions()` and `resume_actions()`. Callbacks receive the new Page and can be synchronous or async. These hooks do not implement preview streaming, input forwarding or takeover.

Known limits: Chromium only; main frame only; no iframe or shadow-DOM traversal; no real LLM; no screenshot/preview transport. DOM-derived names approximate accessible names rather than implementing the full accessibility tree. The tiny-text heuristic can exclude legitimate tiny labels. Navigation allows localhost for the demo; domain allowlists and private-network/SSRF policy belong to the future ActionValidator phase. Same-name duplicate controls can share the runner's semantic loop identity. No frontend, event schema or API route changes are included.
