# Phase 1 verification

**Acceptance blocker remains: D7 — OpenRouter rejected the existing private credential/access.** All five live smoke tests failed before planning. No credential was changed or disclosed. Phase 1 is not fully accepted until successful live and human checks are recorded.

Audit date: 2026-10-21. Baseline `55c1a01`; initial report committed first as `c79467b`. Read root AGENTS.md, discovery report and current backend docs. Evidence below is from this audit; earlier Task 4/7 success claims are historical, not substituted for reruns. No existing test was deleted, skipped, loosened or weakened. New-test environment/configuration errors were corrected without changing their assertions.

## Environment and clean installation

| Fact | Observed value |
|---|---|
| OS | Linux 7.0.0-38-generic x86_64, glibc 2.43 |
| Python | 3.14.4 (project requires >=3.11; no other interpreter version tested here) |
| Playwright / Chromium | 1.64.0 / Google Chrome for Testing 156.0.8078.4, build 1248 |
| FastAPI / pydantic / settings | 0.156.4 / 2.14.1 / 2.16.1 |
| openai SDK / httpx / uvicorn | 2.54.0 / 0.28.1 / 0.54.0 |
| pytest / Ruff / mypy | 9.1.1 / 0.17.1 / 1.20.2 |
| Frontend Node / npm / Vite / Vitest | v22.22.1 / 9.2.0 / 6.4.3 / 4.1.12 |
| Display available | Yes; four headed tests actually ran |
| OPENROUTER_API_KEY available | Yes via ignored backend/.env; initially not exported; value never printed |
| Configured primary / fallback | deepseek/deepseek-v4-flash / none |
| Optional PinchTab | Installed 0.15.2; default operation does not require it |

Initial existing backend/.venv lacked pytest/Ruff executables. Do not install system python3-pydantic: a project virtualenv with pydantic v2 is required. Created a fresh environment at `/tmp/wto-phase1-verify-venv` using `python3 -m venv`, then from backend ran `pip install -e '.[dev]'` and `playwright install chromium` successfully. Existing installed browser files were reused; the browser command exited 0. Fresh resolution and pip check succeeded. `USE_FAKES` is an explicitly retained Task 2 compatibility setting; current driver/provider flags select implementations. BROWSER_HEADLESS is overridden by the required per-run mode. Neither is a retired Node setting.

Then exported tracked commit `3d74173` to `/tmp/wto-phase1-clean-xj4cv1s6` with git archive (no .env, dependencies or generated artifacts), and followed root README command 1 exactly:

```bash
python3 -m venv backend/.venv && backend/.venv/bin/pip install -e './backend[dev]' && backend/.venv/bin/playwright install chromium
```

It succeeded with a second fresh virtualenv. After the ACK fix, a third clean tracked checkout of `7eebd20` at `/tmp/wto-phase1-final-clean-h8vr8lss` repeated the same install successfully; final backend gates use that environment. Frontend files are identical to the second clean checkout (`git diff 3d74173 -- "front end"` is empty). Frontend command `npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache` installed 435 packages from the lockfile in both worktree and clean checkout. No lockfile/package-manifest changes. backend README's .env copy is now conditional and preserves existing private configuration.

The clean fake API served health=200. Frontend HTML and transformed JSX=200; proxied run creation=201 and SSE ended in run.finished. Existing port 5173 was occupied and left untouched; the controlled startup used `npm run dev -- --host 127.0.0.1 --port 5175` with FRONTEND_ORIGIN=http://localhost:5175. README says port 5173 must be free; strictPort prevents silent origin changes. Default-port startup with that occupied port cannot be claimed successful.

## Raw gate results — initial and final

Initial complete backend run (fresh environment, first fixes/new network test already applied; not a claim of testing an unmodified baseline):

```text
pytest -q -ra
307 passed, 11 skipped, 1 warning in 150.43s (0:02:30)
pytest -q -m headed -ra
4 passed, 314 deselected, 1 warning in 12.78s
ruff check .
All checks passed!
mypy . ../scripts
Success: no issues found in 95 source files
pip check
No broken requirements found.
```

Initial frontend `npm ci` → 435 packages in 57s; build → 1,816 modules, 3.85s; `npm test` → 3 files / 25 tests passed in 4.90s. After timeline fix: build 3.28s, 4 files / 26 tests passed in 6.02s. Final new checks bring the total to 28 tests. No frontend lint command/tool is configured in package.json; none is invented or claimed to have passed. Vite build and Vitest are its existing automated gates.

Final clean-checkout results, tracked code `7eebd20`, new virtualenv with no private .env:

```text
# backend/
pytest -q -ra
310 passed, 11 skipped, 1 warning in 155.32s (0:02:35)
pytest -q -m headed -ra
4 passed, 317 deselected, 1 warning in 12.46s
pytest -q tests/test_input_privacy.py tests/test_takeover_browser.py::test_headless_login_handoff
4 passed, 1 warning in 6.16s
PINCHTAB_URL=managed pytest -q -m pinchtab -ra
6 passed, 315 deselected, 1 warning in 20.09s
# root Ruff includes scripts and the backend; backend-only Ruff also passes
ruff check .
All checks passed!
# backend/ exact requested type gate
mypy .
Success: no issues found in 90 source files
# backend/ plus verification scripts
mypy . ../scripts
Success: no issues found in 95 source files
pip check
No broken requirements found.
# clean frontend/
npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache
added 435 packages in 5s
npm run build
1816 modules transformed; built in 2.70s
npm test
Test Files 6 passed (6)
Tests 28 passed (28)
Duration 6.74s
```

The sole warning is the upstream TestClient deprecation noted below, not a test failure. Frontend files are unchanged after this clean build/test run. The root check includes generated-directory exclusions already present in the repository; no test/lint rule was loosened. `git diff --check` passed. Live tests remain the separate actual failures below.

### Every observed intermediate failure / resolution

- Initial attempt to commit report hit read-only .git; rerun with authorized git permissions succeeded. Initial old-venv Ruff/pytest commands were absent; fresh documented install resolved this.
- First Ruff pass over the newly written network test found 7 errors (ASYNC110 polling loops and E501 long lines). Bounded for-loops and formatting fixed them; no assertion or timeout loosened.
- One frontend test invocation accidentally ran npm at repo root: ENOENT package.json. Correct frontend working directory passed; root intentionally has no Node manifest.
- New Vite-config test initially failed to load esbuild in jsdom (TextEncoder/Uint8Array realm invariant). Node-only build configuration is now tested in Node via the Vitest environment directive, with identical assertions (`25f17a1`).
- New command-panel test initially could not resolve the existing @ alias. Vitest now inherits Vite's actual resolve configuration (`12b1f08`); no mock or weakened assertion substituted.
- The first final-clean suite failed its unchanged animation/slow-viewer ACK assertion: received=47, acked=46; **1 failed, 308 passed, 11 skipped in 152.23s**. Cancelling the supervisor during detach had already cleared session ownership. `7eebd20` retains ownership until cleanup finishes and drains ACK tasks; a deterministic cancellation regression now covers it. Nine targeted CDP tests passed in 11.04s. The complete final suite is rerun below.
- Live OpenRouter gate failed all 5 cases (below). This remains open; offline passes do not replace it.
- Restricted socket/browser/network attempts required authorized sandbox escalation. Final network/browser executions used it successfully; no gate was skipped for that limitation.

### Skips investigated

Default suite: five live cases are deliberately opt-in to avoid billing (`pytest_collection_modifyitems` in tests/conftest.py); six optional PinchTab cases require PINCHTAB_URL. Both groups were explicitly executed in this audit. Live: 5 failed, not skipped. PinchTab: 6 passed, not skipped. No headed tests skipped because a display was available. Other platform-dependent /proc tests ran on Linux. The one warning is upstream Starlette's deprecation of httpx TestClient in favor of httpx2; HTTPX remains the required Phase 1 stack and current tests work. No new dependency or test bypass was added just to silence the warning.

## Full specification inventory

Counts: FAIL-FIXED=5, FAIL-OPEN=1, PASS=35, PASS-WITH-DEVIATION=4, UNVERIFIED=2; total=47. PASS-WITH-DEVIATION uses the user-authorized status and explains each difference.

| ID | Status | Evidence and fix commit |
|---|---|---|
| A1 | PASS | `docs/discovery-report.md:5` through its Verification section includes all six discovery parts, inventory decision table, calls to rewire and human decisions; read in this audit. |
| A2 | PASS-WITH-DEVIATION | Tracked-file and Express/Fastify/Nest searches found no Node backend. Browser-only `backend/app/browser/observe.js` and static `testsite/site.js` are required JS, not server code. Only `front end/` has package manifests/configs. |
| A3 | PASS | `backend/pyproject.toml:1` bounds every runtime/dev/build dependency; direct imports account for all packages. `scripts/audit_repo.py` confirms exact Settings/example parity. No Docker/CI backend remnants in tracked inventory; `pip check` passed. |
| A4 | FAIL-FIXED | Timeline fields fixed in `8271ce3`; stable dev Origin in `f483139`/`25f17a1`; ignored limit controls corrected in `12b1f08`. Frontend hook/config/command-panel regressions pass. Clean-checkout HTML/JSX and proxied POST/SSE probe passed; call map below. Frontend build/tests pass. |
| B1 | PASS | Fresh install resolved Python 3.14.4, FastAPI 0.156.4, pydantic 2.14.1, httpx 0.28.1 and official openai 2.54.0; pyproject requires Python >=3.11. Async route/runner paths exercised by offline suite. |
| B2 | PASS | `backend/tests/test_network_contract.py:19::test_real_server_routes_sse_keepalive_and_websockets` exercised all ten routes over real loopback sockets, header/query replay, authenticated JPEG/input and terminal closure. Measured keepalive 15.006 s. `backend/tests/test_api.py:85::test_validation_errors_and_404s`; `backend/tests/test_api.py:121::test_stop_is_fast_and_idempotent` |
| B3 | PASS | `backend/tests/test_state_events.py:51::test_event_union_and_action_validation`; `backend/tests/test_state_events.py:131::test_all_event_variants`; `backend/tests/test_store_emitter.py:48::test_replay_and_live_subscription_race_has_no_gaps`. Reserved variants exist but have no runner emit sites; strict models reject extra fields. No raw chain-of-thought data fields found. |
| B4 | PASS | `backend/tests/test_state_events.py:28::test_every_transition`; `backend/tests/test_state_events.py:70::test_transition_policy_is_explicit`; `backend/tests/test_runner.py:143::test_driver_failures_never_leave_active_run`; real server returned JSON 409 for invalid/terminal transitions. Explicit table: `backend/app/core/state.py:44`. |
| B5 | PASS | `backend/tests/test_architecture_contract.py:11::test_runner_has_no_concrete_fake_dependencies`; runner signature injects every interface, including optional PreviewChannel. Protocol definitions in interfaces/browser, llm, validator, skills and core/store, emitter; AllowAllValidator retains the Phase 2 TODO. |
| B6 | PASS | `backend/tests/test_architecture_contract.py:22::test_env_example_exactly_matches_settings` (47 fields); `backend/tests/test_api.py:247::test_openrouter_missing_config_is_rejected`; `backend/tests/test_api.py:161::test_cors`; `backend/tests/test_api.py:236::test_shutdown_stops_and_drains_tasks`; `backend/tests/test_api.py:85::test_validation_errors_and_404s`. Operational launcher variables (DISPLAY, test-site/spike overrides) are not app Settings. Environment validation/defaults use installed pydantic-settings. |
| C1 | PASS | `backend/tests/test_playwright_headed.py:18::test_headed_visible_smoke`; `backend/tests/test_playwright_headed.py:42::test_headed_scripted_form_runner`; `backend/tests/test_playwright_lifecycle.py:50::test_no_display_is_clear_and_does_not_launch`. Headless browser suite and all four explicit headed tests actually ran. |
| C2 | PASS | `backend/tests/test_playwright_lifecycle.py:14::test_isolated_contexts_and_idempotent_close`; `backend/tests/test_playwright_lifecycle.py:67::test_start_failure_after_launch_closes_browser`; `backend/tests/test_playwright_lifecycle.py:83::test_cancellation_during_start_is_clean`; `backend/tests/test_playwright_hooks.py:68::test_no_permissions_are_granted`. Three-run stress verifies independent same-origin cookies; context creation disables downloads (`backend/app/browser/playwright_driver.py:98–105`). |
| C3 | PASS | `backend/tests/test_browser_models.py:29::test_blocked_urls` includes file/chrome/javascript/data/ftp and malformed HTTP; `backend/tests/test_playwright_actions.py:182::test_blocked_action`. Only internal initialization about:blank is additionally allowed, as AGENTS.md permits. |
| C4 | PASS | `backend/tests/test_playwright_observe.py:21::test_observe_pages`; `backend/tests/test_playwright_observe.py:36::test_hidden_text_is_excluded`; `backend/tests/test_playwright_observe.py:45::test_password_and_secret_patterns`; `backend/tests/test_playwright_observe.py:62::test_caps_state_and_hidden_labels`; `backend/tests/test_browser_models.py:46::test_compact_prompt_and_config`. Generation/ref caps and hidden/secret filtering exercised in real Chromium. |
| C5 | PASS | All `test_playwright_actions.py` cases passed, including fill/select/contenteditable/key/scroll/extract/wait/done, stale/removed/hidden targets, sanitized errors and password summaries; `backend/tests/test_playwright_hooks.py:10::test_popup_switch_callback_and_fallback`; `backend/tests/test_playwright_hooks.py:38::test_alert_is_dismissed_without_dialog_text`. |
| C6 | PASS | `python scripts/check_no_leftover_processes.py` passed ten success/failure/stop/takeover-timeout runs plus three concurrent runs; checks owned PID/start identities before/after. `backend/tests/test_browser_process_cleanup.py:44::test_cancel_reaps_own_chromium_processes`. No claim about unrelated operator browser processes. |
| C7 | PASS | `backend/tests/test_playwright_hooks.py:51::test_new_page_and_pause_hooks`; `backend/tests/test_playwright_hooks.py:10::test_popup_switch_callback_and_fallback`; `PlaywrightDriver` exposes all six required hooks and preview/input use them. Native preview tests consume get_viewport/get_context. |
| C8 | PASS-WITH-DEVIATION | All eight named static pages exist; testsite fixture serves them and real tests visit them. URL/fetch/WebSocket grep found only the intentionally hostile literal https://example.org in injection-visible.html; it is page text, not a link/request. No external script/CDN/request code exists. `scripts/serve_testsite.py` is stdlib loopback HTTP. Actual standalone CLI `python scripts/serve_testsite.py --port 35503` returned HTTP 200 for all eight named pages and was shut down afterwards. |
| D1 | PASS | `backend/tests/test_api.py:247::test_openrouter_missing_config_is_rejected`; `backend/app/llm/openrouter_client.py:91` constructs AsyncOpenAI with configured key/base URL and request timeout. Application source contains no hardcoded real model names. Environment facts list configured names only. |
| D2 | PASS | All `test_openrouter.py` cases passed: structured/JSON-only fenced parsing, invalid retry, fallback, Retry-After, 401/403, timeout, cancellation, cumulative tokens and reported/estimated cost. Current OpenRouter docs and installed SDK signatures were checked; provider.require_parameters=true is documented. Fallback is client-side per-model retry, intentionally no models-list request parameter or attribution headers used. |
| D3 | PASS-WITH-DEVIATION | `backend/tests/test_prompts.py:8::test_page_only_in_random_user_block`; `backend/tests/test_prompts.py:29::test_delimiters_are_neutralized`; `backend/tests/test_prompts.py:37::test_history_limit_and_secrets`. MAX_HISTORY_STEPS_IN_PROMPT caps detailed history; older steps remain as one abbreviated line each, as Task 4 explicitly requested. This differs from a literal cap on all history lines; no old observations are resent. |
| D4 | PASS | `backend/tests/test_agent_loop.py:67::test_empty_done_reasked_once`; `backend/tests/test_agent_loop.py:94::test_stale_reobserves_and_three_fail`; `backend/tests/test_agent_loop.py:116::test_denied_action_not_executed_and_reproposed`; `backend/tests/test_agent_controls.py:60::test_pause_during_proposal_reobserves_before_next_proposal`. Runner plans before observe, closes browser/run LLM session in finally; application lifespan owns shared SDK closure. |
| D5 | PASS | `backend/tests/test_agent_loop.py:152::test_all_limits_report_final_counters`; `backend/tests/test_agent_loop.py:170::test_no_progress_with_different_actions`; `backend/tests/test_runner.py:131::test_loop_detection`; `backend/tests/test_prompts.py:8::test_page_only_in_random_user_block`. Four limits and both loop detectors exercised without network; final budget counters asserted. |
| D6 | PASS | `backend/tests/test_agent_controls.py:16::test_stop_during_inflight_io` measured 0.000714 s (blocking fake LLM) and 0.000719 s (fake browser). `backend/tests/test_agent_security.py:95::test_stop_mid_io_reaps_real_browser` requires real Chromium closure within 2 s in both stages. SDK transport cancellation separately tested; real-provider cancellation cannot be exercised with the rejected credential. Additional real-Chromium timing probe: 0.083766 s during blocking LLM work and 0.074118 s during browser action, both including stop cleanup. |
| D7 | FAIL-OPEN | BLOCKER: all five explicitly opted-in live smoke tests actually failed with "OpenRouter: invalid API key or no access." Each recorded steps=0, tokensUsed=0, costUsd=0.0 before planning; this is not a claim about account billing. `docs/smoke-tasks.md` contains five goals/expected outcomes/curl commands. Private credential/account access must be repaired externally and live tests rerun; no source/test weakening can fix authentication. |
| D8 | PASS | `backend/tests/test_agent_security.py:23::test_scripted_browser_injection_boundary` passed against real local injection-visible.html and hidden-text.html; request-body assertions locate hostile content only inside the randomized user-message block. |
| E1 | FAIL-FIXED | Shutdown ACK ownership race fixed in `7eebd20`; deterministic interrupted-detach regression and all nine CDP tests passed.  `backend/tests/test_preview_cdp.py:28::test_every_received_frame_acked_even_when_throttled`; `backend/tests/test_preview_cdp.py:59::test_native_pixels_and_full_viewport`. Installed Chromium protocol schema confirms start/ACK/frame fields. Base64 decode + header dimension inspection only; no server resize/re-encode. Detached targets may reject ACK attempts and trigger recovery. |
| E2 | PASS | `test_preview_ws.py` auth/Origin/run-bound token/heartbeat cases and real-server authenticated JPEG probe passed. Framing roundtrip/edge tests in `test_preview_hub.py` passed. Tokens travel only in first-message auth; unknown run=4404, bad/late auth=4401, bad Origin=4403. |
| E3 | PASS | `backend/tests/test_preview_hub.py:39::test_latest_wins_multiple_viewers_and_cleanup`; `backend/tests/test_preview_cdp.py:220::test_animation_throttle_and_nonreading_viewer_do_not_block_browser`. Per-viewer queues remain bounded and old frames are discarded. |
| E4 | FAIL-FIXED | `7eebd20` preserves cleanup ownership if the supervisor is cancelled during detach; final ACKs drain before session detach.  `backend/tests/test_preview_cdp.py:98::test_navigation_popup_and_forced_detach_recover`; `backend/tests/test_preview_cdp.py:137::test_fallback_and_periodic_screencast_retry`; `backend/tests/test_preview_cdp.py:174::test_static_idle_resends_without_stall`; `backend/tests/test_preview_cdp.py:195::test_no_first_frame_switches_to_fallback`; `backend/tests/test_preview_hub.py:55::test_idle_resend_stall_and_retention`; `backend/tests/test_preview_hub.py:104::test_run_retention_starts_after_resource_cleanup`. |
| E5 | PASS | `backend/tests/test_preview_ws.py:114::test_preview_lifecycle_privacy_and_shutdown`; `backend/tests/test_preview_hub.py:74::test_transport_debug_payloads_are_filtered`. RAM-only frame paths inspected; privacy assertions inspect logs/events/store. No verification frames written to disk. |
| E6 | PASS | Frontend protocol/sizing and LivePreview component tests passed at DSF 1/2, with native canvas dimensions, max scale 1, latest-only RAF and overlays/debug fields. `frameSizing` caps CSS size and LivePreview draws at native internal width/height. `backend/tests/test_preview_fake.py:13::test_fake_pattern_changes_and_lifecycle` proves fake preview. Old stretched image branch replaced by canvas in earlier tasks; no remaining preview upscaling CSS found. |
| E7 | UNVERIFIED | Subjective text sharpness/readability at 100% requires a person. Native-pixel and sizing tests are objective evidence only, not subjective sign-off. Exact DSF 1/2 comparison steps below. |
| F1 | PASS | `test_input_auth.py` valid/wrong/missing/timeout/Origin/controller cases passed; real network probe verified separate tokens, input auth/state/pong. Token URLs/logging review below; no URL tokens. |
| F2 | PASS | `backend/tests/test_input_auth.py:44::test_single_controller_and_nonaccepting_and_disconnect`; `ControlSession.accepting` checks owner, readiness, paused status and takeover/handoff reason before relay. |
| F3 | PASS | `test_input_protocol.py` validation/rate/size cases and `backend/tests/test_input_auth.py:79::test_rate_limited_input_and_oversize_rejects` passed. Unknown/malformed/oversize rejection and close after 50 are asserted; fake relay and frontend mapping tests verify viewport-relative clamps. |
| F4 | PASS | Installed Chromium /json/protocol 1.3 confirmed dispatchMouseEvent/dispatchKeyEvent/insertText fields and modifier bits Alt=1 Ctrl=2 Meta=4 Shift=8. All `test_input_relay.py` exact-call tests passed; real browser Enter/Tab/Backspace/login tests passed. No DOM/clipboard read in relay. |
| F5 | PASS | All `test_takeover_state.py` and `test_takeover_browser.py` cases passed: cancellation/quiescence, fresh observe, handoff cap, deadlines, stop, popup and disconnect. `takeover` waits at most 1.8 s for active work. Handoff resets repetition tracking; no browser/LLM work while paused. |
| F6 | PASS | `backend/tests/test_input_privacy.py:91::test_websocket_canary_never_reaches_public_channels`; `backend/tests/test_input_privacy.py:30::test_fingerprint_split_typing_and_no_plaintext_history`; real headless/headed login canary assertions passed at DSF 1/2. Canary includes all-level logs, SSE/store, LLM request bodies, sanitized relay exception and password observations; final separate rerun recorded below. |
| F7 | PASS | Frontend `input.test.js`, LivePreview component and hook tests passed. `useInputControl.js` attaches only canvas/editor listeners while controlling; clears hidden editor after sends, sends IME/paste as text, normalizes wheel, does not store text in React state/logs/storage. `mapPointer` uses actual content rect + metadata viewport and clamps. Browser shortcuts are exempt; Tab intentionally also allows leaving the preview (focus is not trapped). |
| F8 | UNVERIFIED | Automated headed/headless login, DSF 1/2 and mapping tests ran; no person performed real typing/click-accuracy/resized-preview verification. Exact manual steps below; display availability alone is not human sign-off. |
| G1 | PASS | Standalone spike rerun: PinchTab 0.15.2, all eight checks PASS, OVERALL PASS; recommendation OPTIONAL. New measurements and exact command below. Existing `docs/pinchtab-spike.md` contains versioned release docs, security choices and earlier measurement samples. |
| G2 | PASS | Six opt-in PinchTab integration tests passed (five smoke goals + canary/stale/pause/outage), plus nine unit cases. `pinchtab_api.py` centralizes endpoints; factory defaults AGENT_DRIVER=playwright; visibility/redaction reconciliation ignores raw values and caps output. Default complete suite/clean fake startup ran without a PinchTab service. |
| G3 | FAIL-FIXED | Atomic admission and JSON 429 added in `9271f2b`, covered by `backend/tests/test_api.py:301::test_concurrent_admission_is_atomic_and_slots_are_released`. Leak script passed ten mixed real-browser runs and three simultaneous runs with isolated events/frames/cookies. Finite RSS sample reported below; historical metadata remains until restart. |
| G4 | PASS | `scripts/audit_repo.py` and separate git log -p pattern scan found no credentials; .env ignored/untracked, 47 settings match example. All application log sites and loopback paths reviewed with file/line below. Fresh pip check passed; dependency/import inventory and Node-backend search found no dead runtime dependencies. |
| G5 | PASS-WITH-DEVIATION | Docker is optional and absent; no Docker/Compose files or exposed PinchTab services were introduced. Local installation and startup verified without Docker. Container-specific checks are therefore not applicable, not claimed as executed. |
| G6 | FAIL-FIXED | Missing top-level README, acceptance checklist and Phase 2 notes completed in `3d74173`; backend README preserves .env, documents all settings/protocols/limitations and corrected timeline fields. Fresh tracked checkout install/build/tests and real startup/proxy probe executed. Port 5173 was occupied; explicit 5175 frontend override preserved the unrelated process. Human/live limitations remain explicit. |

## Real network outputs and cancellation

Command: from backend, `pytest -q -s tests/test_network_contract.py tests/test_agent_controls.py::test_stop_during_inflight_io` → **3 passed in 17.28s**. Actual safe summary:

```json
{"create":201,"events":200,"get":200,"health":200,"input":"authenticated state + pong","invalid":422,"keepaliveSeconds":15.006,"preview":"authenticated JPEG","repeatStop":200,"replay":"header and query","resume":200,"stop":200,"stopPausedSeconds":0.0659,"takeover":200,"terminal":"run.finished","terminalConflict":409,"unknown":404}
```

```text
STOP_TIMING stage=llm seconds=0.000714
STOP_TIMING stage=browser seconds=0.000719
```

Those precise timings use cancellable fakes. An additional in-process timing wrapper ran the existing real-Chromium tests without changing their assertions: **2 passed in 4.26s**, LLM-blocking stage stop+browser cleanup **0.083766 s**, browser-action stage **0.074118 s**. The tests verify owned processes exit, and SDK transport cancellation is tested independently. They do not prove cancellation against an authenticated remote provider when the current credential is rejected.

## Frontend network call map

| Frontend call | Backend handler / contract |
|---|---|
| hooks/useTaskOrchestrator.js:213 POST /api/runs | api/runs.py::create_run; sends goal/mode only; response runId/previewToken/controlToken |
| hook:165 and :237 POST /api/runs/{id}/stop | api/runs.py::stop_run; normal Stop and late-creation race recovery |
| hook:243 GET /api/runs/{id}/events | api/runs.py::events; streamed fetch SSE; Python event fields now consumed |
| hook:381 POST /api/runs/{id}/takeover or /resume | corresponding REST handlers; method POST, no extra body |
| preview/LivePreview.jsx:85 WS /api/runs/{id}/preview | api/preview.py::preview; first-message previewToken, binary frames/status |
| preview/useInputControl.js:14 WS /api/runs/{id}/input | api/ws.py::input_socket; first-message controlToken, private validated input |

WebSocket URL helper includes only encoded runId and scheme; tokens never enter URLs. Vite /api proxy has ws=true. No frontend polling, screenshot HTTP call or SSE preview.frame remains. GET run-state and /health are available and network-tested; the frontend does not currently call them. External font requests are assets, not backend API calls. UI parameter inputs now explicitly say Server configured because the fixed request contract has no per-run limit fields.

## Live smoke results (actual failures)

Explicit command: `pytest -q -s -m live -ra` with existing Settings key/model copied into process environment in memory only. Result: **5 failed, 315 deselected, 1 warning in 13.50s**. Error for every task: **OpenRouter: invalid API key or no access.** No raw response, key, prompt or page text is included here.

| Task | Result | Steps | Recorded tokens | Recorded cost USD | Estimated |
|---|---|---:|---:|---:|---|
| search | FAIL before planning | 0 | 0 | 0.0 | false |
| form | FAIL before planning | 0 | 0 | 0.0 | false |
| table | FAIL before planning | 0 | 0 | 0.0 | false |
| load-more | FAIL before planning | 0 | 0 | 0.0 | false |
| login | FAIL before planning | 0 | 0 | 0.0 | false |

These are backend counters, not proof of account billing. Fallback is not configured; fallback behavior is covered by mocked HTTP tests. Successful live results, actual live step counts and provider cancellation remain unverified until access is restored.

## PinchTab rerun and stress evidence

`PINCHTAB_URL=managed pytest -q -m pinchtab -ra` → **6 passed, 314 deselected, 1 warning in 20.10s**. The managed sentinel is test-only. `python scripts/spike_pinchtab_attach.py` → **OVERALL PASS**, all 8 checks passed, installed/reported version 0.15.2. Anonymous /instances=401, authenticated=200; attach=201; ref actions=200; same target/form change verified through Playwright; preview and CDP input coexist; popup mapping changes; stale ref returns HTTP 500 with keys code/error/retryable; owned children absent after cleanup. Only attach was enabled temporarily; token in memory, local-only config/state removed afterwards. Recommendation remains **OPTIONAL**.

| Page | Pinch chars / estimated tokens / latency ms | Playwright chars / estimated tokens / latency ms |
|---|---|---|
| index.html | 279 / 70 / 22.04 | 407 / 102 / 17.26 |
| form.html | 415 / 104 / 32.65 | 531 / 133 / 28.12 |
| table.html | 735 / 184 / 33.74 | 450 / 113 / 26.13 |

Two fills/click latency: 7.82 / 7.55 / 12.11 ms. Single samples, tokens=ceil(chars/4), not a universal performance claim. Size savings are mixed; additional DOM reconciliation costs remain.

First leak rerun actual output:

```text
PASS short run 1: finished; RSS MiB=56.97
PASS short run 2: failed; RSS MiB=57.55
PASS short run 3: stopped; RSS MiB=57.99
PASS short run 4: timeout; RSS MiB=58.36
PASS short run 5: finished; RSS MiB=58.79
PASS short run 6: failed; RSS MiB=59.14
PASS short run 7: stopped; RSS MiB=59.52
PASS short run 8: timeout; RSS MiB=59.88
PASS short run 9: finished; RSS MiB=60.28
PASS short run 10: finished; RSS MiB=60.68
PASS three concurrent runs: isolated events, native frame colors and cookies
RSS MiB start=51.75 end=74.0 delta=22.25
PASS: 10 lifecycle runs, 3 concurrent runs, no owned Chromium/PinchTab processes
```

Final clean-checkout rerun (after the ACK fix), same command from root:

```text
PASS short run 1: finished; RSS MiB=56.82
PASS short run 2: failed; RSS MiB=57.37
PASS short run 3: stopped; RSS MiB=57.78
PASS short run 4: timeout; RSS MiB=58.19
PASS short run 5: finished; RSS MiB=58.66
PASS short run 6: failed; RSS MiB=59.03
PASS short run 7: stopped; RSS MiB=59.4
PASS short run 8: timeout; RSS MiB=59.78
PASS short run 9: finished; RSS MiB=60.2
PASS short run 10: finished; RSS MiB=60.57
PASS three concurrent runs: isolated events, native frame colors and cookies
RSS MiB start=51.77 end=73.77 delta=22.0
PASS: 10 lifecycle runs, 3 concurrent runs, no owned Chromium/PinchTab processes
```

The final canary rerun above passed all four tests, including both headless DSF variants. The RSS assertion is a finite ten-plus-three sample with explicit thresholds, not proof of bounded memory over unlimited run history. Run records/event history remain process-resident until restart; frame queues/retention and owned browser processes are bounded/cleaned.

## Library API verification

Checked current official documentation and the installed bindings/schema rather than guessing APIs:

- [Playwright Browser](https://playwright.dev/python/docs/api/class-browser), [BrowserContext/CDP](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-new-cdp-session): inspected 1.64.0 installed signatures/docstrings for launch, new_context, new_cdp_session, evaluate, fill, select_option and CDPSession.send. Real browser tests execute them. No page.accessibility API used.
- [CDP Page](https://chromedevtools.github.io/devtools-protocol/tot/Page/) and [Input](https://chromedevtools.github.io/devtools-protocol/tot/Input/): additionally fetched the actual installed Chromium 156 /json/protocol schema through a temporary loopback-only debugging port, then closed the browser. Protocol version 1.3: startScreencast format/quality/maxWidth/maxHeight/everyNthFrame; frame data/metadata/sessionId; ACK sessionId; metadata offsetTop/pageScaleFactor/deviceWidth/deviceHeight/scrollOffsetX/Y/timestamp. Verified dispatchMouseEvent and dispatchKeyEvent field names and modifier bits, insertText text, and Emulation.setDeviceMetricsOverride viewport. Extra protocol options were not enabled merely because present.
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs), [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection), [API reference](https://openrouter.ai/docs/api_reference/overview): response_format json_schema, strict schema, supported_parameters capability check, provider.require_parameters, usage.cost and models-list fallback semantics verified. Code uses explicit client-side fallback to re-check each model's capabilities; no models-list request parameter or optional attribution headers are used. MockTransport tests verify request bodies and retry/error/cancellation behavior.
- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/) and [pydantic discriminated unions](https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions): inspected installed FastAPI 0.156.4 lifespan signature and pydantic 2.14.1 TypeAdapter/Field APIs, exercised through state/event/API suites. Current upstream httpx TestClient deprecation is recorded, not suppressed.
- PinchTab exact 0.15.2 installed README/help and version-tagged docs/source are recorded in docs/pinchtab-spike.md; optional integration rerun verifies those paths against the installed server.

## Security review with source evidence

- `backend/app/core/state.py:166`: Transition logging: constant message, status and runId only.
- `backend/app/agent/runner.py:419`: Agent failure logging: runId and exception class, no exception text.
- `backend/app/agent/runner.py:443`: Browser cleanup logging: constant message, runId and exception class.
- `backend/app/agent/runner.py:454`: LLM cleanup logging: constant message, runId and exception class.
- `backend/app/main.py:127`: Request failures: runId and class only; safe JSON response.
- `backend/app/browser/pinchtab_api.py:120`: Optional version warning: numeric semver only and runId; never raw server payload.
- `backend/app/logging.py:14`: Transport payload/debug filters prevent WebSocket frame/key diagnostics.
- `backend/app/api/preview.py:43`: Preview exact Origin check; constant-time first-message token auth follows.
- `backend/app/api/ws.py:31`: Input exact Origin check; separate constant-time control token auth follows.
- `front end/src/preview/protocol.js:25`: WebSocket URL includes runId, never auth tokens.
- `backend/app/browser/safety.py:13`: Scheme validation before navigation; only internal blank exception.
- `backend/app/browser/pinchtab_driver.py:61`: Optional debug port bound explicitly to loopback.
- `backend/app/browser/pinchtab_api.py:19`: Optional server and attached bridge URL constrained to literal-loopback origin.
- `backend/pyproject.toml:10`: Every dependency upper-bounded or pinned; setuptools bounded separately.

Application logging sites above were all reviewed; library log-level/filter setup does not log payloads. Frontend grep found no console/storage/analytics use in private input paths; only unrelated local run-history storage remains. No secrets printed from .env or written into any report. `python scripts/audit_repo.py` scans reachable history blobs and distributable files, including exact private-key matches in memory; separate `git log -p --no-ext-diff HEAD` pattern scan returned no finding paths. Final pre-report-commit scanner output (HEAD includes every code fix, and the working-file scan includes these final reports):

```json
{"history_blobs_scanned":400,"working_files_scanned":173,"credential_findings":[],"local_env_ignored":true,"tracked_env_files":[],"settings_count":47,"example_missing":[],"example_extra":[]}
```

Separate `git log -p` credential-pattern finding paths: `[]`. Tracked package/config inventory contains only front end/package.json and package-lock.json; outside frontend only browser observe.js and static site.js exist; Node server import findings `[]`; Docker/CI config inventory `[]`. No Docker config exists. Browser-only JS is not a Node server. Installed external tools/ignored venv libraries are not repo backend source.

## Fixed during this audit

| Commit | Fix and regression evidence |
|---|---|
| 9271f2b | Atomic MAX_CONCURRENT_RUNS admission, default 3, JSON 429; four-racing-requests/slot-reuse test. |
| 8271ce3 | Frontend plan/rationale/resultSummary/tokensUsed mappings; real Python-shaped SSE hook test. |
| 1e57b37 | Real-socket route/SSE/WS proof, no-fakes-import and env-parity guards, safe stop/live counters. |
| f483139 + 25f17a1 | Strict frontend port prevents silent WS Origin mismatch; Vite config test uses Node environment. |
| 12b1f08 | Unsupported UI limit overrides explicitly server-managed; command-panel regression; Vitest shares app alias. |
| 7eebd20 | Preview shutdown retains a cancelling supervisor's live CDP session and drains all frame ACKs before detach; deterministic regression. |
| 3d74173 | Missing local README/acceptance/Phase 2 notes; safe .env setup, complete optional config/limits and stale contract docs. |

No public route, event shape/name or action schema changed. New capacity rejection and MAX_CONCURRENT_RUNS are documented Phase 1 hardening. UI design/styling unchanged apart from truthful read-only budget controls.

## Still open

- **BLOCKER — D7:** existing OpenRouter credential/access rejected. Proposed remedy: operator updates only private backend/.env OPENROUTER_API_KEY or restores account/model access; export key/model privately and rerun all five live smoke cases. Do not put a key in chat, source, logs or a report. Keep this blocker until real expected results are verified.
- No other known Phase 1 implementation blocker remains. Upstream TestClient warning and absent optional Docker/frontend lint command are disclosed above, not test failures.

## UNVERIFIED: human must check

1. **Live acceptance/account access:** configure a valid private key and model. From backend activate .venv and privately export OPENROUTER_API_KEY/LLM_MODEL_PRIMARY; run `pytest -q -s -m live`. Record the five per-task statuses, steps, costUsd/costEstimated and compare with account activity. Do not paste credentials into commands that will be shared. Run server in real mode only after access works.
2. **E7 sharpness:** free port 5173; run API with BROWSER_DRIVER=playwright, LLM_PROVIDER=openrouter and DEVICE_SCALE_FACTOR=1, and npm run dev. Serve the local test site. Open localhost:5173/?debug=1 at browser zoom 100%; request form.html and compare its preview text with a normal Chrome window showing the same page. Confirm canvas internal pixels=frame pixels and CSS <= frame/DSF; repeat DSF=2, restarting API, then resize larger/smaller and verify letterboxing/no enlargement. Do not save frames containing personal data.
3. **F8 tactile control:** repeat in headless then headed, each at DSF 1/2. Goal: open login.html and ask the human to sign in. Enter takeover, click username/password, type the published fake demo credentials, submit, Resume. Confirm fresh observation and completion. Resize/letterbox and verify click locations; check double/right-click, wheel, Tab focus escape to Resume, paste and IME. A person must actually perform these steps; automated headed tests are insufficient sign-off.
4. **Cost/provider cancellation:** after valid access, compare successful smoke usage with OpenRouter billing and stop a long in-flight real-provider run, measuring stop-to-cleanup time. Mock SDK cancellation and local browser tests passed, but remote credential failure prevents this live check.

## Out of scope (Phase 2+)

Policy tiers, approval dialogs, domain/private-network allowlists/SSRF enforcement, injection classifier, skill library, accounts and database are intentionally not implemented. Richer retention/shared-store/multi-worker scheduling and production multi-tenant guarantees need Phase 2 design. Current phase permits localhost test sites and AllowAllValidator/EmptySkillProvider stubs; those omissions are not Phase 1 failures. See phase2-notes.md for integration points.
