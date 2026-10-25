# Web Task Orchestrator

Give the agent a browser task, watch the live preview, and take over for sign-in or other human steps.
Python 3.11+ and Node/npm are required. The default hybrid agent requires local PinchTab 0.15.2;
the explicit Playwright demo below needs neither PinchTab nor Docker.

## Run locally

From this repository root, run these three commands. The second and third run in separate terminals.

```bash
python3 -m venv backend/.venv && backend/.venv/bin/pip install -e './backend[dev]' && backend/.venv/bin/playwright install chromium
(cd backend && LLM_PROVIDER=fake BROWSER_DRIVER=fake AGENT_DRIVER=playwright BLOCK_PRIVATE_NETWORK=false .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000)
(cd 'front end' && npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache && npm run dev)
```

Port 5173 must be free: stop your previous frontend dev server with Ctrl+C before starting another.
Vite fails clearly instead of switching ports and breaking the WebSocket Origin check.

Open **http://localhost:5173**. These defaults use scripted actions and a generated preview; no API key is needed.
The API runs with one worker and admits three active runs by default, including paused runs.
`BLOCK_PRIVATE_NETWORK=false` is explicit only for this network-free fake browser demo: its
script uses a reserved `.test` hostname. Restore `BLOCK_PRIVATE_NETWORK=true` when switching
to a real browser; it is the secure production default.

For a real browser and model, create `backend/.env` from `.env.example` only if it does not exist,
set your private `OPENROUTER_API_KEY` and chosen `LLM_MODEL_PRIMARY`, then replace
the complete environment prefix in command 2 with
`LLM_PROVIDER=openrouter BROWSER_DRIVER=playwright AGENT_DRIVER=playwright BLOCK_PRIVATE_NETWORK=true`.
For the default hybrid agent, also remove `AGENT_DRIVER=playwright`, start the authenticated
local service using `python3 scripts/run_pinchtab.py`, and export the same PINCHTAB_TOKEN in
both terminals. See the backend README for the hidden token prompt and exact setup.
The frontend always runs the browser headlessly, inside its right-side preview. No separate Chromium
window opens. Headed mode remains available through the API for local diagnostics. Never commit `.env`.

Optional local demo site: `python3 scripts/serve_testsite.py` → http://127.0.0.1:8765.
Use that address in your goal. Ctrl+C stops a server. Restarting the API loses in-memory runs.

See [backend installation, protocols and privacy](backend/README.md),
[verification and remaining human checks](docs/phase1-verification.md),
[acceptance checklist](docs/phase1-acceptance.md), and [Phase 2 notes](docs/phase2-notes.md).
