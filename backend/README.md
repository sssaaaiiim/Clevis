# Clevis Python backend

An async FastAPI backend for Python 3.11+. Select a fake browser (default) or isolated Playwright Chromium. Choose a scripted fake LLM (default) or the real OpenRouter client. The runner receives its browser, LLM, validator and skills through interfaces.

From `backend/`, create an environment and install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
cp .env.example .env  # Only for a new local setup; preserve any existing private settings.
uvicorn app.main:app --reload
```

The API defaults to port 8000, matching the frontend Vite proxy. Use one worker: all runs, events, subscriptions and tasks are in process memory. Restarting loses them. The existing local `venv/` is unrelated to this setup and is left untouched.

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

Settings are loaded from the process environment and `backend/.env` when running from this folder. Environment values override the file. A key is required only for `LLM_PROVIDER=openrouter`. Unknown legacy settings in an existing `.env` are ignored; known budget/origin values still override defaults.

| Variable | Default | Behavior |
|---|---|---|
| `FRONTEND_ORIGIN` | `http://localhost:5173` | The single allowed CORS origin. |
| `BROWSER_HEADLESS` | `true` | Default preference; the required per-run `mode` always takes precedence. |
| `MAX_STEPS` | `30` | Hard action limit, including the final `done` action. |
| `MAX_SECONDS` | `300` | Hard active-time limit; includes planning and normal cleanup, excludes operator pauses. |
| `MAX_TOKENS` | `200000` | Hard total prompt + completion token limit across planning, actions and retries. |
| `USE_FAKES` | `true` | Legacy compatibility setting; select components with BROWSER_DRIVER and LLM_PROVIDER. |
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
| `POST /api/runs` | `{ "goal": "…", "mode": "headless" or "headed" }` → HTTP 201 `{ "runId": "…", "previewToken": "…" }`; starts a tracked async task. |
| `GET /api/runs/{id}` | `{runId,status,goal,mode,result,error,createdAt}`; nullable result/error. |
| `GET /api/runs/{id}/events` | Replay plus live SSE; closes after the terminal event. |
| `POST /api/runs/{id}/stop` | Stop, cancel pending I/O, close resources; repeated stop returns 200, other terminal states return 409. |
| `POST /api/runs/{id}/takeover` | Running → paused, reason `takeover`; invalid state returns 409. |
| `POST /api/runs/{id}/resume` | Paused → running; invalid state returns 409. |
| `WS /api/runs/{id}/preview` | Origin + first-message token auth, binary image frames and JSON status/heartbeat; unknown run closes 4404. |
| `WS /api/runs/{id}/input` | Unchanged stub: known run closes 1000, unknown run 4404; no operator input yet. |

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
| `budget.update` | `{stepsUsed,maxSteps,secondsUsed,maxSeconds,tokensUsed,maxTokens,promptTokens,completionTokens,costUsd,maxCostUsd,costEstimated}` |
| `run.paused`, `run.resumed` | `{reason}` |
| `run.finished` | `{result}` |
| `run.failed` | `{error}` |
| `run.stopped` | `{}` |

`step.validated` (`{stepId,verdict,reason}`) and `approval.required` (`{stepId,action,risk}`) are defined and validated, but never emitted in this task. There is no `preview.frame` SSE event.

An action has `action` (`click`, `type`, `navigate`, `scroll`, `extract`, `wait`, `done`), `target:{ref,description}` with nullable fields, nullable `value`, a one-sentence `rationale` up to 300 characters, and nullable `plan_step_id`. The event uses `planStepId`. Extra fields, including raw model chain-of-thought fields, are rejected. Observations and action results on the timeline are limited to short summaries.

The explicit transition table is in `app/core/state.py`: created → planning → running ⇄ paused. Failures and stop are allowed from every non-terminal state; finished is allowed from running or paused. Terminal states accept no transitions. Entering planning emits `run.started`; planning → running emits `plan.created`; paused → running emits `run.resumed`. The runner finishes only while running.

Each turn emits observation summary → proposed → executed → budget update. Denied, empty-result and stale-ref attempts count toward steps and return feedback for another proposal. Three consecutive stale/not-found results fail. A nonempty successful `done` finishes with its value. Empty `done` is re-asked once.

Pauses freeze counters and runner publication. Already-started I/O may complete, but no new browser/LLM call starts while paused. On resume, a pre-pause proposal is discarded and the browser is re-observed; an action already executed is not replayed. This is orchestration pause, without browser takeover. Stop aborts in-flight work, closes run resources, then emits stopped; the HTTP response waits for cleanup. SDK connections are shared until application shutdown.

Loop detectors stop three consecutive identical `(action, target ref, value)` proposals, or five successful steps with an unchanged URL and element fingerprint. Fresh observation refs are excluded from the fingerprint; actual element state and values are included. Error summaries list recent action kinds and refs, without typed values.

## Code layout and scope

- `app/core/`: event models, explicit state transitions, async store, replay/fan-out emitter, budget counters.
- `app/interfaces/`: browser/preview, validator, skills and generic typed LLM contracts.
- `app/fakes/`: canned browser operations with failure injection and scripted plan/actions with fake usage.
- `app/agent/runner.py`: injected orchestration, cancellation, pause, budgets and loop detection.
- `app/api/`: REST/SSE routes, authenticated preview WebSocket and input stub.
- `app/runtime.py`: per-run state machines, dependency construction, task registry and shutdown cleanup.

Lifespan shutdown transitions active runs to stopped, cancels tasks and awaits cleanup. Preview uses per-run token authentication; application-wide auth, database persistence and real policies remain later work. History is bounded by the run step limit; subscriber queues remain unbounded in this initial in-memory implementation.

Some frontend timeline fields still expect legacy event shapes; see [Task 2 PR description](../docs/task-2-pr-description.md) for the exact mismatches and assumptions.


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

For the regular app, `BROWSER_DRIVER=playwright USE_FAKES=true uvicorn app.main:app --reload` selects the real driver while retaining the original sample fake LLM. That original fake is not a general browser agent; select LLM_PROVIDER=openrouter for goal-driven behavior.

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

Each element includes role/name/tag/type/value/href and nullable disabled/checked/expanded/selected/required state. The DOM gets `data-agent-ref="eN"` attributes. Ref numbers never repeat within a driver; they remain usable only until the next observation or an active-page switch. An old ref returns `STALE_REF`; a removed/unknown element returns `NOT_FOUND`; a hidden one returns `NOT_VISIBLE`. Callers must observe again after stale refs. Loop detection uses exact action/ref/value repetitions and an element-state fingerprint that excludes fresh refs.

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

Popups/new tabs become active automatically. Closing the active page falls back to the newest remaining page. JS dialogs are dismissed and reported only by type, never message text. Later tasks can use `get_active_page()`, `get_context()`, `on_active_page_changed(callback)`, `get_viewport()`, `pause_actions()` and `resume_actions()`. Callbacks receive the new Page and can be synchronous or async. The preview channel consumes these hooks; input forwarding and real takeover remain later work.

Known limits: Chromium only; main frame only; no iframe or shadow-DOM traversal; no real LLM; no screenshot/preview transport. DOM-derived names approximate accessible names rather than implementing the full accessibility tree. The tiny-text heuristic can exclude legitimate tiny labels. Navigation allows localhost for the demo; domain allowlists and private-network/SSRF policy belong to the future ActionValidator phase. Same-name duplicate controls can share the runner's semantic loop identity. No frontend, event schema or API route changes are included.


## OpenRouter agent loop — Task 4

Get a key from [OpenRouter keys](https://openrouter.ai/settings/keys), then edit your private
`backend/.env` (never commit it):

```dotenv
LLM_PROVIDER=openrouter
BROWSER_DRIVER=playwright
OPENROUTER_API_KEY=your-private-key
LLM_MODEL_PRIMARY=your-selected-model-id
LLM_MODEL_FALLBACK=
```

Choose any model with reliable JSON/tool support from the OpenRouter catalog. Your selected model
is **DeepSeek V4 Flash**; its model ID is populated in `.env.example` and the local ignored `.env`.
Model IDs are configuration, never constants in the client or runner. A missing key or primary
model prevents real-provider startup. Keep fake defaults for deterministic, non-billable development.
The installed official OpenAI Python SDK is **2.54.0**, using `AsyncOpenAI` chat completions with
OpenRouter's base URL. No OpenRouter SDK or agent framework is used.

| Variable | Default | Behavior |
|---|---|---|
| `LLM_PROVIDER` | `fake` | `fake` or `openrouter`. |
| `OPENROUTER_API_KEY` | empty | Secret, required for the real provider; never logged. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible endpoint. |
| `LLM_MODEL_PRIMARY` | empty | Required in real mode; example file uses your selected model. |
| `LLM_MODEL_FALLBACK` | empty | Optional one-time fallback to a second configured model. |
| `LLM_TEMPERATURE` | `0.2` | Sampling temperature. |
| `LLM_MAX_OUTPUT_TOKENS` | `800` | Per-request output token cap; reasoning can share this budget. |
| `LLM_REQUEST_TIMEOUT_S` | `60` | Timeout on each completion and catalog request. |
| `LLM_MAX_RETRIES` | `2` | Extra primary-model attempts for invalid output; also transport retries if no fallback. |
| `MAX_COST_USD` | `0.50` | Per-run cost limit; `0` disables cost enforcement. |
| `MAX_HISTORY_STEPS_IN_PROMPT` | `8` | Detailed recent feedback; older steps retain short status lines. |

The client checks catalog `supported_parameters` before using `json_schema` output. Unknown or
unsupported models get JSON-only instructions with tolerant object/fence parsing and Pydantic
validation. Structured requests use a strict schema and `provider.require_parameters=true`.
A rejected output gets a short validation-type correction without echoing the raw response. Invalid
output retries count tokens and cost. Timeout, 429, or 5xx switches to the configured fallback;
invalid output switches after primary repairs are exhausted. Only one fallback attempt is made.
Without a fallback, transport retries use the configured retry count. Exponential backoff with
jitter respects numeric or HTTP-date `Retry-After`; run cancellation/time budgets interrupt the wait.
401/403 never retry. SDK built-in retries are disabled to avoid hidden duplicate requests.

OpenRouter's server-side `models` list was verified but is intentionally not sent: client-side
fallback lets us adapt structured output to each model's capability and repair invalid JSON,
which server-side error fallback cannot do. Optional app-attribution headers were verified and
are omitted. See [the verification and PR notes](../docs/task-4-pr-description.md).

Planning uses only the goal. Actor messages include the goal, plan/current step, remaining steps
and a fresh observation. Website content and feedback go only in a user message inside randomized
untrusted delimiters; no old observations are resent. Secrets and delimiter-like strings are
neutralized. This is an injection baseline, not a complete policy/security guard. The only credential
exception is explicitly supplied fake demo credentials on the local test site; CAPTCHA, 2FA,
payments and missing credentials require a final handoff explanation.

All type proposals redact their value. Timeline summaries redact known typed values and API keys.
Final results may include a typed value subsequently observed as public, non-redacted field data
(e.g. a search term in a product name or a fake username in a welcome message). Password/secret
fields remain redacted. Never enable SDK HTTP body/headers debug logging.

Budgets include planning and all returned retry usage, including invalid outputs. Active seconds
exclude paused time; all attempts count as steps, including denied/stale/empty-result proposals.
The final `done` also counts. Budget updates add `promptTokens`, `completionTokens`, `costUsd`,
`maxCostUsd`, and `costEstimated` without changing routes or other events. A limit failure emits
final counters and identifies the exceeded limit and progress. Near the step limit, the prompt
asks for a partial result. Cost uses reported `usage.cost` when present, otherwise catalog token
prices (or a conservative $100/million tokens when catalog prices are unknown), flagged estimated.
Estimates are not a billing guarantee; provider routing/caching may change actual charges. A request
cancelled before returning usage may still be billed remotely, with unreported usage unavailable.

Run local smoke goals from [smoke-tasks.md](../docs/smoke-tasks.md). Start the static site and API
in separate terminals. Normal `pytest -q` never opts into paid model calls, even with a key present.
For explicit live tests, export the key and model securely in your shell (or load your private env
using your local environment manager), then from `backend/`:

```bash
pytest -q -m live tests/test_live_smoke.py
pytest -q -m live tests/test_live_smoke.py -k search
```

The tests serve isolated localhost fixtures, use real headless Chromium, and check each expected
result and SSE termination. Live tests skip without `OPENROUTER_API_KEY` or a primary model.

Troubleshooting:

- **401/403**: check the key, permissions and account access. Errors never echo provider bodies.
- **429/5xx**: wait for Retry-After or configure a fallback with sufficient account credits.
- **402**: fund the account or use a different account/key; no automatic retry.
- **Invalid JSON**: choose a model with reliable JSON support; repair attempts are bounded. A model
  spending its output budget on reasoning may need a larger `LLM_MAX_OUTPUT_TOKENS`.
- **Budget errors**: inspect the last budget update and partial action history; adjust the relevant
  limit in `.env`. Denied/stale attempts and planner tokens also count.
- **Loop errors**: inspect action kinds/refs and the latest observation; retry with a clearer goal.

Task 4 left frontend/API routes unchanged. Task 5 adds the authenticated preview below; other
legacy timeline-field rewiring and real takeover remain later work.


Task 4 verification: **210 offline tests passed**, five live cases skipped by default; **all five
live smoke goals passed** with the selected DeepSeek V4 Flash model. Ruff, strict mypy and the
editor's BasedPyright checks pass (zero editor errors/warnings). Real-server curl verification
received 19 ordered events ending in `run.finished` and confirmed Last-Event-ID replay.
See the [PR verification notes](../docs/task-4-pr-description.md) for commands and assumptions.


## Sharp live preview — Task 5

The browser streams through a Playwright CDP session into a per-run in-memory PreviewHub, then
an authenticated WebSocket. Preview never enters SSE, RunStore or the agent's model input.
Each viewer has an independent bounded queue: the latest frame wins and old frames are dropped.
A full/closed viewer cannot hold up acknowledgements, capture, another viewer or the agent.
Decoding base64 and inspecting image headers happen in a worker thread. JPEG/PNG image bytes
are forwarded unchanged: no server resize or re-encoding.

The source requests `ceil(viewportWidth * deviceScaleFactor)` by
`ceil(viewportHeight * deviceScaleFactor)` maximum pixels. Chromium 156 otherwise emits a
DIP-sized screencast at scale 2; an explicit compositor viewport via
Emulation.setDeviceMetricsOverride preserves the CSS viewport while producing native pixels.
Some first frames during window creation/navigation are temporarily clipped. They are still
acknowledged and dropped; only full-size frames are published. If no valid frame arrives within
three seconds, use native-device-resolution screenshot fallback rather than stretching pixels.

`DEVICE_SCALE_FACTOR=1` is lighter; `2` provides crisp HiDPI text at about **4× the pixels**.
Tune JPEG quality and maximum FPS for the available bandwidth. Both headed/headless modes use
this channel. Headed needs a working display; opening a new tab or closing the active tab reattaches
preview. Main-frame navigation and CDP close/error also restart capture, with bounded retries.

| Variable | Default | Effect |
|---|---|---|
| `SCREENCAST_FORMAT` | `jpeg` | `jpeg` or `png`; PNG is lossless and generally larger. |
| `SCREENCAST_QUALITY` | `85` | JPEG quality 1–100; omitted for PNG. Fallback uses JPEG. |
| `SCREENCAST_MAX_FPS` | `15` | Server drops frames above this rate; every frame is still acknowledged. |
| `SCREENCAST_EVERY_NTH_FRAME` | `1` | Chromium's positive frame-sampling interval. |
| `SCREENCAST_FALLBACK_FPS` | `2` | Screenshot polling rate if CDP fails/no valid first frame. |
| `PREVIEW_IDLE_RESEND_S` | `1.0` | Resend the cached frame while static; no new browser capture. |
| `PREVIEW_CLIENT_QUEUE` | `2` | Per-viewer latest-frame queue capacity. |
| `PREVIEW_AUTH_TIMEOUT_S` | `5` | Deadline for the first auth message. |
| `PREVIEW_RETAIN_AFTER_END_S` | `30` | Retain the final image in RAM, then discard it. |

Chrome only captures repaints. A static page therefore has near-zero new-image FPS and is healthy:
we check CDP health independently, resend the latest image, and show “Preview paused: page is idle”.
No frame/health heartbeat for five seconds becomes stalled. After three failed attach attempts,
or three seconds without a valid initial frame, fallback reports low-frame-rate mode. It polls
`page.screenshot(type="jpeg", quality=..., scale="device")` and retries CDP every 30 seconds.
Fake browser runs use a Pillow-generated 640×360 JPEG counter/timestamp pattern, at up to 2 FPS,
without a real browser or any disk writes. Pillow is a runtime dependency because fake mode is
available in ordinary installations; tests also use it to inspect encoded image dimensions.

### Preview authentication and wire format

`POST /api/runs` adds **previewToken** to its 201 response. Keep it only in the current UI session's
memory. It is bound to the returned run, never placed in a URL, event, history, log or RunStore.
Connect to `WS /api/runs/{id}/preview` using the exact configured FRONTEND_ORIGIN as the Origin.
The first message, within the auth deadline, must be:

```json
{"type":"auth","token":"<previewToken from create response>"}
```

Unknown run: close **4404**. Missing/wrong/late auth: **4401**. Wrong/missing Origin: **4403**.
Multiple viewers may authenticate with the same run token. Valid late viewers receive the retained
image before ended status; after retention expiry they receive ended without an image.
Run shutdown closes CDP/capture tasks; application shutdown purges all frames and tokens.

Server JSON messages:

```json
{"type":"status","status":"waiting|live|stalled|fallback|ended","message":"..."}
```

The server also sends `{"type":"ping"}` every 20 seconds. Reply with `{"type":"ping"}` to receive
`{"type":"pong"}`; the frontend sends its own ping every 20 seconds too. Other client messages
are ignored. A viewer without an application heartbeat for about 40 seconds closes 4408. Uvicorn
also sends native WebSocket ping frames every 20 seconds by default; browsers answer those
at the protocol level. To set explicit transport timeouts when deploying:

```bash
uvicorn app.main:app --ws websockets-sansio --ws-ping-interval 20 --ws-ping-timeout 20
```

Binary frame layout: **[4-byte unsigned big-endian JSON byte length N][N UTF-8 metadata bytes][image]**.
Metadata contains format, width/height in actual encoded pixels, deviceScaleFactor, CSS
viewportWidth/viewportHeight, pageScaleFactor, scrollOffsetX/Y, offsetTop, seq, ISO UTC ts and
an opaque per-page tabId. CDP's deviceWidth/deviceHeight are DIPs, so they are not used as image
pixel dimensions; dimensions come from the encoded image header. CDP timestamp/scale/scroll
fields are preserved or converted to UTC; viewport information comes from the driver.
Idle resends repeat the same seq/ts, so receipt is a heartbeat rather than a new capture.

```javascript
ws.binaryType = "arraybuffer";
ws.onopen = () => ws.send(JSON.stringify({type: "auth", token: previewToken}));
ws.onmessage = ({data}) => {
  if (typeof data === "string") { /* handle status/ping/pong */ return; }
  const n = new DataView(data).getUint32(0, false);
  if (n > 65536 || n + 4 >= data.byteLength) throw new Error("Invalid preview frame");
  const frame = JSON.parse(new TextDecoder().decode(new Uint8Array(data, 4, n)));
  const image = new Blob([data.slice(4 + n)], {type: `image/${frame.format}`});
  // Decode with createImageBitmap; draw into canvas.width=frame.width / height=frame.height.
  // CSS width <= frame.width / frame.deviceScaleFactor; preserve aspect ratio and never upscale.
};
```

The existing frontend layout is preserved. Canvas internal dimensions exactly match the frame.
CSS fits the viewport container, capped at native CSS size; intermediate frames are dropped and
bitmap resources are closed. Hidden tabs skip bitmap decoding/drawing and show the latest frame
when visible. Reconnection backs off up to five seconds and stops after ended. Add `?debug=1`
to the Vite dev URL (or VITE_PREVIEW_DEBUG=1) for frame/canvas/CSS dimensions, DPR, painted FPS
and image bytes; the overlay is disabled in production builds. No frames go to localStorage or downloads.

The minimal create-run integration now forwards goal/mode only, appends an optional starting URL
to the goal, and passes the returned token to preview. Legacy per-run limit controls remain visible
but limits are server configuration. Broader timeline field/state rewiring remains Task 8.
The Vite /api proxy now forwards WebSockets; /input remains the existing stub.

### Preview development and verification

From `front end/`: `npm test` runs Vitest decoder/sizing/render/status/reconnection tests;
`npm run build` builds production. From `backend/`, the normal `pytest -q` includes headless
preview/CDP/WebSocket tests; `pytest -m headed` adds visible-window tests when a display exists.
For a deterministic local UI demo, start the static test site, then from backend:

```bash
LLM_PROVIDER=fake BROWSER_DRIVER=playwright uvicorn tests.preview_demo:app --reload
# Set DEVICE_SCALE_FACTOR=2 in the process environment to inspect HiDPI capture.
```

Open the frontend through `http://localhost:5173/?debug=1`, run any fake-demo goal, and inspect the
form. The demo injects a fake model script; it makes no billable LLM call. The requested native-scale
comparison screenshots, readings and protocol verification are in
[the Task 5 PR notes](../docs/task-5-pr-description.md).

Privacy: transport frames exist only in memory, including the bounded post-run retention window.
Do not enable screenshot/video/trace persistence or put tokens in URLs. Protocol DEBUG payload
logging is filtered for Uvicorn/websockets, including auth text and binary data. The only checked-in
images are the explicitly requested comparison composites of the controlled fake-data site/UI;
no raw transport frame or private page is saved. Serve deployed previews over HTTPS/WSS.

Troubleshooting:

- **Preview freezes:** verify every Page.screencastFrame gets Page.screencastFrameAck, including dropped frames; inspect CDP close/retry and status messages.
- **Blurry:** check encoded pixel size, DEVICE_SCALE_FACTOR and CSS size; the canvas must not be enlarged above native CSS size. Server never resizes/re-encodes images.
- **No new frames on a static page:** expected; idle resend and health checks distinguish static from stalled. Painted FPS may be zero.
- **4401/4403:** authenticate with the correct run's token and visit the exact FRONTEND_ORIGIN hostname/port; no token belongs in a query string.
- **Fallback:** CDP failed, detached repeatedly or supplied no valid frame within three seconds. Screenshot mode remains sharp and retries CDP after 30 seconds.
