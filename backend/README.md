# Clevis Python backend

An async FastAPI foundation for Python 3.11+. This task uses a scripted browser and LLM exclusively. It performs no real browser actions or model requests. The runner depends on interfaces; the application injects fake implementations.

From `backend/`, create an environment and install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
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
| `BROWSER_HEADLESS` | `true` | Browser preference reserved for later integrations; this API requires an explicit `mode`, which takes precedence. |
| `MAX_STEPS` | `30` | Hard action limit, including the final `done` action. |
| `MAX_SECONDS` | `300` | Hard active-time limit; includes planning and normal cleanup, excludes operator pauses. |
| `MAX_TOKENS` | `200000` | Reported limit and counter only; token enforcement is deferred. |
| `USE_FAKES` | `true` | Must be true in this task; false prevents startup. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |

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

Lifespan shutdown transitions active runs to stopped, cancels tasks and awaits cleanup. No database, authentication, real policy, browser, model or preview implementation is included. History and subscriber queues are unbounded in this initial in-memory implementation.

The unchanged frontend still expects legacy request and event shapes; see [Task 2 PR description](../docs/task-2-pr-description.md) for the exact mismatches and assumptions.
