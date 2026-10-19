# Phase 1 Discovery Report

## Repository findings

- **Frontend:** React 19 with JavaScript/JSX, built and served by Vite 6; `front end/package.json` and `package-lock.json` are the frontend package-manager manifests.
- **Frontend API integration:** `src/hooks/useTaskOrchestrator.js` currently posts to `POST /api/run` and consumes NDJSON, then polls `GET /api/screenshot`. The Vite dev proxy forwards `/api` to `http://localhost:8000`.
- **Existing backend:** FastAPI/Python under `backend/`, with a legacy NDJSON agent loop, OpenRouter client, PinchTab requests, screenshot proxy, and layout/token telemetry. No database or separate mock server is tracked.
- **Stack choice:** Node.js + TypeScript. The product frontend is JavaScript/React, so a TypeScript backend uses the same ecosystem while providing typed shared run/event contracts.
- **Existing frontend behavior to preserve:** task prompt, run parameters, local history, activity/timeline, live preview, and a Stop button are already present. The integration will adapt these to the new run/SSE contract without redesigning them.
- **Local environment note:** an ignored `backend/.env` and ignored `backend/venv/` were present in the worktree. They are not tracked source files and are not part of the removal.

## Existing backend inventory

| Existing path or dependency | Disposition | Reason |
|---|---|---|
| `backend/app/__init__.py` | REMOVE | Python package marker for the retired FastAPI backend. |
| `backend/app/api/__init__.py` | REMOVE | Python package marker; routes are replaced by the TypeScript API. |
| `backend/app/api/routes.py` | REMOVE | Legacy `/api/run`, `/api/screenshot`, and health routes are replaced with the run/SSE API. |
| `backend/app/config.py` | REMOVE | Python configuration is replaced by typed Node environment configuration. |
| `backend/app/models/__init__.py` | REMOVE | Python package marker for the retired model layer. |
| `backend/app/models/run_request.py` | REMOVE | Old Pydantic request schema is replaced by shared Zod contracts. |
| `backend/app/services/__init__.py` | REMOVE | Python package marker for retired service modules. |
| `backend/app/services/agent.py` | REMOVE | Legacy multi-action NDJSON agent loop is replaced with the bounded Planner/Actor loop. |
| `backend/app/services/openrouter.py` | REMOVE | Replaced by the typed, cancellable OpenRouter client. |
| `backend/app/services/token_telemetry.py` | REMOVE | Layout comparison telemetry is outside Phase 1. |
| `backend/app/utils/__init__.py` | REMOVE | Python package marker for retired utilities. |
| `backend/app/utils/ndjson.py` | REMOVE | NDJSON serialization is replaced by typed SSE events. |
| `backend/main.py` | REMOVE | FastAPI entry point is replaced by the Node HTTP server. |
| `backend/requirements.txt` | REMOVE | Python dependencies are replaced by the TypeScript package manifest. |
| `backend/README.md` | REWRITE | Keep setup documentation, replace obsolete endpoints/setup with Phase 1 run instructions. |
| `backend/.env.example` | REWRITE | Keep the environment template, document all new backend variables without secrets. |
| `backend/.gitignore` | REWRITE | Keep backend-specific ignores and add Node/build/runtime outputs. |

No frontend imports any listed backend file directly. Its old HTTP routes will be replaced with the new API contract before those routes are removed.
