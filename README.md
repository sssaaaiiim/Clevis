# Web Task Orchestrator

Give the agent a browser task, watch the live preview, and take over for sign-in or other human steps.
Python 3.11+ and Node/npm are required. PinchTab and Docker are optional; neither is needed below.

## Run locally

From this repository root, run these three commands. The second and third run in separate terminals.

```bash
python3 -m venv backend/.venv && backend/.venv/bin/pip install -e './backend[dev]' && backend/.venv/bin/playwright install chromium
(cd backend && LLM_PROVIDER=fake BROWSER_DRIVER=fake AGENT_DRIVER=playwright .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000)
(cd 'front end' && npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache && npm run dev)
```

Port 5173 must be free: stop your previous frontend dev server with Ctrl+C before starting another.
Vite fails clearly instead of switching ports and breaking the WebSocket Origin check.

Open **http://localhost:5173**. These defaults use scripted actions and a generated preview; no API key is needed.
The API runs with one worker and admits three active runs by default, including paused runs.

For a real browser and model, create `backend/.env` from `.env.example` only if it does not exist,
set your private `OPENROUTER_API_KEY` and chosen `LLM_MODEL_PRIMARY`, then replace
`LLM_PROVIDER=fake BROWSER_DRIVER=fake` in command 2 with `LLM_PROVIDER=openrouter BROWSER_DRIVER=playwright`.
Choose headed/headless in the UI; headed mode requires a working display. Never commit `.env`.

Optional local demo site: `python3 scripts/serve_testsite.py` → http://127.0.0.1:8765.
Use that address in your goal. Ctrl+C stops a server. Restarting the API loses in-memory runs.

See [backend installation, protocols and privacy](backend/README.md),
[verification and remaining human checks](docs/phase1-verification.md),
[acceptance checklist](docs/phase1-acceptance.md), and [Phase 2 notes](docs/phase2-notes.md).
