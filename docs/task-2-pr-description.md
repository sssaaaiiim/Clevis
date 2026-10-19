# Add the async FastAPI run foundation with injected fakes

Restore the backend as a Python 3.11+ FastAPI application. Creating a run starts a tracked async task with a scripted browser and model, publishes typed lifecycle/action/budget events, and completes without external browser or model requests. Add replayable SSE, stop/takeover/resume controls, explicit state transitions, JSON errors, CORS, structured run logging and shutdown cleanup. Preview/input WebSockets accept and validate the run, then close as stubs for Tasks 5/6.

The runner imports interfaces, never fake implementations. Async locks protect the store, replay/subscription handoff and per-run transition/event ordering. Cancellation interrupts pending I/O; pauses freeze progress and active-time accounting. Step/time limits, repeated-action detection and unexpected driver failures terminate runs cleanly.

## Frontend compatibility

No frontend source, styling, configuration, manifest or lockfile changed. Based on `docs/discovery-report.md`:

| Existing frontend expectation | This API / work needed in Task 8 |
|---|---|
| Creation sends `goal`, `mode`, `startUrl`, `maxSteps`, `maxSeconds` | Accepts only `goal` and `mode`; extra fields return 422. Later frontend work must remove or explicitly reconcile these fields. Limits are server configuration in this task. |
| Creation formerly returned HTTP 202 and `{runId}` | Returns 201 and the same `{runId}`; current `res.ok` check accepts 201. |
| Errors use a flat `error` string | Errors use `{error:{code,message}}`; read `error.message`. |
| `plan.created.data.steps[].label` | Now `steps[].text`; numeric plan step `id` remains. |
| `step.proposed.data.goal`, `step`, `action`, `why`; active step matched by label | Now `stepId`, `planStepId`, `action`, `target`, `value`, `rationale`; map the plan step by ID and render structured rationale. |
| `step.executed.data.result` | Now `ok` and `resultSummary`. |
| `observation.summary.data.summary` | Preserved, with added `stepId`. |
| `budget.update.data.tokens` | Now `tokensUsed`, plus explicit step/time counters and limits. |
| `run.failed.data.reason` | Now `error`. |
| `run.stopped.data.reason` | Now empty data; frontend already has an operator-stop fallback message. |
| Preview comes from `preview.frame.data.dataUrl` over SSE | No frame event in this task. Future preview uses `WS /api/runs/{id}/preview`; the stub immediately closes. |
| No pause/resume, status recovery or operator-input integration | Add lifecycle handling for `run.paused`/`run.resumed`, REST status/takeover/resume and input WebSocket in later work. |
| Fetch-based SSE without reconnect | Existing URLs/`data:` JSON framing remain; add cursor/reconnect handling to use replay. |
| Vite `/api` HTTP proxy | Still points to the default backend port 8000; evaluate `ws: true` later for WebSockets. |

`run.started` and `run.finished.data.result` remain compatible. Run creation, events and stop retain their existing endpoint URLs. This task intentionally does not add compatibility aliases that would obscure the new event contract.

## Assumptions

- No `AGENTS.md` exists in the repository or ancestor directories as checked at task start.
- Explicit request mode overrides the reserved `BROWSER_HEADLESS` preference. Goals are trimmed before length validation. Unknown request fields are rejected.
- `USE_FAKES=false` prevents startup until real dependencies are implemented. No API keys were added to code or the environment example. Existing private `.env` and local `venv/` were preserved.
- Planning → running emits `plan.created`; no extra unrequested `run.running` event is introduced. Resume is valid only from paused.
- Stop is idempotent only for stopped runs, and returns 409 for finished/failed. Other control conflicts return 409. Control responses contain the full run state.
- Step budgets count every executed action, including `done`; active time includes planning and excludes pauses. Token usage is counted and reported, without token enforcement yet.
- A pending fake operation may finish while paused; no result, timeline event or budget progress is applied until resume. This task provides state transitions rather than real browser takeover semantics.
- History, tasks and queues are per-process memory. Run one worker; persistence, queue bounds, auth, real policies and preview transport are later work.
- WebSocket stubs accept first, close unknown runs with 4404, and close known runs normally with 1000 without meaningful data.

## Validation

Using an isolated Python 3.14.4 environment (project supports Python 3.11+; mypy targets 3.11), from `backend/`:

- `pip install -e '.[dev]'` — passed.
- `pytest -q` — **97 passed** in 6.86 seconds; one upstream Starlette TestClient/httpx deprecation warning. REST/SSE tests use `httpx.AsyncClient`; TestClient is used only for WebSocket stubs.
- `ruff check .` — passed.
- `mypy .` — passed, strict mode, 30 source files.
- `USE_FAKES=true uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log` — server started successfully on an isolated verification port.
- Real HTTP: `POST /api/runs` returned 201. `curl -fsSN /api/runs/{id}/events` received 15 events with contiguous sequence IDs and the expected ordering, ending in `run.finished`. `curl -fsSN -H 'Last-Event-ID: 5' ...` replayed exactly sequences 6–15.
- Real HTTP takeover/resume succeeded; stop completed in **0.051 seconds** and a repeated stop returned 200.
- Tests cover all 49 state pairs, all event variants, replay/fan-out and disconnect cleanup, complete runner order, pause/cancellation, step/time budgets, loop detection, all fake driver failure points, JSON errors, CORS, WebSockets and shutdown.
- `git diff --exit-code 2f11981 -- 'front end'` — passed: no frontend changes.

Implementation is split into the requested seven commits: setup/config; events/state/tests; store/emitter/tests; interfaces/fakes; runner/tests; API/SSE/tests; README and this PR description. No new Node/TypeScript backend or agent framework was introduced.
