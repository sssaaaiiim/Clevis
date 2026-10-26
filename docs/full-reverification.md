# Full Phase 1 and Phase 2 re-verification

**Quality gates pass. RELEASE BLOCKER: one historical credential-shaped blob remains; provider revocation is unverified. The security scan exits 1. No zero-findings security acceptance is claimed.**

Started 2026-10-25T22:51:15.720015+05:00; finalized 2026-10-26 (Asia/Karachi); baseline `2c890601eab3de4cdee1f5e788e00accfd01852f`. Report-first commit `b1b47ae`. This report uses new executions and directly inspected code, not previous audit results. Implementation/security-test fix commits: 0546bf9 and 340d849; documentation correction: 050f1a4. No existing test was weakened, skipped, removed or edited. No application route, event field name or action schema changed.

## Environment baseline and installation

- OS: Linux-7.0.0-38-generic-x86_64-with-glibc2.43; Python 3.14.4; Node v22.22.1; npm 9.2.0.
- Existing backend/.venv: LangGraph 1.2.17, Playwright 1.64.0, FastAPI 0.156.4, pydantic 2.14.1.
- Fresh /tmp/reverify-venv: langgraph 1.2.17, playwright 1.64.0, fastapi 0.162.0, pydantic 2.14.1, openai 2.54.0. Chromium 156.0.8078.4.
- LANGGRAPH_TESTED_VERSION=1.2.17; matches installed metadata and successful fresh pip show langgraph.
- Display available: yes; four actual display-backed tests ran. Human visual checks remain unverified.
- AGENTS.md at root: yes; Phase 1 and Phase 2 sections read before work.
- OPENROUTER_API_KEY in backend/.env: yes (presence only). No key or token value printed/committed.
- Configured primary/fallback model names: deepseek/deepseek-v4.1-flash / deepseek/deepseek-v4.1-flash. Outcome model unset, inherits primary.
- Fresh documented install succeeded: from backend, python3 -m venv /tmp/reverify-venv; /tmp/reverify-venv/bin/pip install -e '.[dev]'; /tmp/reverify-venv/bin/playwright install chromium. No install-instruction fix needed. Fresh pip check passes. Temporary venv path preserves the operator environment.
- Exact normal-port README startup probe: UNVERIFIED because port 8000 is already occupied; operator service untouched. Frontend/real HTTP/browser tests independently launch isolated servers. This is not claimed as a successful execution of all three README startup commands.
- Paid-model billing opt-in remains withheld under the earlier explicit user restriction. Configured key presence does not trigger paid tests. No live smoke/eval or OpenRouter completion call was made.

## Gate results

All backend commands run from backend except root scripts/install paths. Frontend commands run from `front end/`. Each exit below is the individual command result; orchestration continued after known audit failures. The initial full suite collected 545 passing cases before the new real HTTP regression was added. The final full suite includes that extra case.

| Gate | Command | Result | Exit code |
|---|---|---|---:|
| Initial fresh venv | `python3 -m venv /tmp/reverify-venv` | Completed successfully. | 0 |
| Initial fresh install | `/tmp/reverify-venv/bin/pip install -e '.[dev]'` | Completed successfully. | 0 |
| Initial fresh chromium | `/tmp/reverify-venv/bin/playwright install chromium` | Completed successfully. | 0 |
| Initial fresh full | `/tmp/reverify-venv/bin/pytest -q -ra` | 545 passed, 25 skipped in 231.86s (0:03:51) | 0 |
| Initial fresh headed | `/tmp/reverify-venv/bin/pytest -q -m headed -ra` | 4 passed, 567 deselected in 9.77s | 0 |
| Initial fresh eval | `/tmp/reverify-venv/bin/pytest tests/eval/ -q -ra` | 24 passed, 5 skipped in 49.73s | 0 |
| Initial fresh pinchtab | `env PINCHTAB_URL=managed /tmp/reverify-venv/bin/pytest -q -m pinchtab -ra` | 15 passed, 556 deselected in 36.55s | 0 |
| Initial fresh ruff | `/tmp/reverify-venv/bin/ruff check .` | All checks passed! | 0 |
| Initial fresh mypy | `/tmp/reverify-venv/bin/mypy .` | Success: no issues found in 162 source files | 0 |
| Initial fresh pip | `/tmp/reverify-venv/bin/pip check` | No broken requirements found. | 0 |
| Initial fresh privacy | `/tmp/reverify-venv/bin/pytest -k 'canary or privacy or log' -v -ra` | ================ 20 passed, 5 skipped, 546 deselected in 22.84s ================ | 0 |
| Initial fresh network | `/tmp/reverify-venv/bin/pytest -q -s tests/test_network_contract.py tests/test_agent_controls.py::test_stop_during_inflight_io` | 3 passed in 16.95s | 0 |
| Initial fresh spike | `/tmp/reverify-venv/bin/python scripts/spike_pinchtab_attach.py` | PASS 8: owned browser/PinchTab processes cleaned up; OVERALL PASS | 0 |
| Final leaks | `/tmp/reverify-venv/bin/python scripts/check_no_leftover_processes.py` | 10 mixed lifecycle + 3 concurrent runs PASS; zero owned Chromium/PinchTab survivors; RSS 94.08→126.21 MiB (delta 32.13). External managed server cleaned up. | 0 |
| Final full | `/tmp/reverify-venv/bin/pytest -q -ra` | 546 passed, 25 skipped in 224.93s (0:03:44) | 0 |
| Final ruff | `/tmp/reverify-venv/bin/ruff check .` | All checks passed! | 0 |
| Final mypy | `/tmp/reverify-venv/bin/mypy .` | Success: no issues found in 162 source files | 0 |
| Final pip | `/tmp/reverify-venv/bin/pip check` | No broken requirements found. | 0 |
| Real approval HTTP | `.venv/bin/pytest -q -s tests/test_reverification_http.py` | 1 passed in 12.46s; numeric status matrix below. | 0 |
| Frontend initial install | `npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache` | added 435 packages in 4s | 0 |
| Frontend initial build | `npm run build` | ✓ built in 2.40s | 0 |
| Frontend initial tests | `npm test` | 12 files / 57 tests passed ; 13.12s | 0 |
| Dependency audit before fix | `npm audit --audit-level=high --json` | 7 advisories: 6 high, 1 moderate, 0 critical | 1 |
| Compatible audit fix | `npm audit fix --no-audit --no-fund --cache /tmp/wto-npm-cache` | changed 11 packages; no --force; manifest ranges unchanged | 0 |
| Dependency audit after fix | `npm audit --audit-level=high --json` | 0 vulnerabilities at every severity | 0 |
| Frontend final clean install | `npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache` | added 435 packages in 6s | 0 |
| Frontend final build | `npm run build` | ✓ built in 2.42s | 0 |
| Frontend final tests | `npm test` | 12 files / 57 tests passed ; 14.33s | 0 |
| Secrets/env parity | `python scripts/audit_repo.py` | 1 historical finding; 0 working-tree findings; 761 history blobs/279 working files ; 62 settings ; 0 missing/extra | 1 |
| Continuation security recheck | `backend/.venv/bin/python scripts/audit_repo.py` | 762 history blobs / 279 working files; one historical finding, zero working-tree findings; env parity unchanged | 1 |
| Requested version attribute | `python -c "import langgraph; print(langgraph.__version__)"` | AttributeError: module 'langgraph' has no attribute '__version__' | 1 |
| Supported version lookup | `pip show langgraph` plus Python `importlib.metadata.version("langgraph")` | 1.2.17 for both; constant 1.2.17 | 0 |

All full-suite 25 skips are intentional existing opt-ins: 5 live_eval billing, 5 live billing and 15
PinchTab service cases. The 15 PinchTab cases were then run successfully against a disposable
local server via PINCHTAB_URL=managed; no operator token/service was reused. The standalone eval
has 5 paid-case skips; its 24 passes comprise 23 scenarios and one recorder privacy test. The privacy
selector skips one live_eval, one live and three PinchTab cases; the latter pass in the managed gate.
Marker/-k deselections are not disabled tests. No headed skip occurred. No new skip/xfail marker
was added. Initial and final full backend suites both passed; the new regression expands coverage.
These commands ran before the environment continuation on 26 October. Temporary /tmp logs and
venvs were discarded by that continuation; the actual summary lines were captured before it.
The documentation-only correction after continuation does not change the checked application/test code.

The leak script was a separate subprocess of a wrapper that owns an authenticated temporary
PinchTab 0.15.2 server. The checker sees that server as external, matching normal separate-terminal
operation; the wrapper also verifies server cleanup afterward. The run printed zero owned survivors.
RSS is finite-workload evidence, not a proof of unbounded memory stability.

## API/library verification

- Installed LangGraph 1.2.17 imports verified before calls: langgraph.types.interrupt and Command,
  langgraph.checkpoint.memory.MemorySaver, langgraph.graph.StateGraph/START/END. Inspected interrupt
  and Command signatures, MemorySaver.adelete_thread and graph state APIs. Runtime checkpointer
  identity and pydantic JSON roundtrip both true. The missing __version__ attribute is a package
  convention, not a reason to alter third-party code. [Official interrupt/resume docs](https://docs.langchain.com/oss/python/langgraph/interrupts).
- Installed Playwright 1.64.0 generated async API was inspected for 107 matching method signatures
  used by app call names. Strict mypy and real browser tests check concrete calls. Chromium 156.0.8078.4
  was launched temporarily with a loopback-only debugging port; its own /json/protocol schema
  confirmed all 13 literal CDP commands found in backend/app, their parameters and screencast event
  fields. The probe browser closed in finally. [Playwright CDPSession docs](https://playwright.dev/python/docs/api/class-cdpsession),
  [official Input protocol](https://chromedevtools.github.io/devtools-protocol/tot/Input/).
- Confirmed Page.startScreencast format/quality/maxWidth/maxHeight/everyNthFrame; frame event
  data/metadata/sessionId; Page.screencastFrameAck.sessionId; Page.stopScreencast/getLayoutMetrics/
  stopLoading; Emulation.setDeviceMetricsOverride including viewport; Fetch enable/failRequest/
  continueResponse; Target.getTargetInfo; Input mouse/key/insertText fields. Actual metadata includes
  deviceWidth/deviceHeight/pageScaleFactor/scrollOffsetX/Y/offsetTop/timestamp; image header provides
  actual frame pixel dimensions. Mouse/key mappings are also exercised by exact fake-CDP and real
  browser tests. No new CDP method is introduced by this audit.
- Installed OpenAI 2.54.0 AsyncOpenAI constructor, models.list and chat.completions.create signatures
  inspected. [Current structured-output docs](https://openrouter.ai/docs/guides/features/structured-outputs)
  and [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection) confirm response_format
  JSON schema and provider.require_parameters. [Model catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties)
  supports capability/pricing lookup; [usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)
  documents automatic usage/cost fields. Unknown model capability uses JSON-only parsing;
  fallback is a client-controlled model retry, not an unverified models-list request parameter.
  All transport behavior was checked with mocked HTTP; actual provider/model reliability remains UNVERIFIED.

## Real HTTP evidence and frontend contract mapping

Fresh loopback uvicorn tests made real HTTP/WebSocket requests. Safe numeric summaries:

- Health 200, create 201, get 200, events 200, resume 200, takeover 200, stop 200, repeated-stop 200,
  terminal conflict 409, unknown 404, invalid request 422; stream ended with run.finished.
- Last-Event-ID and ?after replay both matched contiguous sequences. SSE keepalive 15.005s;
  stop while paused 0.0711s. Fake in-flight I/O cancellation: LLM 0.003409s, browser 0.001354s;
  real-browser cancellation/reaping tests passed separately in the full suite.
- Both approve and deny: 200 with correct capability/ID, 401 without capability, 422 with stale ID,
 409 on duplicate. Real GET returned resolved allowed domains/step/cost limits. Both preview/input
  sockets: 4401 for bad auth and actual missing-auth timeout, 4404 for unknown run.

| Frontend call site | Request/consumed data | Backend serving route |
|---|---|---|
| hooks/useTaskOrchestrator.js:232 | POST goal, headless mode, optional changed permissions; consumes runId and three capabilities | api/runs.py:43 POST /api/runs,201 |
| hook:265 | GET SSE; reads envelope type/data, ignores id/event fields | api/runs.py:128 GET /api/runs/{run_id}/events |
| hook:176/258 | POST stop | api/runs.py:113 /api/runs/{run_id}/stop |
| hook:416 | POST takeover/resume | api/runs.py:118/123 /api/runs/{run_id}/takeover and /resume |
| hook:433 | POST approve/deny with UUID approval_id, optional denial reason and bearer capability | api/runs.py:77/92 /api/runs/{run_id}/approve and /deny |
| preview/LivePreview.jsx:95; protocol.js:26 | preview WS, auth in first message; binary metadata+image | api/preview.py:37 WS /api/runs/{run_id}/preview |
| preview/useInputControl.js:16 | input WS, separate first-message auth; validated input/state/pong | api/ws.py WS /api/runs/{run_id}/input |

Frontend SSE fields match current models: plan.steps.id/text; proposal.action/rationale/planStepId;
execution.resultSummary; observation.summary; budget.tokensUsed; approval metadata; pause reason/message;
finished.result; failed.error. step.validated is intentionally not rendered by the hook, not a mismatch.
No preview.frame event is expected: preview has its own binary channel. The frontend does not send
obsolete startUrl/maxSeconds/top-level maxSteps fields; starting URL is appended to the trusted goal,
and explicit permission limits go under permissions. Frontend transport/component tests and actual
React approval/preview browser integration run in the full suite. SSE replay support is server-side;
the frontend currently has no automatic SSE reconnection/replay, a documented operational gap below.

## Phase 1

| ID | Description | Status | Evidence (test name or file:line) |
|---|---|---|---|
| A1 | Discovery report six parts | PASS | docs/discovery-report.md:5/14/44/52/104: frontend, data calls, preview, inventory/decision table and calls-to-rewire all read; historical baseline wording is not current runtime evidence. |
| A2 | No Node/TypeScript server outside frontend | PASS-WITH-DEVIATION | Tracked-file scan found only backend/app/browser/observe.js (page.evaluate DOM code) and testsite/site.js (static fixture client code); no package/tsconfig manifests or Express/Fastify/Nest server imports outside front end/. |
| A3 | Backend dependencies needed and consistent | PASS | backend/pyproject.toml:10 direct dependencies mapped to app imports (Pillow→PIL, official openai, LangGraph, httpx, anyio etc.); fresh pip check gate below. A clean resolver does not itself prove every transitive package is necessary. |
| A4 | Frontend call/route mapping | PASS | Fresh source review: hooks/useTaskOrchestrator.js:176/232/265/416/433; preview/protocol.js:26, useInputControl.js:16. Pair and shape tables below; real HTTP and frontend tests pass. |
| B1 | Async Python stack and bounded dependencies | PASS | backend/pyproject.toml:8/10; app/main.py:46; fresh installed versions below; all app APIs async, SDK imports read in llm/openrouter_client.py:12. |
| B2 | Real HTTP REST/SSE/WebSocket status contracts | FAIL-FIXED | backend/tests/test_network_contract.py:19 `test_real_server_routes_sse_keepalive_and_websockets`; backend/tests/test_reverification_http.py:18 `test_real_http_approval_permissions_and_websocket_rejections`; both execute actual uvicorn loopback sockets. Current-run safe matrices and timing output below. Coverage gap fixed in 340d849. |
| B3 | Event envelopes/order and reserved variants | PASS-WITH-DEVIATION | backend/tests/test_state_events.py:131 `test_all_event_variants`; backend/tests/test_state_events.py:51 `test_event_union_and_action_validation`; backend/tests/test_store_emitter.py:11 `test_fanout_replay_order_and_cleanup`; app/core/events.py:61 defines13 types. Phase 2 explicitly enables step.validated/approval.required, so the old Phase 1 “defined but not emitted” rule is superseded. No chain-of-thought output fields. |
| B4 | Run state machine and exception termination | PASS | backend/tests/test_state_events.py:28 `test_every_transition`; backend/tests/test_state_events.py:70 `test_transition_policy_is_explicit`; backend/tests/test_browser_integration.py:59 `test_real_driver_failure_and_stop_cleanup`; core/state.py:49 table; runtime.py takeover/resume/stop paths read. |
| B5 | Interfaces injected; no fake import in runner | PASS | backend/tests/test_architecture_contract.py:11 `test_runner_has_no_concrete_fake_dependencies`; agent/context.py:34 dependency fields; runtime.py:104 injects store/emitter/browser/model/policy/skills/preview; interfaces/ definitions and core/store.py/core/emitter.py protocols read. |
| B6 | Env parity/CORS/errors/lifespan | PASS | backend/tests/test_architecture_contract.py:22 `test_env_example_exactly_matches_settings`; backend/tests/test_phase2_hardening.py:86 `test_invalid_permission_response_never_echoes_user_domain`; backend/tests/test_approval_cors.py:7 `test_approval_cors_preflight_accepts_authorization_header`; main.py:62 lifespan closes service/pool; :100 CORS origin allowlist; audit parity62 settings, no missing/extra. |
| C1 | Headless/headed and no-display failure | PASS | backend/tests/test_playwright_headed.py:18 `test_headed_visible_smoke`; backend/tests/test_playwright_lifecycle.py:50 `test_no_display_is_clear_and_does_not_launch`; backend/tests/test_browser_integration.py:96 `test_headed_start_error_is_clear_in_run_state`; actual headed gate below. |
| C2 | Fresh contexts and idempotent cleanup | PASS | backend/tests/test_playwright_lifecycle.py:14 `test_isolated_contexts_and_idempotent_close`; backend/tests/test_playwright_lifecycle.py:67 `test_start_failure_after_launch_closes_browser`; backend/tests/test_playwright_lifecycle.py:83 `test_cancellation_during_start_is_clean`; playwright_driver.py:286 new_context, :339 shielded close; leak results below. |
| C3 | Scheme blocking | PASS-WITH-DEVIATION | backend/tests/test_browser_models.py:29 `test_blocked_urls`; backend/tests/test_playwright_actions.py:197 `test_blocked_action`; browser/safety.py validates http(s) with internal about:blank bootstrap exception. All five prohibited schemes are parameterized. |
| C4 | Visible/redacted/capped generation observations | PASS | backend/tests/test_playwright_observe.py:21 `test_observe_pages`; backend/tests/test_playwright_observe.py:36 `test_hidden_text_is_excluded`; backend/tests/test_playwright_observe.py:45 `test_password_and_secret_patterns`; backend/tests/test_playwright_observe.py:62 `test_caps_state_and_hidden_labels`; browser/observe.js:1/12/75 visibility/name/value extraction; playwright_driver.py:388 increments generations. |
| C5 | Actions/refs/errors/popups/dialogs | PASS | backend/tests/test_playwright_actions.py:61 `test_fill_form_select_checkbox_and_submit`; backend/tests/test_playwright_actions.py:145 `test_contenteditable_and_keyboard`; backend/tests/test_playwright_actions.py:162 `test_stale_removed_hidden_and_unknown_refs`; backend/tests/test_playwright_actions.py:235 `test_timeout_and_sanitized_browser_error`; backend/tests/test_playwright_hooks.py:10 `test_popup_switch_callback_and_fallback`; backend/tests/test_playwright_hooks.py:38 `test_alert_is_dismissed_without_dialog_text`; playwright_driver.py:467/497. |
| C6 | No owned Chromium after run outcomes | PASS | backend/tests/test_browser_process_cleanup.py:44 `test_cancel_reaps_own_chromium_processes`; backend/tests/test_agent_security.py:95 `test_stop_mid_io_reaps_real_browser`; freshly executed ten-run leak script covers finished/failed/stopped/takeover-timeout and reports zero owned survivors. Operator processes are not killed or counted as leaks. |
| C7 | Browser hooks | PASS | playwright_driver.py:261/266/729/740/763/767: active page/context/listener/viewport/pause/resume methods read; backend/tests/test_playwright_hooks.py:51 `test_new_page_and_pause_hooks` |
| C8 | Static testsite and server | PASS-WITH-DEVIATION | scripts/serve_testsite.py:22 main binds127.0.0.1; all9 HTML pages plus static assets exist. Injection page contains an external URL as untrusted text; ssrf-redirect.html intentionally targets private addresses for blocked-navigation tests. No CDN or external script dependencies. |
| D1 | OpenRouter official SDK/configured models | PASS | llm/openrouter_client.py:12/95 AsyncOpenAI configured with env settings; config.py:30–39; model identifiers not hardcoded in production Python. Tests use fake identifiers; .env model names only were recorded. |
| D2 | Output formats/retries/auth/usage/cancellation | PASS | backend/tests/test_openrouter.py:85 `test_formats_and_usage`; backend/tests/test_openrouter.py:106 `test_invalid_then_valid_counts_every_attempt`; backend/tests/test_openrouter.py:124 `test_fallback_and_retry_after`; backend/tests/test_openrouter.py:169 `test_no_retry_or_secret_in_errors`; backend/tests/test_openrouter.py:198 `test_timeout`; backend/tests/test_openrouter.py:210 `test_cancellation_aborts_inflight_request`; official docs/current SDK signature verification below. |
| D3 | Trusted prompts and bounded untrusted data | PASS | agent/prompts.py:11 static system rules, :77 random delimiters, neutralized markers and redaction; backend/tests/test_graph_execution.py:157 `test_graph_history_is_capped_and_cost_prompt_is_present`; backend/tests/test_agent_security.py:23 `test_scripted_browser_injection_boundary` |
| D4 | Graph bridge/order/stale/pause/finally | PASS-WITH-DEVIATION | runner.py:159 astream; initial driver startup/blank page occurs before planner but no website observation is read by planner. Outer while only manages interrupts; action loop is graph nodes. backend/tests/test_agent_loop.py:94 `test_stale_reobserves_and_three_fail`; backend/tests/test_agent_controls.py:60 `test_pause_during_proposal_reobserves_before_next_proposal`; runner.py:215 finally closes preview/browser/LLM. |
| D5 | All budgets and both loop detectors | PASS | backend/tests/test_agent_loop.py:189 `test_all_limits_report_final_counters`; backend/tests/test_agent_loop.py:207 `test_no_progress_with_different_actions`; backend/tests/test_agent_loop.py:220 `test_different_values_do_not_trigger_identical_action_loop`; core/budgets.py:34, nodes/navigator.py step limit, nodes/outcome_check.py:27 fingerprint threshold; budget events emitted through execution.publish. |
| D6 | Measured stop cancellation | PASS | backend/tests/test_agent_controls.py:16 `test_stop_during_inflight_io`; backend/tests/test_graph_execution.py:191 `test_graph_stop_interrupts_in_flight_node_within_two_seconds`; backend/tests/test_agent_security.py:95 `test_stop_mid_io_reaps_real_browser`; fresh STOP_TIMING measurements below distinguish fake-I/O timings from real-browser cleanup tests. |
| D7 | Five smoke goals and paid live correctness | UNVERIFIED | docs/smoke-tasks.md:7/19/31/43/55 read: five goals, expected answers and curl commands. Scripted real-browser flows tested. Paid live smoke tests not run under prior explicit billing restriction despite configured key. |
| D8 | Injection baseline stays untrusted | PASS | backend/tests/test_agent_security.py:23 `test_scripted_browser_injection_boundary` parameterizes hidden-text and injection-visible, captures prompt boundaries with scripted model; no semantic attack-classifier claim. |
| E1 | CDP/native pixels/acks/no re-encode | PASS | backend/tests/test_preview_cdp.py:28 `test_every_received_frame_acked_even_when_throttled`; backend/tests/test_preview_cdp.py:59 `test_native_pixels_and_full_viewport`; backend/tests/test_preview_ack_shutdown.py:15 `test_shutdown_keeps_inflight_ack_alive_when_supervisor_is_cancelled`; preview/cdp.py ack before throttle, native max dimensions, Pillow header-only inspection; actual Chromium schema inspected. |
| E2 | Preview WS protocol/auth | PASS | api/preview.py:37–63 verifies run/Origin/auth timeout before subscription; preview/framing.py:28 length prefix + unchanged bytes. backend/tests/test_preview_ws.py:58 `test_valid_token_frames_ping_and_cleanup`; backend/tests/test_reverification_http.py:18 `test_real_http_approval_permissions_and_websocket_rejections` |
| E3 | Bounded latest-wins queues | PASS | backend/tests/test_preview_hub.py:39 `test_latest_wins_multiple_viewers_and_cleanup`; backend/tests/test_preview_cdp.py:220 `test_animation_throttle_and_nonreading_viewer_do_not_block_browser`; preview/hub.py:42 nonblocking oldest-drop. |
| E4 | Preview resilience/retention | PASS | backend/tests/test_preview_cdp.py:98 `test_navigation_popup_and_forced_detach_recover`; backend/tests/test_preview_cdp.py:137 `test_fallback_and_periodic_screencast_retry`; backend/tests/test_preview_cdp.py:174 `test_static_idle_resends_without_stall`; backend/tests/test_preview_hub.py:104 `test_run_retention_starts_after_resource_cleanup`; preview/cdp.py supervisor and hub.py:82/120. |
| E5 | Frame privacy | PASS | backend/tests/test_preview_ws.py:114 `test_preview_lifecycle_privacy_and_shutdown`; backend/tests/test_preview_hub.py:74 `test_transport_debug_payloads_are_filtered`; Frame repr hides bytes, no emitter/store dependency in PreviewHub; actual logging sites reviewed. |
| E6 | Canvas native sizing/latest draw/debug/fakes | PASS | front end/src/preview/LivePreview.jsx: draw sets internal dimensions and RAF latest-only; image.js sizing caps CSS; frontend protocol/image/LivePreview tests; backend/tests/test_preview_fake.py:13 `test_fake_pattern_changes_and_lifecycle` |
| E7 | Subjective preview sharpness | UNVERIFIED | Automated native-pixel/DSF tests pass but no person compared rendered text against normal Chrome at DSF 1/2. Exact human procedure below. |
| F1 | Separate control token/auth/controller | PASS | backend/tests/test_input_auth.py:9 `test_auth_rejects`; backend/tests/test_input_auth.py:44 `test_single_controller_and_nonaccepting_and_disconnect`; backend/tests/test_reverification_http.py:18 `test_real_http_approval_permissions_and_websocket_rejections`; runtime.py:96–100 separate token_urlsafe calls; api/ws.py control acquisition and4409. |
| F2 | Accept input only in eligible paused state | PASS | backend/tests/test_input_auth.py:44 `test_single_controller_and_nonaccepting_and_disconnect`; preview/control.py accepting checks owner and pause reason; api/ws.py:110 locks/rechecks before relay. |
| F3 | Input validation/rate/reject limits | PASS | backend/tests/test_input_protocol.py:20 `test_invalid`; backend/tests/test_input_protocol.py:24 `test_size_and_private_repr`; backend/tests/test_input_protocol.py:35 `test_rate_limit`; backend/tests/test_input_auth.py:79 `test_rate_limited_input_and_oversize_rejects`; api/ws.py:98 reject counter closes4400 at50; input_protocol.py constrained models. |
| F4 | CDP mouse/key/wheel/text mapping | PASS | backend/tests/test_input_relay.py:24 `test_mouse_exact`; backend/tests/test_input_relay.py:71 `test_keys_exact`; backend/tests/test_input_relay.py:97 `test_wheel_shortcut_text_and_popup`; preview/input_relay.py:14/34/91/118/150; actual Input schema fields and modifiers/button flags verified against installed Chromium protocol. |
| F5 | Takeover synchronization/handoff/resume/timeouts | PASS | backend/tests/test_takeover_state.py:39 `test_takeover_waits_for_inflight_and_resume_observes`; backend/tests/test_takeover_state.py:74 `test_control_timeout_and_stop`; backend/tests/test_takeover_state.py:108 `test_handoff_resume_and_limit`; backend/tests/test_takeover_browser.py:215 `test_user_takeover_form_popup_disconnect_and_stop`; runtime.py:187 control lock/cancel gate; driver pause flag + epoch fresh observation. |
| F6 | Input privacy canary/password observations | PASS | backend/tests/test_input_privacy.py:91 `test_websocket_canary_never_reaches_public_channels`; backend/tests/test_takeover_browser.py:172 `test_headless_login_handoff`; backend/tests/test_takeover_browser.py:182 `test_headed_login_handoff`; current privacy selector output below. Fake canaries never copied to this report. |
| F7 | Frontend input capture/mapping/IME/privacy | PASS | preview/input.js:2 pure mapPointer uses actual canvas rect and viewport metadata; useInputControl.js:65–145 listeners restricted to preview/editor, no React text state; frontend input and LivePreview tests. Storage sites reviewed separately. |
| F8 | Human typing and click alignment | UNVERIFIED | Automated DSF 1/2 login/iframe and headed tests execute, but no human typed/visually checked this session. Human headless/headed/resized/letterbox procedure below. |
| G1 | PinchTab spike version/verdict/cleanup | FAIL-FIXED | docs/pinchtab-spike.md:3/14/69/82/98: historical verdict OPTIONAL, version/checks/measurements preserved; 050f1a4 corrects the outdated default-driver wording to current PinchTab with explicit Playwright fallback. Fresh spike script reported OVERALL PASS and owned-process cleanup. Existing test_optional_flag_preserves_default_factory passed again after the documentation edit (1 passed in 0.08s). |
| G2 | Ten mixed runs plus three isolated concurrent runs | PASS | scripts/check_no_leftover_processes.py:88–255 read; freshly run with a disposable authenticated external PinchTab server. Output/RSS and zero survivor count below. |
| G3 | Working tree/history secret scan | FAIL-OPEN | Fresh scripts/audit_repo.py scan reports one historical credential-shaped blob at backend/.env.example (introduced 523fbde, removed 5d1b7aa). No working-tree finding, no tracked.env; revocation unknown. Exact scan counts/exit below. |
| G4 | Optional Docker | PASS | Tracked-file scan: no Dockerfile or compose deployment exists; Docker is optional and not needed by install/test commands. Absence accepted by specification. |
| G5 | Docs and three-command README startup | UNVERIFIED | backend/README.md install/API/events/security/preview/control/limitations sections read; docs/phase1-acceptance.md exists. Fresh documented dependency install succeeds. Exact normal-port startup attempt blocked because8000 is already occupied; existing operator service left untouched. Full browser/frontend tests use their own ports. Human retry steps below. |

## Phase 2

| ID | Description | Status | Evidence (test name or file:line) |
|---|---|---|---|
| H1 | Pinned LangGraph/import/version match | PASS | pyproject.toml:21 langgraph==1.2.17; agent/version.py constant 1.2.17; fresh pip show and metadata match. Imports/signatures and checkpointer attachment verified in fresh runtime probe. |
| H2 | Serializable state/hash records/handoff counters | PASS | backend/tests/test_graph_state.py:8 `test_graph_state_is_json_serializable_and_hashes_values`; agent/state.py:16/25/39/63; runtime JSON round trip succeeds; all 18 requested fields checked. |
| H3 | Eight async node modules | PASS-WITH-DEVIATION | All eight modules exist under agent/nodes and are async returning dicts. Nodes intentionally perform injected LLM/browser/event I/O and update a local state model; “pure” cannot literally apply to those required effects. Conditional routers alone are pure; no rewrite attempted. |
| H4 | Pure tested conditional routes | PASS | backend/tests/test_graph_routing.py:84 `test_routes_are_pure`; backend/tests/test_outcome_graph.py:133 `test_revision_routes`; backend/tests/test_outcome_graph.py:142 `test_failed_outcome_at_max_routes_to_finish`; routing.py AST scan finds zero Await/Call/AsyncFunctionDef nodes. State-equality assertions verify no mutation. |
| H5 | Compiled graph/MemorySaver/thread recovery | PASS | backend/tests/test_graph_execution.py:82 `test_interrupt_checkpoint_resumes_with_command`; backend/tests/test_policy_graph.py:67 `test_real_graph_approval_interrupt_and_resume`; graph.py:27/ 57; runtime identity true; all inspected config dictionaries use run ID as thread_id. |
| H6 | Bridge/events/cancel/error | PASS | runner.py:159 discards graph chunks, context.py execution.publish→EventEmitter, runner.py:183/247 terminal paths; backend/tests/test_graph_execution.py:30 `test_graph_order_events_and_final_counters`; backend/tests/test_graph_execution.py:230 `test_checkpoint_error_channels_do_not_store_raw_exception_text` |
| H7 | Graph stop/pause/budget behavior | PASS | backend/tests/test_graph_execution.py:191 `test_graph_stop_interrupts_in_flight_node_within_two_seconds`; backend/tests/test_agent_controls.py:60 `test_pause_during_proposal_reobserves_before_next_proposal`; backend/tests/test_graph_budgets.py:19 `test_budget_failure_checkpoints_terminal_state`; measured results below. |
| H8 | Phase 1 regression preservation | PASS | Fresh full suite includes original Phase 1 tests; PinchTab opt-ins run separately. git diff baseline2c89060 shows no modified/deleted existing test file; only the new real HTTP regression added. Paid live skips are explicit. |
| I1 | Policy modules and structural interface | PASS | agent/policy/{tiers,domains,dataflow,validator}.py read; validator.py:83 accepts RunRecord or AgentState, structurally satisfies interfaces/validator.py:33; full mypy verifies injected dependency. |
| I2 | Tier rules and hidden target tests | PASS | backend/tests/test_policy_tiers.py:43 `test_ordered_tier_rules`; backend/tests/test_policy_tiers.py:78 `test_keyboard_submit_and_independent_switches` parameterized cases cover tier0 read-only, tier1 click/type/select/check, tier2 submit/payment/download/upload/send, tier3 hidden/scheme/generated credential/financial confirmation; domain override tests cover remaining rules. |
| I3 | Private/metadata ranges with injected DNS | PASS | backend/tests/test_policy_domains.py:36 `test_private_and_metadata`; backend/tests/test_policy_domains.py:40 `test_injected_dns_all_answers_checked`; backend/tests/test_policy_domains.py:60 `test_dns_resolution_is_once_per_hostname_per_run_without_network`; domains.py:9/76 uses is_global and mapped IPv6, resolver.py asynchronous cache. Tests patch getaddrinfo or inject lambdas; socket references are local servers, not real external DNS. |
| I4 | Hash-only bounded dataflow | PASS | backend/tests/test_policy_dataflow.py:9 `test_hash_only_cross_domain_and_same_domain`; backend/tests/test_policy_dataflow.py:26 `test_limits_are_atomic_and_multiple_sources_remain_flagged`; dataflow.py:22 FlowEntry only domains/byte_len; :28 SHA256 first500chars; actual value transient only. |
| I5 | All verdict branches/events/deny bound | PASS | backend/tests/test_policy_graph.py:125 `test_policy_three_denials_never_act_and_have_gap_free_events`; backend/tests/test_policy_graph.py:67 `test_real_graph_approval_interrupt_and_resume`; backend/tests/test_policy_graph.py:181 `test_extraction_to_other_domain_requires_approval`; nodes/policy_check.py:56 emits validation before branching; :88 uuid4. |
| I6 | Interrupt/Command approval resumption | PASS | nodes/approval_gate.py:47 interrupt; runner.py:178 Command; backend/tests/test_policy_graph.py:67 `test_real_graph_approval_interrupt_and_resume` |
| J1 | Bounded real verifier call/model/token cap | PASS | backend/tests/test_outcomes.py:31 `test_verifier_caps_and_untrusted_boundary`; backend/tests/test_outcome_model.py:14 `test_outcome_session_model_and_eighty_token_cap`; outcomes.py:39 elements[:50], :44 history[-3:], :66 llm.propose; OpenRouterPool.outcome_session sets80 tokens. |
| J2 | Verdict parse/retry/fallback/usage | PASS | backend/tests/test_outcomes.py:72 `test_outcome_validation_retry_and_usage`; backend/tests/test_outcomes.py:93 `test_projection_truncation_lowers_verifier_confidence`; backend/tests/test_outcome_graph.py:78 `test_verified_subgoals_complete_and_count_verifier_usage`; outcomes.py two attempts and static failure verdict, nodes/outcome_check.py budget.add_usage. |
| J3 | Outcome routing and partial completion | PASS-WITH-DEVIATION | backend/tests/test_outcome_graph.py:142 `test_failed_outcome_at_max_routes_to_finish`; backend/tests/test_outcome_graph.py:105 `test_two_failures_replan_remaining_work_then_finish_partial_at_limit`; routing.py:52; existing max_attempts counts revisions after initial attempt, preserved and explicitly tested rather than changed. |
| J4 | Safe bounded pure revision | PASS-WITH-DEVIATION | backend/tests/test_outcome_graph.py:113 `test_revision_is_bounded_and_never_echoes_page_or_target_content`; revisions.py:6 categorizes reason, :18 builds≤300 chars with subgoal/action. Uses fixed safe reason categories rather than echoing arbitrary model/page-derived wording. |
| J5 | Planner re-entry and revise timeline | PASS | backend/tests/test_graph_revision.py:25 `test_revision_preserves_completed_work_and_bounds_attempts`; backend/tests/test_outcome_graph.py:88 `test_one_failed_check_revises_then_retries_with_fresh_observation`; planner.py:15/25 preserves completed goals; revise.py emits ProposedData action=revise, value=None. |
| J6 | Authenticated approve/ID/status/stop | FAIL-FIXED | backend/tests/test_approval_api.py:98 `test_wrong_token_stale_id_duplicate_and_unknown`; backend/tests/test_policy_graph.py:150 `test_stop_during_approval_closes_resources_within_two_seconds`; backend/tests/test_reverification_http.py:18 `test_real_http_approval_permissions_and_websocket_rejections`; api/runs.py:65/77, runtime.py:162 matching checkpoint ID; 340d849 adds real HTTP proof. |
| J7 | Authenticated deny/reproposal | PASS | backend/tests/test_approval_api.py:123 `test_denial_then_new_request_rejects_old_id`; backend/tests/test_reverification_http.py:18 `test_real_http_approval_permissions_and_websocket_rejections`; api/runs.py:92; approval_gate denied branch records fixed safe feedback. |
| J8 | One-second approval timeout checkpoint cleanup | PASS | backend/tests/test_phase2_hardening.py:66 `test_approval_timeout_erases_interrupt_history`; tests inspect all history and pending writes; no next/interrupt/pending ID, only safe terminal snapshot. |
| J9 | Approval token isolation/privacy | PASS | api/runs.py:39/53 returns per-run token; runtime.py:97 separate random token; hook.js:58 state and435 bearer only. Frontend approval hook storage/log spies and recorder privacy test executed. |
| J10 | Approval dialog and hook | PASS | front end/src/components/ApprovalDialog.jsx and hook handler at319/335; ApprovalDialog.test.jsx verifies safe fields, buttons/disabled/expiry and Stop; useTaskOrchestrator.approval.test.jsx checks resumed dismissal and auth header. |
| K1 | Permission fields/domain/budget validation | PASS | backend/tests/test_permissions.py:17 `test_invalid_permission_domain`; backend/tests/test_permissions.py:22 `test_permission_bounds_and_global_merge`; backend/tests/test_permissions.py:38 `test_permissions_api_validation_and_effective_response`; backend/tests/test_permission_cost_floor.py:22 `test_subcent_request_rejected_without_breaking_server_default`; permissions.py:13/42 separates effective global limits from user request minimum. |
| K2 | Per-run overrides/global defaults | PASS | policy/validator.py:92 uses state.permissions; permissions.py:48 merges blocked domains and global bounds; backend/tests/test_permissions.py:66 `test_state_permissions_restrict_domains_and_submission` |
| K3 | Effective permissions over real HTTP | FAIL-FIXED | backend/tests/test_reverification_http.py:18 `test_real_http_approval_permissions_and_websocket_rejections` asserts effective domain/max steps/max cost on real GET; 340d849. |
| K4 | Frontend optional permissions panel | PASS | PermissionsPanel.jsx:5 validates domains and returns undefined for defaults; :32 details collapsed; hook.js:238 sends overrides only; PermissionsPanel.test.jsx and useTaskOrchestrator.permissions.test.jsx executed. |
| K5 | Frame redirects/domain-only state | PASS | backend/tests/test_navigation_monitor.py:14 `test_browser_blocks_page_driven_navigation`; backend/tests/test_navigation_monitor.py:60 `test_pinchtab_action_keeps_playwright_navigation_hook`; playwright_driver.py:695 framenavigated registered per page; runner.py:80 stores domain only; network interception guards before redirects too. |
| K6 | Fresh DNS rebinding check | PASS | backend/tests/test_dns_rebinding.py:5 `test_post_navigation_rechecks_dns`; backend/tests/test_dns_rebinding.py:12 `test_frame_navigation_hook_performs_fresh_dns_check`; browser/network.py fresh=True triggers new resolver. Classification/recheck tests do not establish actual TCP peer pinning; deployment limitation listed separately. |
| K7 | All three testsite redirect modes | PASS | testsite/ssrf-redirect.html read; backend/tests/test_navigation_monitor.py:14 `test_browser_blocks_page_driven_navigation` parameterizes js/meta/form against private destinations with source-only fixture exception. |
| K8 | Strict fail and non-strict warning | PASS | tests/eval/scenarios/test_ssrf_eval.py:23 test_ssrf_scenarios includes StrictModeFailsRun and NonStrictModeWarns; asserts failed/finished respectively and domain-only warning events. |
| K9 | Independent browser and policy protection | PASS | backend/tests/test_policy_browser_boundary.py:11 `test_private_navigation_denied_by_policy_and_browser_boundary`; backend/tests/test_navigation_monitor.py:52 `test_browser_guard_is_independent_from_policy`; backend/tests/test_http_redirect_guard.py:14 `test_http_redirect_cannot_contact_private_target`; HTTP tripwire proves private target not contacted on tested redirect/popups. |
| L1 | Eval harness layout | PASS | tests/eval/conftest.py, eval_recorder.py, scenarios/base.py and all five category modules read/listed; fixture drives production graph with real local Chromium and fake models. |
| L2 | All 23 non-live scenarios | PASS | Fresh standalone eval24 tests (23 scenarios+recorder privacy), category counts independently from current source/records: policy6,outcome4,approval5,revision3,SSRF5; actual gate below. |
| L3 | Eval JSON fields/content | PASS | New schema/content scan below checks all records and latest 23 scenarios; strict nine-field numeric/boolean/static-identifier output, no payload fields; longest string recorded. |
| L4 | Per-category evaluation report | PASS | docs/phase2-eval-report.md current table read; report contains policy/outcome/approval/revision/SSRF rates. Prior command counts treated only as historical documentation; this report records fresh results. |
| L5 | Paid live eval accuracy/cost | UNVERIFIED | Five live_eval scenarios present; configured key yes, billing opt-in not granted under earlier restriction. No real model task/accuracy/cost claims. Exact authorized-run steps below. |
| M1 | Secret/history status | FAIL-OPEN | Same freshly run finding as G3, not a second exposure: one historical blob in backend/.env.example; no provider revocation evidence. |
| M2 | Capability token storage/logging | PASS | All production storage references hook.js:14/148/151/159 reviewed; history writes explicit task/url/status/time/steps/detail fields, no capability token. No sessionStorage/cookie assignment. Backend actual log calls allow metadata only; frontend spies verify no token leaks. |
| M3 | Dataflow/state raw values | PASS-WITH-DEVIATION | dataflow.py retains only digest keys/domains/lengths; StepRecord has value_hash and private_action clears value. Active AgentState deliberately holds a redacted Observation and safe result summaries for graph operation; it is not entirely text-free. Raw transient action/observation remains RunContext; terminal snapshots scrubbed. |
| M4 | Eval string bounds | PASS | Scan every string field in every appended historical record; longest/over300 count below; no payload printed. |
| M5 | Log/privacy selection | PASS | Fresh exact pytest -k "canary or privacy or log" -v gate below; skips individually investigated; PinchTab cases run separately. |
| M6 | Terminal checkpoint privacy | PASS-WITH-DEVIATION | backend/tests/test_phase2_hardening.py:23 `test_terminal_checkpoints_remove_page_content_and_action_values`; backend/tests/test_phase2_hardening.py:66 `test_approval_timeout_erases_interrupt_history`; backend/tests/test_terminal_public_result.py:14 `test_terminal_summary_preserves_only_intentionally_public_result`; checkpoints.py deletes entire thread then seeds safe counters and intentionally public sanitized final answer, not raw page history. Public requested facts may remain. |
| M7 | Verdict logs safe and structured | PASS | backend/tests/test_policy_validator.py:123 `test_policy_log_formatter_exposes_only_safe_metadata`; nodes/policy_check.py:49 and runtime.py:173 log static decision/tier/action/runId only. logging.py:5 whitelist excludes arbitrary extras; raw exceptions not logged. |
| N1 | Backend docs coverage | PASS | backend/README.md:3 graph; :1008 verifier/revision/approval ASCII sequence; :1088 permissions; :1126 SSRF; :1184 evaluations; :514 preview and654 takeover read. |
| N2 | All config examples and parity | PASS | Fresh audit parity:62 fields, zero missing/extra; all 16 named Phase 2 vars present. LANGGRAPH_TESTED_VERSION is a comment, not a setting; backend/tests/test_architecture_contract.py:22 `test_env_example_exactly_matches_settings` |
| N3 | Phase 2 verification document exists | PASS | docs/phase2-verification.md exists and has environment/gates/item/fix/open/human sections. No results copied from it. |
| N4 | Completion document exists | PASS | docs/phase2-completion-check.md exists with summary/item/gate/security/human sections. No results copied from it. |
| N5 | Acceptance checklist/human steps | PASS | docs/phase2-acceptance.md exists; human approval, typing/DSF, paid eval and credential-owner actions documented. |
| N6 | Phase3/4 extension notes | PASS | docs/phase2-notes.md read: navigator/policy hooks for later injection classifier and planner SkillProvider retrieval boundary; notes only, no later-phase implementation. |
| N7 | Phase 1 baseline contract diff | PASS-WITH-DEVIATION | Git history independently identifies8fc28ba immediately before first LangGraph dependency commitc4d9bd5. AST diff core/events.py shows no removed fields; added ObservationData.warning/domain, ApprovalData.approval_id/action_summary/page_domain/tier, approval-paused variant; internal revise action allowed by Phase 2. API adds approve/deny, approvalToken and permissions. Existing preview/control semantics unchanged. No public contract change in this re-verification. |

Status totals (98 items): FAIL-FIXED=4, FAIL-OPEN=2, PASS=76, PASS-WITH-DEVIATION=11, UNVERIFIED=5. G3/M1 refer to one finding, not two different credentials.

## Cross-cutting check results

| # | Check | Result and findings |
|---|---|---|
| 1 | Secret scan | FAIL-OPEN: exit 1, one history blob in backend/.env.example ; 0 working findings. Scanned 761 history blobs/279 working files at HEAD 340d849 before final docs commit. git log --all --find-object identifies 523fbde addition / 5d1b7aa removal. A continuation recheck at HEAD 050f1a4 scans 762 history blobs/279 working files and still reports the same one history finding. An in-memory git log -p pattern scan finds 2 changed lines (addition/removal), no values printed. .env ignored/untracked; parity 62/0/0. |
| 2 | Leftover processes | PASS: 10 mixed outcomes plus 3 concurrent runs, 0 owned Chromium/PinchTab survivors; RSS start 94.08/end 126.21/delta 32.13 MiB; disposable server also removed. Operator processes not touched. |
| 3 | Privacy canary/log selector | PASS:20 passed,5 opt-in skipped,546 deselected in 22.84s. Full-suite real-browser canary/password tests also pass. Skip reasons above; no canary payload copied into report. |
| 4 | Token storage | PASS: all 4 production storage references reviewed, all in hook.js:14/148/151/159; only bounded explicit history fields, no capability token. No production sessionStorage or cookie storage. Separate token state/first-message-auth/bearer paths and tests verified. |
| 5 | Raw value/state scan | PASS-WITH-DEVIATION: dataflow stores hash/domain/length only. StepRecord has value_hash; checkpoint actions clear value. AgentState includes redacted last_observation/result_summary strings while active, so a claim of no text-capable fields would be false. Terminal cleanup removes history and retains only sanitized intentionally public result/counters, tested across all endings. |
| 6 | Eval content | PASS: 590 append-only records; longest string 63 chars ; 0 strings>300; nine allowed fields only. Latest 23/23 scenarios pass with event/assertion booleans true. Old failures retained. Static scenario name ApprovalTokenMissing is not a capability value. |
| 7 | Log statements | PASS: reviewed 8 actual app log calls (main.py:136, runtime.py:173, core/state.py:180, agent/runner.py:194/225/240/255, nodes/policy_check.py:49). Static messages, runId/status/errorType/tier/action only; no content or raw traceback. NavigationMonitor.warning and pool.info are not logging calls. Structured whitelist/transport DEBUG filters and log-capture tests pass. |
| 8 | Frontend contracts | PASS: request/response/SSE/WS pairs reviewed in table above; headless body and optional permissions match CreateRun. Safe approval dialog fields and existing preview/control protocols match. No application contract changed in this check. |
| 9 | LangGraph version | PASS-WITH-DEVIATION: requested langgraph.__version__ command exits 1 with AttributeError; installed package does not expose it. pip show and importlib.metadata both 1.2.17; LANGGRAPH_TESTED_VERSION 1.2.17; graph imports/JSON roundtrip/checkpointer attachment succeed. |
| 10 | Dependency audit | FAIL-FIXED: npm initial7 advisories (6 high/1 moderate), compatible lockfile update0546bf9 now 0; clean frontend build/tests pass. Fresh pip check says No broken requirements found. No backend dependency removed or loosened. |

## Fixed during this re-verification

| Commit | Area | What was fixed | Test that covers it |
|---|---|---|---|
| 0546bf9 | Phase 1 dependency security | Non-force, lockfile-only compatible updates remove six high and one moderate npm advisory; no direct manifest range changed | npm audit 0; clean npm ci; all 57 frontend tests; production build |
| 050f1a4 | Phase 1 documentation | Label the spike recommendation as historical; correct current PinchTab default and Playwright fallback without changing measurements | app/config.py:80; test_optional_flag_preserves_default_factory: 1 passed in 0.08s |
| 340d849 | Phase 2 contract evidence | Add real loopback HTTP coverage for approve/deny auth, stale/duplicate decisions, effective permissions and both WS auth close codes | backend/tests/test_reverification_http.py:18 test_real_http_approval_permissions_and_websocket_rejections; targeted 1 pass and final full suite |

The report-first commit is b1b47ae. Final report/eval artifact commit records results only. No
existing test/assertion/timing/skip was modified. No new feature, route or public event/schema field
was added. No backend or frontend application source changed. The initial backend suite had no
failure; the new test closes a required evidence gap. The npm audit and history scan failures are
recorded, not hidden behind overall test success.

## Still open (FAIL-OPEN)

| ID | Severity | Description | Proposed approach |
|---|---|---|---|
| G3/M1 | blocker | Historical credential-shaped blob in backend/.env.example, introduced 523fbde and removed 5d1b7aa. Revocation and whether it is still usable are unknown. Scanner exits 1. | Owner privately identifies/revokes/rotates any real exposed credential and proves revocation; then explicitly coordinate history/remote/clone cleanup. Never print its patch/value. Rotation alone does not remove history findings; do not weaken the scanner or rewrite shared history without authorization. |
| K6 deployment limit | should-fix | DNS classification/rechecks do not pin the actual TCP peer; tests prove specified checks and tested redirects, not universal DNS-rebinding immunity. | Review independent egress/proxy enforcement or peer-IP pinning in deployment. This requires a security design choice; do not silently claim it exists. |
| Runtime retention | should-fix | In-memory run/event/capability/terminal-summary dictionaries lack a general historical TTL. Finite stress/RSS pass is not an unbounded-service-memory guarantee. | Decide retention/reconnect/audit requirements before introducing expiry or durable storage. No new retention feature added during verification. |
| Frontend SSE recovery | minor | Server supports replay, but the frontend fetch stream has no automatic reconnect/Last-Event-ID replay after a network drop. | Add explicit reconnection/cursor behavior in a separately scoped UX change while preserving terminal/history semantics; current UI exposes the stream error. |
| Initial-popup redirect usability | minor | Initial popup HTTP redirects fail closed even when public, which can limit OAuth-style flows. | Keep safe default; review redirect interception and public-hop validation before widening behavior. No real-account OAuth success claimed. |

## UNVERIFIED: human must check

1. **Normal startup/README:** close only your own old backend/frontend terminals if they occupy 8000/5173.
   From repo root execute the three commands in README.md under Run locally. That explicit fake
   configuration makes no paid calls. Confirm localhost:5173 loads, /health returns status ok and a
   fake task finishes with generated preview. For real mode use the documented private .env and
   authenticated loopback PinchTab setup; do not put tokens in URLs/history.
2. **Preview sharpness:** use only the local fake-data pages, start real browser mode, set
   DEVICE_SCALE_FACTOR=1 and open http://localhost:5173/?debug=1. At100% zoom compare preview text
   against the same page in normal Chromium. Check internal canvas=frame pixels, CSS is not upscaled.
   Repeat with factor 2 after restarting backend; resize and letterbox. No human comparison is claimed.
3. **Takeover typing:** deliberately allow localhost only in a local-development test configuration,
   start login.html, Take over, type the fake credentials shown by that demo, submit, Resume. Verify
   fresh observation and result. Repeat headless and headed (headed via API), at DSF 1/2 and resized
   letterboxed preview; verify click placement, typing, Tab/Enter and Stop. Never use real secrets for
   this acceptance check. Restore BLOCK_PRIVATE_NETWORK=true outside the isolated local demo.
4. **Approve/deny UI:** use the local form goal, leave submit approval enabled, inspect safe summary,
   risk/domain and active Stop button. Approve once and confirm execution/completion. Repeat and Deny;
   confirm no denied action executes and a fresh proposal follows, then approve an acceptable proposal.
   Confirm duplicate/stale request behavior and no capability in storage/address bar.
5. **SSRF fixture:** with default BLOCK_PRIVATE_NETWORK=true an ordinary agent navigation to localhost
   itself must be denied. Do not disable protection globally and call that a redirect-security test.
   Run `pytest -q -s tests/eval/scenarios/test_ssrf_eval.py` from backend: its isolated driver grants only
   the fixture source origin, while JS/meta/form private destinations remain protected. All five cases
   must pass; event assertions require observation.summary warning and domain-only ssrf_blocks.
   To inspect those blocks manually in the frontend, use an isolated test app with that same
   source-origin-only injected fixture exemption (see test_ssrf_eval.py:29–37), never a production
   bypass. Observe each mode separately in its timeline and strict-mode failure. No manual frontend
   SSRF timeline inspection was performed here; the source exception is intentionally test-only.
6. **Live smoke, only after explicit billing opt-in:** activate the backend environment and privately
   configure OPENROUTER_API_KEY/LLM_MODEL_PRIMARY; from backend run
   `pytest -q -m live tests/test_live_smoke.py -ra`. Check all five fake-site expected results against
   docs/smoke-tasks.md. In OpenRouter activity/billing compare model/timestamps/tokens/costs against run
   counters and remaining credit. No real paid step count, accuracy or cost was measured here.
7. **Live eval, only after billing opt-in:** run
   `pytest -q -m live_eval tests/eval/scenarios/test_live_eval.py -ra` from backend. Inspect five newly
   appended docs/eval-results.json records: status, events_matched, assertions_passed, steps/tokens/cost.
   Compare with OpenRouter activity; require at least 4/5 correct expected outcomes. Never copy keys,
   input or raw page/model text into reports. Do not confuse scripted fake usage with billed usage.
8. **Historical credential:** privately establish owner/provenance and revoke any real exposure;
   confirm old credential unusable, configure replacement only in ignored .env, coordinate approved
   history/clone remediation and rerun scripts/audit_repo.py. This remains a release gate.

## Out of scope (Phase 3+)

Injection classifier and adversarial attack suite; trusted skill library/retriever implementation;
accounts, durable database and shared multi-worker browser recovery. No later-phase feature built.
