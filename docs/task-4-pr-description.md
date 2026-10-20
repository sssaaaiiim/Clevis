# Run browser goals with OpenRouter and a bounded async agent loop

Replace the placeholder orchestration with planner → observe → one proposed action → validation → act → completion. Inject browser/model implementations; use the official async OpenAI SDK for OpenRouter, with one SDK transport per application lifespan and a separate session per run. Fake defaults remain deterministic and require no key or external model network.

The real actor now receives compact, labeled action history and fresh page data in a randomized untrusted user-message block. Planning receives only the goal. Track all returned planning/action/retry usage, enforce steps/active seconds/tokens/cost, and terminate repeated or stalled action sequences. Stop interrupts model/browser work and waits for cleanup; resume discards a pre-pause proposal and re-observes. Empty done, stale refs and policy denials receive bounded retry feedback.

## Verified OpenRouter and SDK features

Verified against current official documentation and the installed **openai Python 2.54.0** SDK on 2026-10-20:

| Feature | Verification and implemented behavior |
|---|---|
| OpenAI-compatible async client | [OpenAI Python SDK](https://github.com/openai/openai-python#async-usage): `AsyncOpenAI`, configurable `base_url`, `chat.completions.create`, per-call timeout, `max_retries=0`, async `close`, and `models.list`; also checked installed signatures and exercised them through MockTransport and live requests. |
| Structured output | [Structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs): `response_format.type=json_schema`, strict named Pydantic-derived schema. Planner schema enforces at most six steps. Nullable Action fields stay unchanged. Unsupported/unknown models receive JSON-only instructions and tolerant parsing instead. |
| Capability and prices | [Model catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties): inspect `supported_parameters` for `structured_outputs`; cache `pricing.prompt`/`pricing.completion` for estimates. Public catalog confirmed the selected DeepSeek model advertises structured outputs. |
| Provider routing | [Provider selection](https://openrouter.ai/docs/guides/routing/provider-selection): `provider.require_parameters=true` prevents silent parameter dropping. |
| Model fallback | [Model fallbacks](https://openrouter.ai/docs/guides/routing/model-fallbacks): verified the server-side ordered `models` array. Deliberately use explicit client-side primary → fallback requests instead, so capabilities can differ and invalid JSON can trigger fallback after repairs. Tests verify the switch; no live fallback model was configured. |
| Usage and cost | [Usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting): use prompt/completion tokens and reported `usage.cost`. Otherwise estimate from catalog token prices and mark estimated; unknown prices use a conservative $100/million-token estimate. Invalid-output attempts are included; internal retries stop if their accumulated token/cost limit is exceeded. |
| HTTP errors/backoff | [Errors and debugging](https://openrouter.ai/docs/api_reference/errors-and-debugging): 401/403 fail immediately without echoing the body; 402 reports insufficient credits. Retry 429/5xx with jitter and Retry-After; timeouts can select the fallback. SDK retries are disabled, preventing hidden retry multiplication. Cancellation interrupts requests and backoff. |
| Optional attribution | [API reference](https://openrouter.ai/docs/api_reference/overview): HTTP-Referer and X-OpenRouter-Title are optional; X-Title remains an accepted alias. These headers are omitted. |

No model IDs are embedded in implementation code. The user's selected primary model is configured in `.env.example` and the ignored local `.env`.

## Frontend and event compatibility

Frontend files and API route modules are unchanged from Task 3. The only event-model change is additive budget fields: `promptTokens`, `completionTokens`, `costUsd`, `maxCostUsd`, `costEstimated`. Existing envelope fields and event types remain unchanged. Turn order now matches Task 4: observation summary → proposed → executed → budget update. Type proposal values are redacted; extraction timeline summaries contain no page dump.

The mismatches identified in [discovery](discovery-report.md) and the [Task 2 PR](task-2-pr-description.md) still need Task 8 rewiring:

- `POST /api/runs` must send only goal/mode, without legacy startUrl/maxSteps/maxSeconds. Start URLs belong in the goal; limits are server configuration. HTTP 201 is already accepted by the frontend's res.ok check.
- Render `steps[].text`, ID-based `planStepId`, structured `rationale`, `target`/`value`, `resultSummary`, `tokensUsed` and `run.failed.data.error`; read nested `error.message` for request errors.
- Existing runs/events/stop endpoint URLs remain valid. Add SSE reconnection/cursor support and state/pause/resume integration later.
- Replace legacy preview.frame SSE handling with the future preview WebSocket. Preview/input sockets remain stubs; no streaming or real takeover is added here.

## Assumptions and practical limits

- No AGENTS.md exists in the repository or ancestors. Task 2 provided RunRecord/state-machine types but no serializable agent memory, so this task adds AgentState separately, without changing REST state shape.
- LLM_PROVIDER and BROWSER_DRIVER select components. USE_FAKES is retained as a legacy compatibility setting and no longer prevents real-provider startup.
- The single-step planner exception is reserved for unclear/unsafe goals; ordinary goals request 2–6 steps. Schema permits 1–6 and never passes webpage text to planning.
- The login smoke goal explicitly supplies fake local credentials; that is the only credential-use exception. No guessing, website-derived credentials, CAPTCHA solving, payment handling or real takeover is implemented.
- All type proposals and ordinary timeline feedback redact typed values. Final answers may contain values subsequently observed in public, non-redacted fields, allowing the requested search-result and demo-welcome answers. Known password/secret values always remain protected, even if also present in a public field. API keys and obvious token strings are defensively filtered.
- Page-derived labels and feedback remain inside the untrusted block. Older history uses short status lines; only the configured number of recent entries include detailed feedback. No old observations are resent. These prompts are a baseline rather than a complete injection/policy defense; AllowAllValidator remains the explicit placeholder.
- A pause prevents new runner calls/publication and freezes counters. In-flight operations may complete, but proposals from before pause are discarded after resume. Actions already completed are not replayed. Browser takeover/suspension is deferred.
- Cost is checked after returned usage, including between repair attempts. Estimates and cancelling a request cannot guarantee the provider will not bill unreported in-flight work. SDK output limits may include model reasoning; only validated action JSON is consumed, never reasoning fields.
- Fingerprints exclude fresh refs/generation so they detect actual unchanged element state. Different typed values do not count as identical actions. Loop errors list only action kinds and refs.
- Store/events/queues remain in memory and require one API worker. Preview, persistence, queue bounds, auth and real policies remain later work.
- Existing ignored environment secrets were neither printed nor committed. Only the chosen primary model ID was updated in the private environment.

## Verification

Environment: Python 3.14.4 (package requires 3.11+, mypy targets 3.11), OpenAI SDK 2.54.0, Playwright 1.64.0 / Chromium 156.0.8078.4. The display is available and the existing headed tests run normally.

| Command/check | Result |
|---|---|
| `pytest -q` from backend | **210 passed, 5 skipped** in 65.67s; one existing upstream Starlette TestClient/httpx deprecation warning. Paid cases skip even when a key exists unless explicitly selected. |
| `ruff check .` from backend | PASS. |
| `mypy .` from backend | PASS, strict mode, 60 source files. |
| Zed BasedPyright against `pyrightconfig.json` | **0 errors, 0 warnings**; 46 focused tests also passed after the final editor-typing fixes. |
| `git diff --exit-code 9a65fb6 -- 'front end' backend/app/api` | PASS: frontend and API route modules unchanged. |
| `git diff --check` | PASS. |
| Load private env into a child process, then `pytest -q -m live tests/test_live_smoke.py` | **5 passed in 193.06s**, primary **deepseek/deepseek-v4-flash**, no fallback configured. All five goals reached run.finished with matching expected values through the real API/SSE and headless Chromium. |
| `python scripts/serve_testsite.py --port 8766` | Static site started on an isolated verification port. |
| `LLM_PROVIDER=openrouter BROWSER_DRIVER=playwright .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001` | Real server started with the selected model and existing private key. |
| `curl -sS -H 'Content-Type: application/json' -d '{"goal":"Open http://127.0.0.1:8766/table.html and report the product with the lowest price, including its name and price.","mode":"headless"}' http://127.0.0.1:8001/api/runs` | HTTP **201**. |
| `curl -sS -N http://127.0.0.1:8001/api/runs/<runId>/events` | **19** contiguous events, four turns, ending in run.finished; result **Notebook at $5.00**. Reported run cost **$0.0006620432**. |
| `curl -sS -N -H 'Last-Event-ID: 3' http://127.0.0.1:8001/api/runs/<runId>/events` | Replayed exactly events 4–19. |

Stop tests cancel during model and browser operations within two seconds; real Chromium process audits check that owned children exit. Pause tests assert counters/events freeze and fresh observation precedes the resumed proposal. Mock HTTP covers structured and JSON-only output, invalid JSON repairs, per-model fallback, 429 Retry-After, 401/403, timeouts, cancellation, usage estimates and retry limits. Security tests cover hidden and visible injection boundaries, API-key filtering and final-result secret protection. All four budgets and both loop detectors terminate cleanly with counters.

Work is organized into the requested nine commits: config/usage; OpenRouter client; prompts; steps/runner; budgets/loops; controls; injection baseline; smoke tasks/live tests and their regression fixes; README/PR notes. No PR was published from this workspace.
