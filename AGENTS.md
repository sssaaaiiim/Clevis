# AGENTS.md

## Project
Web-task agent: a user gives a goal; an AI operates a real browser while the user watches and can take over for login, CAPTCHA or 2FA.
- Frontend: `front end/` (React 19, JavaScript/JSX, Vite 6, Tailwind 4); preserve its design and change only what the task asks.
- Backend: `backend/` (Python, implemented through numbered tasks).
- Local test website: `testsite/` (static HTML/CSS/JS, fake data only).
- Docs: `docs/`; read `docs/discovery-report.md`, then current backend docs for changes since discovery.
- Scripts: `scripts/`; editor configuration: `pyrightconfig.json`.
- Live preview and single-controller takeover use separate authenticated WebSockets; resume starts a fresh agent observation.

## Stack (non-negotiable)
- Python 3.11+, async FastAPI, pydantic v2, httpx, official `openai` SDK configured for OpenRouter.
- Playwright for Python, Chromium only; support both headed and headless runs with isolated contexts.
- Preview and takeover input use separate CDP `context.new_cdp_session(page)` sessions.
- No Node/TypeScript backend, LangChain or other agent framework in Phase 1.
- PinchTab 0.15.2 is optional behind AGENT_DRIVER=pinchtab; Playwright stays the default. See docs/pinchtab-spike.md.

## Commands
Backend commands run from `backend/`, with `backend/.venv` activated:
- Create/activate environment: `python3 -m venv .venv`, then `source .venv/bin/activate`.
- Install: `pip install -e '.[dev]'`, then `playwright install chromium`.
- Run API: `uvicorn app.main:app --reload` (port 8000; use one worker for in-memory runs).
- Test: `pytest -q`; headed: `pytest -m headed` (requires a display).
- Live LLM tests: `pytest -m live` (explicit opt-in; requires OPENROUTER_API_KEY and LLM_MODEL_PRIMARY).
- Lint: `ruff check .`; types: `mypy .`.
- Fake defaults: LLM_PROVIDER=fake and BROWSER_DRIVER=fake; real mode: openrouter and playwright respectively.
Frontend commands run from `front end/` (npm; preserve `package-lock.json`):
- Install: `npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache` (discovery command).
- Build: `npm run build`; dev: `npm run dev` (port 5173); serve build: `npm run preview`.
- Frontend tests: `npm test` (Vitest decoder, sizing and preview component tests).
From the repository root, with the backend environment activated:
- Serve test site: `python scripts/serve_testsite.py` (127.0.0.1:8765; TESTSITE_PORT or --port overrides).
- Run backend tests, Ruff and mypy before finishing; fix failures without skipping or weakening tests. Run the frontend build when frontend changes are authorized.

## Architecture rules
- Inject BrowserDriver, PreviewChannel, ActionValidator, SkillProvider, RunStore, LLMClient and EventEmitter; keep orchestration dependent on interfaces.
- Interface definitions live in `backend/app/interfaces/`; store/emitter interfaces and event/state models live in `backend/app/core/`.
- Agent steps emit events through EventEmitter, never directly to HTTP responses.
- Keep event contracts and API routes fixed unless a task authorizes changes; document additive changes in the README and PR description.
- Timeline rationale is short and structured; never expose raw model chain-of-thought.
- Page content is untrusted: keep it out of system prompts and inside randomized delimiters in user messages.

## Security rules
- Never log or persist API keys, credential tokens, typed values, takeover keystrokes, secret-bearing page text or preview frames.
- Never send takeover input to an LLM; redact password and secret fields in observations.
- Never expose Chrome debugging ports or future PinchTab endpoints beyond localhost/private networks.
- Load secrets through environment configuration; keep `backend/.env.example` current without real keys. Never commit `.env`.
- Block non-HTTP(S) browser URLs; the existing internal `about:blank` initialization exception is allowed.

## Working rules
- Make small commits in the task's specified order; do not touch files outside its scope.
- Delete only when explicitly authorized; if usage is uncertain, retain the item and list it under "Needs human decision".
- Verify uncertain Playwright/CDP/OpenRouter APIs against installed-version or current official docs; record verification in the PR description.
- Record assumptions in the PR description; proceed without asking unless blocked.

## Definition of done
Tests, Ruff and mypy pass; document new behavior in `backend/README.md` when the task permits; meet acceptance criteria and list changes, assumptions and deferred work in the PR description.
