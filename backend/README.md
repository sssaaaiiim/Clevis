# Web Task Orchestrator — Backend

A FastAPI server that drives a ReAct-style browser agent powered by
[OpenRouter](https://openrouter.ai/) and
[PinchTab](https://pinchtab.com/) (local HTTP browser bridge).

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11+ |
| PinchTab | latest |
| An OpenRouter API key | — |

---

## Setup

### 1. Install & start PinchTab

Follow the [PinchTab installation guide](https://pinchtab.com/docs) for your
platform, then start the server:

```bash
pinchtab server
# PinchTab listens on http://localhost:9867 by default
```

### 2. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Open .env and add your OpenRouter API key
```

`.env`:
```
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

Create an API key in your [OpenRouter account](https://openrouter.ai/keys).
The backend uses `deepseek/deepseek-v4-pro-0813` with reasoning enabled.

### 4. Run the server

```bash
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

Interactive docs: `http://localhost:8000/docs`

---

## API

### `GET /api/health`

Liveness probe.

```json
{ "ok": true }
```

---

### `POST /api/run`

Run the browser agent. Returns a **streaming NDJSON** response — one JSON
object per line — so the frontend can display live progress.

**Request body:**

```json
{
  "url": "https://example.com",
  "task": "Find the price of the first product",
  "max_steps": 10,
  "timeout": 120,
  "headless": true
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | required | Starting URL |
| `task` | string | required | Natural-language task description |
| `max_steps` | integer | 10 | Max agent steps (1–50) |
| `timeout` | integer | 120 | Per-request HTTP timeout in seconds (10–600) |
| `headless` | boolean | true | Run browser headlessly |

**Stream event shapes:**

```jsonc
{ "event": "status", "status": "Planning" }
{ "event": "log", "actor": "Planner", "msg": "Decomposed task into 5 steps." }
{ "event": "plan", "steps": [{ "id": 1, "label": "Load the page" }, ...] }
{ "event": "step", "index": 0 }
{ "event": "browser_tab", "tab_id": "..." }
{ "event": "log", "actor": "Navigator", "msg": "Navigated to https://example.com." }
{ "event": "status", "status": "Completed" }
{ "event": "result", "status": "success", "message": "Found price: $29.99" }
```

The frontend uses the `browser_tab` event to poll
`GET /api/screenshot?tab_id=...` while the task runs. The endpoint requests a
full-scale PNG from PinchTab rather than a downscaled, compressed JPEG.

PinchTab's `/instances/start` API rejects arbitrary launch arguments, so this
backend does not send unsupported fields that would prevent browser startup.
To set Chromium's device scale factor, add
`"extraFlags": "--force-device-scale-factor=2"` under PinchTab's top-level
`browser` configuration and restart PinchTab. PinchTab reserves
`--window-size` for its runtime window model; its built-in sizes include
`1280,800`, but do not guarantee that exact size per launch.

---

## Architecture

```
Frontend  ──POST /api/run──▶  FastAPI (main.py)
                                  │
                         ┌────────┴──────────┐
                         ▼                   ▼
                 OpenRouter API        PinchTab HTTP
             (DeepSeek V4 Pro)        (localhost:9867)
               agent reasoning        browser control
                                     + page screenshots
```

1. **Planning** — OpenRouter decomposes the task into ordered step labels.
2. **Execution loop** — for each step, PinchTab captures an accessibility-tree
   snapshot; OpenRouter chooses the next action; PinchTab executes it.
3. **Live preview** — the frontend polls the screenshot endpoint for the active
   tab and displays the latest full-scale PNG.
4. **Validation** — after all steps, OpenRouter judges whether the task succeeded.
5. All progress is streamed back as NDJSON so the UI can render live updates.
6. Layout telemetry compares the raw HTML size with the optimized snapshot and
   reports byte savings and estimated token savings. OpenRouter's actual token
   usage remains authoritative; failures in this optional telemetry do not stop
   task execution.
