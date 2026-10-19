# Clevis Phase 1 backend

The backend is Node.js 22 + TypeScript. It exposes a typed run API and SSE events, orchestrates an OpenRouter Planner/Actor loop, and drives an isolated PinchTab profile for each run. Run state is in memory and is intentionally single-process.

## Run locally

1. Copy `backend/.env.example` to `backend/.env`, set `OPENROUTER_API_KEY` and a strong `PINCHTAB_TOKEN`, and retain the default `FRONTEND_ORIGIN=http://localhost:5173`.
2. Run `docker compose up --build` from the repository root. This starts the backend and PinchTab `v0.15.2` on a private Docker network; PinchTab has no host-published port.
3. In another terminal run `cd "front end" && npm run dev`, then open `http://localhost:5173`.

The local smoke page is served at `http://localhost:8000/test-page.html` and can be selected in the existing Starting URL field. In the compose setup, the browser accesses it through `http://backend:8000/test-page.html`. For headed browser mode, run PinchTab and the backend directly on a local desktop with a display, set `ALLOW_HEADED=true`, and point `PINCHTAB_URL` at that local PinchTab server. Docker mode is headless.

## API

- `POST /api/runs` accepts `{ "goal": "…", "mode": "headed" | "headless" }` and returns `{ "runId": "…" }`. Optional `startUrl`, `maxSteps`, and `maxSeconds` preserve the frontend's existing URL and budget controls; request budgets cannot exceed backend environment limits.
- `GET /api/runs/:id/events` streams typed `text/event-stream` events with monotonically increasing `seq` IDs. Reconnect using `Last-Event-ID`.
- `POST /api/runs/:id/stop` cancels model and browser requests and closes the browser profile.
- `GET /api/runs/:id` returns the current state, result, and error.

Run states are `created → planning → running → finished | failed | stopped`. Event definitions and runtime validation live in `src/contracts.ts`; reserved `step.validated` and `approval.required` event shapes are declared but not emitted.

Timeline rationale is user-facing structured data (`goal`, `step`, `action`, one-sentence `why`), never model chain-of-thought. Page snapshots are delimited and explicitly treated as untrusted model input. Preview frames contain sensitive browser content and are sent only to the frontend over the backend API.

## PinchTab integration

PinchTab is pinned to `pinchtab/pinchtab:v0.15.2`. `src/pinchtab/paths.ts` holds all PinchTab paths. At that version the adapter uses `POST /profiles`, `POST /instances/start`, `POST /instances/{id}/tabs/open`, `GET /tabs/{id}/snapshot`, `POST /tabs/{id}/action`, `POST /tabs/{id}/navigate`, `GET /tabs/{id}/text`, and `GET /tabs/{id}/screenshot`. A unique profile is created per run and deleted after the instance is closed. The Compose config binds PinchTab only inside its private container network and allows only the backend hostname for the local smoke page.

Version `v0.15.2` documents screenshots and saved screencast recordings, but no live frame-stream endpoint. The adapter therefore emits periodic JPEG screenshots (about 1.4 fps); `ALLOW_SCREENCAST` is reserved for a future PinchTab live-stream adapter and does not enable a recording endpoint.

The frontend only talks to the backend. PinchTab is reachable only on the private Compose network and requires `PINCHTAB_TOKEN`. The Vite proxy forwards `/api` to `localhost:8000`; production deployments must set `FRONTEND_ORIGIN` to the exact frontend origin.

## Configuration

See `.env.example` for the complete variable list. `MAX_STEPS`, `MAX_SECONDS`, `MAX_LLM_TOKENS`, and `MAX_LLM_COST_USD` are hard per-run limits. OpenRouter token usage and reported cost are counted; stopping is enforced through `AbortSignal` for in-flight API and browser requests.
