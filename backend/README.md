# Clevis Python backend

## Phase 2 graph skeleton

The internal agent loop now uses **LangGraph 1.2.17**, pinned in pyproject.toml and recorded in
`app/agent/version.py` as LANGGRAPH_TESTED_VERSION. OpenRouter is still called directly through
the injected LLMClient; no LangChain chains, agents, tools, or model integrations are used.
LangGraph installs langchain-core and LangSmith transitively. Automatic external tracing is
explicitly disabled around each run, including when shell tracing variables are present.

The graph is compiled once in `app/agent/graph.py` and runs inside the existing background task.
`runner.py` is the lifecycle bridge; its old cancellation/privacy helper lives in `execution.py`
and remains re-exported for existing callers. All frontend events still use EventEmitter → SSE;
LangGraph's internal updates are discarded by the bridge. API routes and event schemas are unchanged.
The already-defined `step.validated` event is now emitted between step.proposed and step.executed.

| Node | Responsibility |
|---|---|
| planner | Generate the initial plan; on revision preserve completed work and regenerate remaining steps. |
| navigator | Observe once, propose one action, account for tokens/steps, emit observation/proposal events. |
| policy_check | Call the injected PolicyValidator with current agent state; emit step.validated and approval.required. |
| approval_gate | Pause with interrupt; resume with an approved/denied Command, keeping browser resources alive. |
| executor | Execute the approved action or handoff, record sanitized history, emit execution/budget events. |
| outcome_check | Verify a completed/capped sub-goal with a bounded LLM call; enforce no-progress detection. |
| next_sub_goal | Advance only after verified completion; reset per-sub-goal counters. |
| revise | Retry with sanitized feedback, then re-plan remaining work; bound attempts. |
| finish | Own terminal transitions and success cleanup. |

Stop still cancels in-flight browser/LLM work and closes resources in finally. The bridge handles
both asyncio.CancelledError and 1.2.17's NodeCancelledError wrapper. Takeover uses the existing
state-machine pause gate, cancellation epoch and active-time clock; it does not use interrupt().
After resume, an interrupted turn returns to navigator for a fresh observation. Paused time does
not consume MAX_SECONDS. Existing global steps, tokens, cost and repetition/no-progress limits apply.

AgentState is a pydantic model to retain existing prompt-call compatibility and validate node
inputs. BudgetState is the canonical graph budget; the old injected Budget object is a synchronized
compatibility view. SubGoal records derive success conditions from the existing plan text in this
skeleton. SUBGOAL_MAX_STEPS (8) bounds actions before a completion check; SUBGOAL_MAX_ATTEMPTS (2)
bounds revisions after unsuccessful verification. StepRecord contains SHA-256 value_hash,
not value, and step_history is capped at MAX_HISTORY_STEPS_IN_PROMPT. The compatibility history
view is capped too. Actual values and original observations live only in a per-run injected context.
Checkpoint action values are removed, observation/feedback projections are redacted, and raw node
exception text is sanitized before LangGraph can checkpoint its error channels. No frames or
credentials belong to graph state.

The checkpointer is `langgraph.checkpoint.memory.MemorySaver` (an alias of InMemorySaver in
1.2.17). Every graph config uses thread_id = run_id. StateGraph/START/END import from langgraph.graph,
CompiledStateGraph from langgraph.graph.state, and interrupt/Command from langgraph.types; all imports
were verified against the installed package. Policy graph tests exercise production interrupt
persistence and approved/denied resumption with Command on the same run thread.

MemorySaver is process-resident and has **no automatic TTL**; restarting clears it. Terminal
snapshots are retained for inspection. Long-lived production processes will need retention/pruning;
the installed saver supports `await checkpointer.adelete_thread(run_id)`. Interrupts do not provide
cross-process recovery of live browser/client objects. That lifecycle must be extended when real
durable approval recovery is added; the current run task keeps those resources alive in process.

## Phase 2 policy engine

Production RunService injects a new PolicyValidator per run. Tests/embedders may still explicitly
inject an ActionValidator; legacy RunRecord validators remain supported, and the state-aware
protocol supplies the current Observation, private user goal and hash-only data-flow state.
No fake-mode switch disables production policy. Preview and takeover protocols are unchanged.

Rules are deterministic, evaluated from highest to lowest risk:

| Tier | Decision | Examples |
|---|---|---|
| 0 | allow | Public allowed-domain navigation, extract, scroll, wait. done/handoff stay available for safe exit. |
| 1 | allow, log metadata | Ordinary clicks, filling non-secret fields, select/checkbox interactions. |
| 2 | approval | Submit/Enter, payment/checkout/order pages, download/upload/send, unknown allowed-list destination, cross-domain data transfer. |
| 3 | deny | Blocked domains, private/metadata addresses, non-HTTP(S), hidden targets, financial confirmation pages, generated credentials. |

Password/secret-field typing is denied unless the exact proposed value occurs in the original
user goal. This is a conservative provenance heuristic, not proof of a credential's origin;
prefer takeover for real credentials. Hidden targets are checked from observation metadata;
drivers continue to exclude hidden elements and reject invisible/stale refs themselves.
Form ownership/action and download metadata supplement role/type/text heuristics. These
heuristics cannot prove a site's business semantics; policy approvals are not transaction verification.

| Variable | Default | Meaning |
|---|---|---|
| ALLOWED_DOMAINS | empty | Exact hostnames/IPs, comma separated; empty or * permits public hosts. |
| BLOCKED_DOMAINS | empty | Exact hosts always denied; * blocks all destinations. |
| BLOCK_PRIVATE_NETWORK | true | Deny non-global IPs, loopback/link-local, IPv4-mapped private IPv6, metadata hosts. |
| REQUIRE_APPROVAL_FOR_SUBMIT | true | Form submissions and unreferenced Enter keys require approval. |
| REQUIRE_APPROVAL_FOR_DOWNLOAD | true | Download links/buttons require approval. |
| REQUIRE_APPROVAL_FOR_UPLOAD | true | File inputs and upload/attach buttons require approval. |
| REQUIRE_APPROVAL_FOR_SEND | true | Message/chat/compose submissions require approval independently of submit setting. |
| AUTO_ALLOW_SAME_DOMAIN_DATA_FLOW | true | Same-domain reuse allows; false returns a warning. |
| MAX_DATA_FLOW_BYTES | 10000 | Bound tracked extraction bytes; exceeding it fails the run. |
| POLICY_LOG_VERDICTS | true | INFO metadata: runId, tier, action type only. |

Domain entries reject URL/path/port/wildcard-subdomain syntax at configuration validation.
Matching is exact: example.com does not implicitly allow sub.example.com. Blocked lists win.
Unknown hosts in a nonempty allowed list require approval. Production DNS resolution is async,
bounded to two seconds, checked across all answers, cached once per host per run, and fails
closed. Pure address tests inject a resolver and make no DNS requests. Known metadata names
are blocked independently of DNS. A browser context request guard also rejects forbidden
destinations; service workers are disabled so they cannot bypass routing. This applies to the
Playwright-owned browser in either agent-driver mode. DNS rebinding between validation and
Chromium's independent lookup remains a limitation; network egress controls are still needed
for hostile environments.

Local test sites require an explicit BLOCK_PRIVATE_NETWORK=false in a dedicated development
configuration. Do not use that exception on real accounts or untrusted goals. Legacy automated
form flows also need explicit approval handling or test-only approval settings. Secure defaults
are not relaxed automatically for localhost, fake models or the test runner.

The test suite explicitly uses IsolatedSettings to permit localhost and automated submit/send
for legacy demo scenarios. Policy tests instead use PolicySettings with the secure production
defaults. Neither class is used by production code; a regression test verifies the separation.
The former approval-stub test now checks a real pause and explicit consent before execution.

Data-flow tracking records successful extract results as SHA-256(first 500 characters),
source hosts and byte lengths in AgentState.data_flow. It stores no extraction value there.
Exact matching values at least 20 characters long copied to a different host require approval;
short/numeric/common values are exempt. Multiple source domains remain flagged. This is an
exact-prefix hash check, not a semantic/substring detector: transformed text and content read
only through observations are not comprehensively tracked. Budget limits are enforced atomically.

Every policy verdict emits step.validated with the existing wire values allow/deny/approval.
The Python Verdict also accepts decision=approve and exposes its decision property without
changing that event. Denied actions never reach act; three consecutive policy denials on one
sub-goal fail the run. approval.required retains its existing {stepId, action, risk} fields and adds approval metadata;
the action is the redacted checkpoint projection, never raw typed content.

As expressly requested for this task, run.paused adds a reason=approval variant with a typed
request {action_summary, risk, page_url}; page_url contains a hostname only, without credentials,
path or query. The graph saves pending_approval, calls interrupt, and retains its browser and
LLM in the existing task while awaiting a decision. Internal submit_approval(machine, decision)
feeds Command(resume={decision: approved|denied}) back into that thread. This internal bridge
is private to the runner; authenticated HTTP endpoints now submit decisions through it.
The frontend shows an approval dialog, and its takeover Resume button cannot approve a policy action. Approvals do not grant input control. Paused time is
excluded from MAX_SECONDS; Stop cancels the wait and closes resources. Denied human decisions
are recorded as compact feedback before a fresh proposal.

Before real-account use:

- Set ALLOWED_DOMAINS to the intended exact hosts and review BLOCKED_DOMAINS.
- Keep BLOCK_PRIVATE_NETWORK=true and all approval switches enabled.
- Confirm the approval dialog and Stop control work; do not treat takeover Resume as approval.
- Review transaction heuristics, hash-matching limitations and deployment egress controls.

Policy logs look like {message: policy.verdict, runId: ..., tier: 2, action: click}. They include
no goal, destination domain, element name, rationale, typed value, page text or approval payload.

The authorized Phase 1 expectation update includes step.validated between step.proposed and
step.executed. Lifecycle and graph tests share `tests/event_sequences.py`; all other assertions
are preserved. See docs/phase2-task1-graph.md and docs/preview-repetition-results.md for actual
gate results and the separate investigation of intermittent preview failures.

PinchTab 0.15.2 may return HTTP 409 `navigation_changed` during a link click. This is mapped
to STALE_REF so the runner re-observes the current page and proposes its next action. It does
not retry the click automatically or misreport it as a token/server failure. Other 409 responses,
including paused-handoff refusals, are not automatically treated as navigation conflicts.

PinchTab HTTP requests use operation-specific deadlines: navigation gets at least
NAV_TIMEOUT_MS/1000 + 2 seconds, actions get at least ACTION_TIMEOUT_MS/1000 + 2 seconds,
and other requests use PINCHTAB_TIMEOUT_S. A slow operation reports TIMEOUT; connection
failures, interrupted connections and invalid server responses have distinct sanitized messages.
The terminal error names the attempted action; inspect the preceding Browser update for detail.

Invalid action arguments are recoverable: the runner records the rejected action, consumes its
step budget, obtains a fresh observation, and asks the model to correct the next action. Three
consecutive INVALID_ACTION results fail clearly; existing loop and budget limits still apply.
No browser validation is bypassed. Prompts specify numeric wait seconds, supported scroll
directions, full navigation URLs, and field-ref versus keyboard-key typing conventions.

An async FastAPI backend for Python 3.11+. The default hybrid agent uses PinchTab 0.15.2
for observations/actions and Playwright for isolated Chromium, preview and takeover. Choose a
scripted fake LLM (default) or OpenRouter. Dependencies are injected through interfaces.

From `backend/`, create an environment and install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
test -f .env || cp .env.example .env  # Preserve existing private settings.
# Start authenticated PinchTab first (see "Start the local PinchTab service" below).
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
| `MAX_CONCURRENT_RUNS` | `3` | Per-process active-run cap, including pauses and cleanup; POST returns JSON 429 `run_capacity_exceeded` when full. |
| `MAX_STEPS` | `30` | Hard action limit, including the final `done` action. |
| `MAX_SECONDS` | `300` | Hard active-time limit; includes planning and normal cleanup, excludes operator pauses. |
| `MAX_TOKENS` | `200000` | Hard total prompt + completion token limit across planning, actions and retries. |
| `USE_FAKES` | `true` | Legacy compatibility setting; select components with BROWSER_DRIVER and LLM_PROVIDER. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `BROWSER_DRIVER` | `fake` | With AGENT_DRIVER=playwright selects fake or real Playwright; ignored by the default hybrid driver, which launches real Chromium. |
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
| `POST /api/runs` | `{ "goal": "…", "mode": "headless" or "headed" }` → HTTP 201 `{ "runId": "…", "previewToken": "…", "controlToken": "…" }`; starts a tracked async task. |
| `GET /api/runs/{id}` | `{runId,status,goal,mode,result,error,createdAt}`; nullable result/error. |
| `GET /api/runs/{id}/events` | Replay plus live SSE; closes after the terminal event. |
| `POST /api/runs/{id}/stop` | Stop, cancel pending I/O, close resources; repeated stop returns 200, other terminal states return 409. |
| `POST /api/runs/{id}/takeover` | Quiesce running work → paused, reason `takeover`; idempotent for takeover pause; invalid state 409. |
| `POST /api/runs/{id}/resume` | Paused → running; invalid state returns 409. |
| `WS /api/runs/{id}/preview` | Origin + first-message token auth, binary image frames and JSON status/heartbeat; unknown run closes 4404. |
| `WS /api/runs/{id}/input` | Authenticated single-controller CDP input while paused for takeover/handoff; see protocol below. |

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
| `run.paused`, `run.resumed` | `{reason}`; handoff pause adds `{message}` |
| `run.finished` | `{result}` |
| `run.failed` | `{error}` |
| `run.stopped` | `{}` |

`step.validated` (`{stepId,verdict,reason}`) is now emitted by the Phase 2 policy node.
`approval.required` (`{stepId,action,risk}`) remains reserved for the approval task.
There is no `preview.frame` SSE event.

An action has `action` (`click`, `type`, `navigate`, `scroll`, `extract`, `wait`, `done`, `handoff`), `target:{ref,description}` with nullable fields, nullable `value`, a one-sentence `rationale` up to 300 characters, and nullable `plan_step_id`. The event uses `planStepId`. Extra fields, including raw model chain-of-thought fields, are rejected. Observations and action results on the timeline are limited to short summaries.

The explicit transition table is in `app/core/state.py`: created → planning → running ⇄ paused. Failures and stop are allowed from every non-terminal state; finished is allowed from running or paused. Terminal states accept no transitions. Entering planning emits `run.started`; planning → running emits `plan.created`; paused → running emits `run.resumed`. The runner finishes only while running.

Each turn emits observation summary → proposed → executed → budget update. Denied, empty-result and stale-ref attempts count toward steps and return feedback for another proposal. Three consecutive stale/not-found results fail. A nonempty successful `done` finishes with its value. Empty `done` is re-asked once.

Pauses freeze agent counters and runner publication. Takeover waits for cancellation of active browser/LLM work before accepting input; preview continues independently. On resume, interrupted or pre-pause proposals are discarded and the browser is re-observed with new refs. Completed actions are not replayed. Human-control deadlines are separate from the paused agent time budget. Stop aborts in-flight work, closes run resources, then emits stopped; the HTTP response waits for cleanup. SDK connections are shared until application shutdown.

Loop detectors stop three consecutive identical `(action, target ref, value)` proposals, or five successful steps with an unchanged URL and element fingerprint. Fresh observation refs are excluded from the fingerprint; actual element state and values are included. Error summaries list recent action kinds and refs, without typed values.

## Code layout and scope

- `app/core/`: event models, explicit state transitions, async store, replay/fan-out emitter, budget counters.
- `app/interfaces/`: browser/preview, validator, skills and generic typed LLM contracts.
- `app/fakes/`: canned browser operations with failure injection and scripted plan/actions with fake usage.
- `app/agent/runner.py`: injected graph/lifecycle bridge; graph.py and nodes/ own orchestration,
  with execution.py preserving cancellation/pause and graph-state helpers tracking budgets/loops.
- `app/api/`: REST/SSE routes, separately authenticated preview and controller WebSockets.
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

Popups/new tabs become active automatically. Closing the active page falls back to the newest remaining page. JS dialogs are dismissed and reported only by type, never message text. Later tasks can use `get_active_page()`, `get_context()`, `on_active_page_changed(callback)`, `get_viewport()`, `pause_actions()` and `resume_actions()`. Callbacks receive the new Page and can be synchronous or async. Preview and takeover consume these hooks; input uses a separate active-page CDP session.

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
is [DeepSeek V4.1 Flash](https://openrouter.ai/deepseek/deepseek-v4.1-flash); its model ID is populated in `.env.example` and the local ignored `.env`.
Model IDs are configuration, never constants in the client or runner. A missing key or primary
model prevents real-provider startup. Keep fake defaults for deterministic, non-billable development.
The installed official OpenAI Python SDK is **2.54.0**, using `AsyncOpenAI` chat completions with
OpenRouter's base URL. Keep OPENROUTER_BASE_URL at `https://openrouter.ai/api/v1`; the SDK
appends `/chat/completions`. The agent consumes a validated JSON action per turn while the
application streams its timeline and preview separately. No OpenRouter SDK or agent framework is used.

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
payments and missing credentials require the `handoff` action and a short human-facing reason.

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

Task 4 left frontend/API routes unchanged. Task 5 adds authenticated preview and Task 6 adds
takeover/handoff. The Phase 1 verification audit subsequently aligned the frontend timeline fields.


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
to the goal, and passes the returned token to preview. Per-run limit controls now explicitly show
"Server configured"; the timeline consumes the current Python event fields.
The Vite /api proxy forwards preview and input WebSockets; Task 6 implements /input below.

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

## Human takeover and agent handoff (Task 6)

Use `BROWSER_DRIVER=playwright` for real input. Capture remains independent and works in both
headed and headless Chromium. In headed mode you may also interact with the real window while
paused; keep the controller/frontend open for keep-alives. Fake-browser previews are test
patterns and have no interactive webpage; their input relay returns INPUT_UNAVAILABLE.

Run creation now returns `{runId, previewToken, controlToken}`. These are separate random,
run-bound capabilities held only in process/UI session memory. Never put either token in a URL,
localStorage, logs, SSE or RunStore. A preview viewer cannot control the browser with its token.

1. Click **Take over** beside Stop, or POST `/api/runs/{id}/takeover`. This pauses only a running
   run, sets reason `takeover`, cancels active work and waits up to 1.8 seconds for acknowledgement.
   The driver keeps its browser open on takeover cancellation. Repeating takeover while already
   paused for takeover returns 200; other invalid transitions return 409.
2. Open the input WebSocket with the first-message authentication below. One controller is allowed;
   multiple preview viewers remain supported. Input stays disabled until work is quiescent.
3. Click/type on the preview. The banner says **You are in control. The agent is paused**.
   Its privacy tooltip says **Your typing goes straight to the browser; it is not shown to the AI.**
4. Click **Resume agent** or POST `/api/runs/{id}/resume`. The controller closes, held keys/buttons
   are released, the driver resumes actions and the agent re-observes before proposing. Old refs
   cannot be used for a resumed turn. Stop works while paused and closes all browser resources.

The model can instead propose `handoff`, with a short, non-secret reason in value. The runner
emits `run.paused` data `{reason:"handoff", message:"Please sign in, then click Resume"}` and
uses the same controller path. Handoff is orchestration, never a browser action or loop repeat.
It counts as a step and is limited to MAX_HANDOFFS. Normal takeover pauses/resumes keep `{reason}`;
no existing event type was removed. The only REST response addition in this task is controlToken.

### Input settings

| Environment variable | Default | Purpose |
|---|---|---|
| TAKEOVER_MAX_SECONDS | 600 | Maximum duration of each human-control pause, even with keep-alives. |
| INPUT_IDLE_TIMEOUT_S | 120 | Maximum time without valid active input or controller ping. |
| INPUT_MAX_MESSAGES_PER_SECOND | 200 | Per-controller fixed one-second rate window; excess messages drop. |
| INPUT_MAX_TEXT_LENGTH | 2000 | Unicode characters per text message. |
| INPUT_MAX_MESSAGE_BYTES | 8192 | UTF-8 bytes per complete incoming message, including JSON. |
| MAX_HANDOFFS | 3 | Maximum agent-requested handoffs in one run. |

Paused time never consumes MAX_SECONDS. Either takeover deadline fails the run with
**Take-over timed out**, ends control/preview capture, and closes the browser. Losing a controller
connection frees its slot and releases held input; the agent stays paused until Resume or timeout.

### Input WebSocket protocol

Connect `WS /api/runs/{id}/input` with exact Origin=FRONTEND_ORIGIN. Within five seconds send:

```json
{"type":"auth","token":"<controlToken from POST /api/runs>"}
```

Unknown run closes 4404, wrong/missing Origin 4403, missing/wrong/late auth 4401, second controller
4409. All messages are strict Pydantic-validated JSON; unknown fields/types, malformed/oversize
messages and non-finite coordinates are ignored. Fifty rejects close 4400; rate-limit drops are
counted separately. Payloads and validation exception details are never echoed or logged.

```json
{"type":"mouse","action":"down","x":240,"y":210,"button":"left","clickCount":1,"modifiers":0}
{"type":"mouse","action":"up","x":240,"y":210,"button":"left","clickCount":1,"modifiers":0}
{"type":"wheel","x":240,"y":210,"dx":0,"dy":350}
{"type":"key","action":"down","key":"Enter","code":"Enter","modifiers":0}
{"type":"key","action":"up","key":"Enter","code":"Enter","modifiers":0}
{"type":"text","value":"<private typing, IME result or pasted text>"}
{"type":"ping"}
```

Mouse action also accepts move; buttons left/middle/right; clickCount 1–3. Modifiers are CDP
Alt=1, Ctrl=2, Meta=4, Shift=8. Keys are for non-printable keys and Ctrl/Meta shortcuts; printable
characters, IME commits and paste use Input.insertText. Enter includes its generated carriage
return on keyDown (needed for native form submission); keyUp never includes generated text.
Ctrl/Meta+A/C/X use the documented Blink selectAll/copy/cut commands. No Playwright keyboard/mouse
fallback is used. The relay never reads/modifies the DOM or reads the server clipboard.

Server replies:

```json
{"type":"state","accepting":true,"controller":true,"limits":{"maxTextLength":2000,"maxMessageBytes":8192}}
{"type":"state","accepting":false,"controller":true,"limits":{"maxTextLength":2000,"maxMessageBytes":8192}}
{"type":"pong"}
{"type":"error","code":"INPUT_UNAVAILABLE"}
```

The additive limits object lets the frontend split paste/IME by both configured Unicode and
UTF-8 byte limits. Legacy clients can ignore it and use defaults. Only a ready active controller
in paused reason takeover/handoff can send input; other states receive accepting=false.
Frontend pings every 20 seconds. Errors contain codes only, with no input or coordinates.

Coordinates are **viewport-relative CSS pixels**, clamped to [0,width−1]/[0,height−1]. Never add
scroll offsets or multiply by deviceScaleFactor. The frontend uses the actual drawn canvas rect:
`x = (clientX − rect.left) * viewportWidth / rect.width` (same for y). Letterbox margins belong
outside that rect. Latest displayed frame metadata supplies viewport dimensions at DSF 1 and 2.
Pointer moves throttle to about 60/s; wheels normalize lines/pages into CSS pixel deltas.

Keyboard capture belongs only to the controlled preview and its transparent DOM typing editor.
No input is held in React state, analytics, storage or console. The editor clears after every
send; IME composition stays local until committed. Ctrl/Meta+W/T/L/R, F5 and F12 remain browser
shortcuts. Tab reaches the remote form and also follows native frontend focus navigation so
keyboard users can leave the preview for Resume. Escape is forwarded, never treated as resume.

### Privacy and verification

Input never enters the agent's history, events or RunStore. After takeover, all observed editable
values are redacted. Ephemeral salted HMAC token/prefix fingerprints suppress literal input
reflected elsewhere in page content, metadata or final feedback without retaining a plaintext
input history. This redaction is conservative: a public username echoed in a welcome message is
hidden too. For the demo the browser shows `Welcome, demo-user`; the agent reports
`Welcome, [redacted]-[redacted]`. The resulting page's non-private content remains available.
Frames still stay exclusively in memory. No input traces, screenshots or videos are recorded.

Tests send CANARY-PASSWORD-9137 over the authenticated socket and check all-level captured logs,
SSE/events, stored state, exception responses and every recorded model request. They also check
split-character typing, password observations, actual login success, fresh refs, active-page
changes, controller replacement, idle/total deadlines, stop, native keys, rate limits and cleanup.
Playwright 1.64.0's installed cancellation path sends a protocol abort and waits for its result;
a real-browser auto-wait regression proves a cancelled agent click cannot fire afterward.

```bash
# From backend/, with the environment active:
pytest -q
pytest -m headed
ruff check .
mypy .
# Optional actual-product UI check: npm ci first; needs unused ports 5173 and 8000.
python -m tests.takeover_ui_demo
```

The optional check starts/stops its own local test site, Vite and API, performs login through the
actual resized canvas, and resumes in headless mode at DSF 1 and 2. The frontend always requests
headless mode; direct API/driver headed tests remain available with `pytest -m headed`.
It uses fake credentials and a scripted LLM; no key or paid call is needed. This is an automated
check; the separate human checklist is in [Task 6 PR notes](../docs/task-6-pr-description.md).

Limitations: main frame only; no file upload/download; no server clipboard read; platform clipboard
permissions and some shortcuts may not work via CDP. Paste sends text from the user's local paste
event. Automation-detecting CAPTCHAs may still block human interaction. The interface does not
provide a public Chrome debugging endpoint. Website transformations/exfiltration are outside
literal-echo filtering; domain/action policies and further injection guards remain later phases.

Troubleshooting:

- **Clicks land in the wrong place:** check the displayed canvas rect, CSS viewport metadata and
  letterboxing. DSF scales the image, not input coordinates; never add scroll offsets.
- **Keys do nothing:** confirm paused takeover/handoff, a ready active controller, and focus the
  preview. Another window may own control (4409). Fake test-pattern previews cannot accept input.
- **Enter does not submit:** keyDown must include the documented generated `text:"\r"`.
- **Control closes:** check Origin/token/auth deadline and reject counters; keep pings active.
  Reconnect stays paused; Resume ends the controller session deliberately.
- **Timed out while paused:** inspect TAKEOVER_MAX_SECONDS/INPUT_IDLE_TIMEOUT_S separately from
  agent MAX_SECONDS. A pause does not extend the independent human-control deadlines.

Task 6 verification: **296 backend tests passed, five paid live cases skipped**; Ruff and strict
mypy pass (84 source files), editor diagnostics are clear. **25 frontend tests and the production
build pass**. Automated actual-frontend login/resume passed headless DSF 2 and headed DSF 1;
the human-only checklist remains pending in the PR notes.

## Default hybrid PinchTab agent (0.15.2 required)

The attach spike passed; its historical recommendation was OPTIONAL. The agent now defaults to
AGENT_DRIVER=pinchtab and uses a separately installed,
authenticated loopback PinchTab **0.15.2** server for refs/actions. See
[spike evidence](../docs/pinchtab-spike.md). It is never required for preview, input, tests or startup
when AGENT_DRIVER=playwright is explicitly selected. PINCHTAB_URL must be a literal-loopback HTTP
origin and PINCHTAB_TOKEN is required for the default hybrid path. Startup rejects unreachable,
unauthenticated, authentication-disabled, or version-mismatched servers. Outages fail clearly;
there is no automatic fallback. API routes and event contracts are unchanged.


### Hybrid configuration and limitations

| Variable | Default | Behavior |
|---|---|---|
| `AGENT_DRIVER` | `pinchtab` | Hybrid agent; explicitly select `playwright` for the original BROWSER_DRIVER selection. |
| `PINCHTAB_URL` | `http://127.0.0.1:9867` | Bare HTTP origin with explicit port and literal loopback IP; no credentials, path, query, redirects or public host. |
| `PINCHTAB_TOKEN` | empty | Required for the default hybrid adapter; keep in private environment configuration. |
| `PINCHTAB_TIMEOUT_S` | `8` | Bounded HTTP request timeout. |

Only PinchTab **0.15.2** has been tested. Install it separately using the release instructions linked
in [the spike report](../docs/pinchtab-spike.md). The spike itself creates a disposable authenticated
loopback server, enables only attach, and cleans up its own processes:

```bash
# Repository root, with the backend environment active:
python scripts/spike_pinchtab_attach.py
python scripts/check_no_leftover_processes.py
python scripts/audit_repo.py
# Backend folder; managed is a TEST FIXTURE sentinel, never a production URL:
PINCHTAB_URL=managed pytest -q -m pinchtab
```

For an operator-owned server, use a loopback bind, explicit allocation, authenticated token,
attach enabled for loopback http/ws only, activity recording disabled, and network-body retention
disabled. Keep evaluate, file access, cookies, clipboard, uploads, downloads, macros and native
PinchTab screencast disabled. Supply the same token to the API through PINCHTAB_TOKEN, never in
a URL. Review the exact v0.15.2 configuration in the spike script before starting your own server.
There is no frontend PinchTab connection.

The hybrid driver keeps Playwright in charge of browser ownership, preview and input. It reconciles
PinchTab refs against the normal DOM observation's visibility/redaction limits, ignores raw snapshot
values, drops ambiguous matches, and re-snapshots before acting. Extraction uses the safe visible
observation text. This adds overhead and can omit ambiguous elements; it is not a guaranteed token
or latency optimization. A PinchTab outage fails safely with BROWSER_ERROR; there is no silent runtime
fallback. Both drivers obey pause/resume. The explicit Playwright path starts without PinchTab.

### Start the local PinchTab service

Install the tested release separately (`npm install -g pinchtab@0.15.2`), then verify
`pinchtab --version` reports `pinchtab 0.15.2`. From the repository root:

```bash
# Set one private token in this shell, without putting it in command history:
read -rs -p 'Local PinchTab token: ' PINCHTAB_TOKEN; export PINCHTAB_TOKEN
python3 scripts/run_pinchtab.py
```

In the backend terminal export the same token (repeat the hidden prompt above), leave
AGENT_DRIVER unset or set it to pinchtab, and run `uvicorn app.main:app --reload`.
Existing private `.env` files with AGENT_DRIVER=playwright continue to override the default;
change that setting intentionally. The helper reads environment variables, not `.env`.
Its URL is fixed at http://127.0.0.1:9867. Stop it with Ctrl+C after stopping the backend.

Verified against installed 0.15.2 `server --help`, `config schema --print`, and tagged
[configuration docs](https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/config.md)
and [attach docs](https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/instances.md).
The exact child command is `pinchtab server --bind 127.0.0.1 --port 9867 --log-level error`.
PINCHTAB_CONFIG selects a disposable configuration; PINCHTAB_TOKEN overrides the token at runtime.
Only attach is enabled, restricted to 127.0.0.1 and http/ws. Other optional capabilities retain
their disabled defaults, activity recording is off, and network bodies are not retained.
Child output is suppressed to avoid accidental sensitive logging. Configuration is removed on exit.
Preview and takeover remain on their existing independent Playwright CDP sessions.

## Phase 1 verification and operational limits

See [the current verification report](../docs/phase1-verification.md) for fresh-environment command
results, exact dependency versions, per-task live metrics, fixes and unverified human checks.
Historical Task 3–6 counts above describe those tasks, not the current audit.

Run one API worker. MAX_CONCURRENT_RUNS limits active runs (including paused/cleanup work) per
process; full admission returns JSON 429. Completed run metadata/history remains in memory until
restart. Frame retention is separately bounded and never persists frames. The 10-run RSS check is
a finite stress sample, not a proof of bounded memory for unlimited historical runs.

The UI now consumes plan text, planStepId, rationale, resultSummary and tokensUsed from the Python
contract. The obsolete per-run limit controls are read-only and say "Server configured"; they do not override server budgets;
set MAX_STEPS/MAX_SECONDS in backend configuration. No extra request fields were added.

This remains a local single-operator Phase 1 product. Policy tiers, private-network/domain rules,
approvals, skill libraries, accounts and persistent storage are Phase 2+. Main-frame-only observation,
Chromium-only operation, automation-sensitive CAPTCHAs and OS clipboard/browser shortcut limits
still apply. Human sharpness and actual typing checks remain required; automated tests do not imply
human sign-off. Docker is deliberately omitted and is not needed for development.


## One frontend preview

The product UI always creates runs with `mode="headless"`: the right-side canvas is the only
visible browser. Website popups become the active tab in that same preview. The backend still
supports `mode="headed"` through the API for local diagnostics; it deliberately opens a separate
Chromium window and requires a display.

For sharper text on HiDPI screens, set these in your private `backend/.env`, then restart the API
and start a **new** run (existing contexts retain their old scale):

```dotenv
DEVICE_SCALE_FACTOR=2
SCREENCAST_QUALITY=90
```

The portable defaults remain 1 and 85. Scale 2 sends roughly four times as many pixels. The server
passes frames through unchanged; canvas internal dimensions match frame pixels and its CSS size
never exceeds the native CSS viewport. Use `http://localhost:5173/?debug=1` to inspect frame,
canvas and CSS dimensions, device pixel ratio, painted sequence and tab identifier.

The loading overlay stays visible until a frame has actually been painted. ImageBitmap failures
fall back to the browser image decoder; failed frames can be retried on idle resend. Transient
WebSocket disconnects retain the last image while reconnecting. Authentication, Origin and missing
run failures show actionable messages instead of endlessly retrying. Use exactly the configured
FRONTEND_ORIGIN (default `http://localhost:5173`); `127.0.0.1` is a different Origin.

Regression checks (install frontend dependencies first):

```bash
# backend/, environment active; starts isolated local Vite/API servers, no model calls:
pytest -q tests/test_frontend_preview.py
# front end/:
npm test
npm run build
```

The real React/browser test runs at DSF 1 and 2 and verifies one headless agent, actual canvas
paint, popup switching, forced CDP detach recovery, resizing, login through the preview, resume,
and the retained final frame. Browser headed tests continue to verify diagnostic support.
Subjective sharpness still needs a human comparison at 100% browser zoom; no private frames are
saved by these tests.


## Search goals and completion

Typing a query only fills the field. The agent must submit using a visible search button or
`type` with `value="Enter"` and an empty target, then inspect a fresh observation. If the goal
requests a destination page, search results are an intermediate step: the agent must open the
relevant result and verify the destination URL, title and visible content before claiming success.
The system prompt no longer tells the agent to finish immediately after a search.

A displayed plan is not execution evidence. When a run stops, inspect its final timeline entry:
`run.finished` contains the model's result, `run.failed` contains the actual failure (for example
browser TIMEOUT, model error or a named budget limit), and `run.paused` requests human control.
Copy that final status/error when reporting a stopped search. The search-prompt regression and
local real-browser Enter → results → login-page regression do not prove a live search engine
will avoid CAPTCHAs or that a particular remote site is reachable.


## Takeover click recovery and HiDPI iframes

During human control, the banner no longer intercepts clicks intended for the browser underneath.
Input relay failures and input WebSocket close reasons are visible in the banner; **Reconnect
control** reopens only the authenticated input socket. It does not resume the agent, create a
second browser or interrupt the preview. Another controller still receives 4409, and expired
credentials or missing runs require starting a new run.

With DEVICE_SCALE_FACTOR other than 1, the screencast compositor enlargement can misroute
mouse events into cross-origin iframe surfaces in the tested Chromium. During takeover/handoff,
capture therefore restores native CSS geometry and uses the existing screenshot fallback at
SCREENCAST_FALLBACK_FPS (default 2). Images retain full device-pixel resolution; no resize or
re-encoding is performed. The first input on a newly attached HiDPI page waits 100 ms for updated
compositor hit-test regions. Resume returns capture to the regular screencast automatically.
Scale factor 1 keeps the ordinary screencast during takeover. The agent's observation still
covers only the main frame; human coordinate input can reach an iframe without inspecting it.

Verification uses only a local fake form in a cross-origin iframe, including DSF 1/2, resized
canvas input, controller disconnection/reconnection while paused, checkbox state, login/resume,
native frame dimensions, and return to screencast. Production challenges are a separate limit:
[Cloudflare does not support automated browsers for solving production challenges](https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/).
Successful local input does not guarantee that a site's verification accepts this browser.

## Human verification and visible failures

If a model proposes `wait` on a recognized interactive verification page, the runner converts
that proposal to the existing `handoff` action before validation. Recognition is deliberately
narrow: a human-verification checkbox, or a “Just a moment” title together with visible
verification text. It never clicks or solves the challenge. The ordinary handoff cap, timeout,
authenticated controller and fresh-observation-on-resume rules still apply. Ordinary loading
waits and the existing loop detectors are unchanged.

A terminal run's preview is a retained, read-only final frame: “Failed” and “Run ended” mean
the browser has closed, so clicking cannot affect it. Start a new run, then interact while the
banner says the agent is paused and the controller is accepting input. Cloudflare may still
reject the browser even with working input; this change does not promise challenge acceptance.

Task errors now appear immediately below the task title, above execution steps. Long messages
scroll within that summary instead of sitting underneath the floating CLEVIS COMMAND launcher.
Regression checks cover the error's actual screen position at both preview scale factors.


## Phase 2 Task 3: outcome verification, revision and approvals

Completion is checked when the Navigator proposes a nonempty `done` for its current sub-goal,
or reaches that sub-goal's step cap. Ordinary actions do not incur verifier calls. The verifier
uses `LLM_OUTCOME_MODEL` (empty means `LLM_MODEL_PRIMARY`), an 80-token output limit, and no
fallback model. Choose a fast model with reliable JSON support; no paid model was tested for
this change. Invalid output gets one corrective retry; both calls count toward token/cost budgets.
A second invalid response gives an unsuccessful, low-confidence verdict. Transport/auth failures
fail safely. Low confidence also marks retried or truncated input.

The user-message prompt contains at most 50 elements and the last 3 step summaries, plus title,
hostname and up to 500 characters of redacted visible text. This bounded excerpt is needed to
verify plain-text confirmations and table results which have no interactive element. All website
data stays inside randomized untrusted delimiters; values are omitted. A no-op done reuses its
current observation; a real action at the cap gets a fresh observation before verification.

A failed check triggers a revision of at most 300 characters containing only fixed feedback
categories and action types. Raw verifier reasons, page text, element descriptions and values
never enter revision feedback. First revision retries the Navigator; the second re-enters the
Planner, preserving completed sub-goals. This follows the task's explicit routing table. At the
retry limit the run finishes with a partial-result explanation. `revise` is a reserved internal
Action/step.proposed value for the timeline; model-proposed or executable revise actions are rejected.
Each verifier call emits budget.update with its accumulated usage.

| Setting | Default | Meaning |
|---|---|---|
| LLM_OUTCOME_MODEL | empty | Dedicated verifier model; empty selects primary. |
| APPROVAL_TIMEOUT_S | 300 | Approval wait limit; 0 disables this separate limit. |

POST /api/runs additionally returns `approvalToken`, separate from previewToken and controlToken.
It is an in-memory per-run capability. React holds it only in state and clears it when the run ends.
It is never sent in a URL, stored in localStorage, included in graph checkpoints or logged.

| Endpoint | Body | Authentication / result |
|---|---|---|
| POST /api/runs/{id}/approve | {approval_id: UUID4} | Bearer approvalToken; 200 {status:"approved"} |
| POST /api/runs/{id}/deny | {approval_id: UUID4, reason?: string <=200} | Bearer approvalToken; 200 {status:"denied"} |

Unknown runs return 404; missing/wrong tokens 401; stale IDs 422; invalid state or duplicate
submission 409. Only the matching pending request may be decided. The optional denial reason
is reduced to a fixed safe category before checkpointing or model feedback. Decision logs include
runId, tier and action type, never content. The modal shows only the sanitized summary, risk and
hostname. Both decision buttons disable after one click; Stop remains available. Stale requests
show an expiry message. run.resumed dismisses the dialog. Approval never enables take-over input.

Additive event fields: approval.required.data now also has `approval_id`, `action_summary`,
`risk`, `page_domain`, `tier` (existing stepId/action/risk remain). run.paused supports reason
`approval`; run.resumed uses `approved` or `denied` for approval decisions. No existing routes,
event types, preview protocols or take-over behavior were removed or renamed.

```text
agent proposes Tier 2 action
        |
        v
policy_node: verdict=approve, approval_id=uuid
        |-- approval.required {approval_id, action_summary, risk, page_domain, tier}
        |-- run.paused {reason:"approval"}
        v
graph pauses at approval_gate: interrupt(request)
        |
        | user sees modal and clicks Approve
        v
POST /api/runs/{id}/approve {approval_id} + Bearer approvalToken
        |-- authenticate and verify pending ID under the control lock
        |-- queue decision to the original run task (one graph producer)
        v
runner: agent_graph.ainvoke(Command(resume={decision:"approved"}), thread_id=run_id)
        |-- run.resumed {reason:"approved"}
        v
executor_node runs the approved action
```

A denial routes back to Navigator with sanitized feedback. The original runner retains the
private dependency context and browser while interrupted. Approval waiting uses asyncio.wait_for;
timeout fails with "Approval timed out" and Stop cancels the wait with normal cleanup. Approval
pause time does not consume the agent's active-time budget. MemorySaver and tokens remain process
resident: restart clears them; this is not durable approval recovery.

Task 3 evidence and compatibility-test adjustments: `docs/phase2-task3-verification.md`.
