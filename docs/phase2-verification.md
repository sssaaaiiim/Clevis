# Phase 2 verification and hardening

**RELEASE BLOCKER — F1 (historical credential) remains open.** The approved follow-up fixes resolved A9: the clean-environment backend suite passes 544 tests, and all 15 managed PinchTab integration tests pass. Historical failures and their subsequent fixes are recorded below; owner credential remediation remains required.

**F1:** one credential-shaped historical blob was detected in `backend/.env.example`. Revocation is unverified. The working tree has no scanner findings, but this is not a clean-history security PASS. No secret values are included here. Do not release with an unrevoked exposed credential.

Audit started from `937c8d5`; report-first commit `647cdd8`. No pre-existing test assertion was changed, removed, skipped or weakened during this audit. Paid model tests remain unrun under the prior explicit prohibition; a configured key is not treated as billing permission.

## Environment and installation

- OS Linux 7.0.0-38-generic; Python 3.14.4; Node v22.22.1.
- Existing environment: LangGraph 1.2.17, Playwright 1.64.0, FastAPI 0.156.4.
- Fresh audit environment: LangGraph 1.2.17 (constant also 1.2.17), Playwright 1.64.0, FastAPI 0.162.0, pydantic 2.14.1. Dependency ranges legitimately resolve newer FastAPI/pydantic versions; final gates use the clean environment.
- Display configured: yes. Actual headed gate outcome is recorded below; no human visual check is claimed.
- OPENROUTER_API_KEY configured: yes (presence only). Primary/fallback: `deepseek/deepseek-v4.1-flash`; outcome model unset, inherits primary. No .env values other than permitted model names/presence were copied into this report.
- Fresh install: from backend, `python3 -m venv /tmp/clevis-phase2-audit-venv`, `/tmp/clevis-phase2-audit-venv/bin/pip install -e '.[dev]'`, `/tmp/clevis-phase2-audit-venv/bin/playwright install chromium`. Same documented commands, temporary environment path instead of replacing the operator environment. Initial clean install succeeded. After continuation discarded temporary files, recreated it for final gates; results below.
- `npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache`: 435 packages installed, exit 0. Frontend manifests/lockfile unchanged.

## API verification

Installed 1.2.17 imports succeeded: `langgraph.types.interrupt`, `langgraph.types.Command`, `langgraph.checkpoint.memory.MemorySaver`, and `langgraph.graph.StateGraph/START/END`.
`interrupt(value, *, response_schema=None)` and keyword-only `Command(..., resume=..., ...)` were inspected in the installed package. `MemorySaver.adelete_thread(self, thread_id)` deletes all thread checkpoints/writes; `agent_graph.aupdate_state(..., as_node="finish")` seeds the terminal summary. Regression tests exercise these calls.
Official documentation checked: [interrupts and Command resumption](https://docs.langchain.com/oss/python/langgraph/interrupts). The current docs include additional streaming/HITL options; this product uses only interrupt/Command and its existing EventEmitter→SSE transport.

## Raw quality gates — before fixes

| Command / scope | Actual result |
|---|---|
| Existing env, backend `pytest -q -ra` | `531 passed, 25 skipped in 222.31s (0:03:42)`; exit 0. |
| New audit regressions before fixes | `5 failed, 1 passed in 24.70s`: page content retained on finished/failed/stopped, timeout pending approval ID retained, Authorization CORS preflight 400. Domain-error non-echo test passed. |
| Fresh backend Ruff/mypy before code changes | `All checks passed!`; `Success: no issues found in 152 source files`. |
| Checkpoint regression + existing graph/budget/policy/outcome tests after fix | `32 passed in 2.20s`. |
| Approval CORS regression after fix | `1 passed in 0.62s`. |
| Initial new-test mypy attempt | Two config-dict contextual typing errors in the new test only; fixed in 378f7f1 without changing assertions. Subsequent backend mypy: `Success: no issues found in 155 source files`. |
| New sub-cent budget regressions before fix | `2 failed in 1.66s`; valid global0.005 failed graph round-trip and default run. First fix attempt caught double resolution: `1 failed, 27 passed in 4.78s`; corrected at the API/service boundary. |
| Permissions/checkpoint/approval after cost fix | `28 passed in 5.52s`. |
| Clean full suite before final cost fix | `537 passed, 25 skipped in 264.76s (0:04:24)`. |
| Public-result regression before correction | `1 failed, 1 passed in 0.51s`; terminal cleanup double-redacted a permitted public username. After correction: `17 passed in 2.50s` including privacy/graph tests. |
| Full suite after cost fix, before public-result correction | `1 failed, 538 passed, 25 skipped in 266.97s`; unchanged `test_hidpi_takeover_iframe_input_and_capture_resume` failed at test_preview_cdp.py:336: checkbox remained unchecked after CDP down/up. No assertion/timing/preview code was changed. Isolated rerun and final complete rerun recorded below. |
| HiDPI investigation after full-suite failure | Initial isolated rerun: `1 failed in 7.04s`. Five further isolated runs: 3 passed, 2 failed; both failures at test_preview_cdp.py:336 (`Locator expected to be checked`, actual unchecked). Times: 7.00s fail, 2.98s pass, 7.04s fail, 3.06s pass, 3.01s pass. Existing implementation, assertions and timing limits unchanged. This is evidence of intermittency, not a fix. |
| Frontend baseline `npm test` | `Test Files 12 passed (12)`; `Tests 57 passed (57)`; 12.89s. |
| Frontend baseline `npm run build` | exit 0; `built in 2.35s`. |
| Security baseline | 716 history blobs / 265 working files scanned, one historical finding, zero working-tree findings; .env ignored, none tracked; 62 settings, zero missing/extra example variables. |

Shell attempts from the wrong working directory and sandbox stream-fd restrictions were corrected; they are not substituted for a documented backend quality-gate result. Temporary logs from before the continued turn were discarded by the environment; counts above are the command outputs actually observed during this audit. The final log summary is recorded below before completion.

## Original final quality gates (before the subsequent approval)

Commands used the fresh `/tmp/clevis-phase2-audit-venv` Python/CLI, from backend unless stated.

| Exact command / scope | Raw result / exit |
|---|---|
| `pytest -q -ra` | **`1 failed, 540 passed, 25 skipped in 258.43s (0:04:18)`**, exit1. Failure: `test_preview_cdp.py::test_hidpi_takeover_iframe_input_and_capture_resume`, line336, checkbox expected checked but actual unchecked. |
| `pytest -q -m headed -ra` | `4 passed, 562 deselected in 13.28s`, exit0. Display-backed Chromium really launched; no headed skips. |
| `pytest -q tests/eval/ -ra` | `24 passed, 5 skipped in 57.40s`, exit0; 23 scenarios plus recorder privacy test. |
| `PINCHTAB_URL=managed pytest -q -m pinchtab -ra` | **`2 failed, 13 passed, 551 deselected in 46.34s`**, exit1. Both login smoke fixtures (default hybrid and Playwright selector) omit demo credentials from their user goal; policy denies scripted password typing as agent-generated. Their final result assertion consequently fails. |
| Targeted input/checkpoint privacy + stop + real network contract | `12 passed in 18.74s`, exit0; command below. |
| `ruff check .` | `All checks passed!`, exit0. |
| `mypy .` | `Success: no issues found in 157 source files`, exit0. |
| `pip check` | `No broken requirements found.`, exit0. |
| Frontend `npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache` | `added 435 packages in 1m`, exit0. |
| Frontend `npm test` | `Test Files 12 passed (12)`; `Tests 57 passed (57)`; 19.52s, exit0. |
| Frontend `npm run build` | `built in 3.39s`, exit0. |
| Root `python scripts/check_no_leftover_processes.py` | PASS ten mixed finished/failed/stopped/takeover-timeout runs and three concurrent isolated contexts, frames, events and cookies; no owned Chromium/PinchTab process remains. RSS MiB start93.94, end 126.36, delta 32.42; exit0. |
| Root `python scripts/audit_repo.py` | **exit1**: at code commit6723da7 before documentation-only commits: 732 history blobs /272 working files scanned; one historical credential-shaped finding, zero working-tree findings. No tracked .env; local .env ignored. Settings count62, missing example variables0, extra0. Failure is not waived. |
| `git log -p --all` pattern scan (in-memory, no patch printed) | Two matching changed lines, corresponding to addition/removal of the same historical credential-shaped content. Values not printed. |
| Eval JSON schema/content/latest-record scan | 406 historical records, exactly nine allowed fields each; no forbidden capability/canary fields/content. Latest 23 scenarios all pass, all event/assertion booleans true. Fake token counters 1282, fake cost0.0. Paid live usage/cost remains UNVERIFIED. |

Targeted privacy/stop command: `pytest -q -s tests/test_input_privacy.py tests/test_phase2_hardening.py tests/test_terminal_public_result.py tests/test_agent_controls.py::test_stop_during_inflight_io tests/test_network_contract.py`.
Measured stop cancellation: LLM0.001844s, browser0.001831s. Real HTTP stop while paused0.0701s. These are measured fake-I/O cancellation times; existing real-browser cancellation/cleanup tests also ran in the full suite. SSE keep-alive measured15.005s; real health/create/get/events/stop/takeover/resume and authenticated preview/input checks passed; replay tested by header and query.

The leak command ran unchanged against a disposable authenticated PinchTab0.15.2 server on an ephemeral loopback port, started with the existing managed fixture configuration. The server was external to the checked script, matching documented separate-terminal operation. The wrapper also verified server process cleanup after fixture teardown. No operator service, process or private token was reused.

Skip investigation: five paid `live_eval` cases require explicit `-m live_eval`; five paid Phase1 `live` cases require `-m live`. Both remain unrun under the prior billing prohibition despite a configured key. Fifteen PinchTab cases skipped during ordinary collection are legitimate explicit-service opt-ins; they were subsequently run with a managed server, exposing the two failures above. Deselected cases in marker-only commands are selection results, not altered skip logic.

The HiDPI failure also occurred in the preceding complete run and in three of six isolated invocations in this audit (initial isolated failure plus five repetitions with two failures). Earlier historical rates are in preview-repetition-results.md. A separate pre-last-fix clean run passed537 tests, but that result does not replace the failing final run. No preview implementation, timing threshold, assertion, fixture or existing test was altered to obtain a green result.

Pure reproduction of the hybrid login conflict returned `{decision:deny, tier:3, reason:"Agent-generated credential denied; request human handoff."}` for the fixture's actual generic goal and password-field action. Both smoke cases fail because the fake script expects a welcome message after the denied action. Production credential protection must remain intact; resolving the legacy scenario needs an explicitly agreed fixture/provenance or human-handoff update, not disabling policy.

At the original audit endpoint 66fb45f, `git diff 647cdd8` confirmed zero modified pre-existing backend test or frontend source files. The later approved follow-up changes only the legacy login fixture input; its original assertion ASTs remain identical. New regressions cover the fixes; no assertions were weakened. All gate exit codes above are individual command results, not the exit code of the orchestration helper that continued through failures.

## Approved follow-up — fixes and verification

The subsequent user approval authorized fixing the HiDPI preview/input race and correcting the
legacy login fixtures. Paid live calls and destructive credential/history remediation were not
included. Earlier failures above remain recorded as evidence.

- 6cdab93: add a bounded preview/input readiness barrier. Mouse input waits until scaled capture
  detaches and native fallback capture has been attempted. Deterministic tests cover no dispatch
  before readiness and detach-before-readiness ordering. Original HiDPI assertion/timing unchanged.
- 7f0ab6f: supply fake credential provenance in the login fixture's trusted goal and share the
  existing secret redactor with run.started. All existing login result, event and password-privacy
  assertions remain unchanged; the production generated-credential deny rule is unchanged.
- Initial targeted units: 20 passed in 0.37s. The initial new unit had a mock Page reporting closed;
  corrected that mock to represent an open page, without removing/changing its assertions.
- HiDPI browser repetitions: 30/30 separate pytest invocations passed, zero failures, in isolation.
  This is not a claim of 30 repetitions under parallel browser load.
- Managed PinchTab integration: 15 passed, 554 deselected in 54.66s, including both login selectors.
- Lint/types: All checks passed; Success: no issues found in 160 source files.

Final approved follow-up gates used the recreated clean environment, with no application changes
between this full-suite run and the subsequent serial checks:

| Command / scope | Actual result |
|---|---|
| Backend `pytest -q -ra` | `544 passed, 25 skipped in 258.73s (0:04:18)`, exit0. |
| `pytest -q -m headed -ra` | `4 passed, 565 deselected in 13.68s`, exit0; real display-backed launches. |
| `pytest -q tests/eval/ -ra` | `24 passed, 5 skipped in 58.53s`, exit0; 23 scenarios plus recorder unit. |
| Managed PinchTab `PINCHTAB_URL=managed pytest -q -m pinchtab -ra` | `15 passed, 554 deselected in 54.66s`, exit0. |
| Targeted privacy/canary/terminal-state/stop checks | `12 passed in 2.41s`, exit0; exact command below. |
| `ruff check .` | `All checks passed!`, exit0. |
| `mypy .` | `Success: no issues found in 160 source files`, exit0. |
| `pip check` | `No broken requirements found.`, exit0. |
| Frontend `npm test` | 12 files / 57 tests passed, 19.45s, exit0. |
| Frontend `npm run build` | `built in 3.35s`, exit0. |
| Root `python scripts/check_no_leftover_processes.py` | PASS ten mixed lifecycle runs and three concurrent isolated runs; no owned Chromium/PinchTab remains, exit0. RSS MiB start 94.12, end 126.59, delta 32.47. Disposable authenticated server also cleaned up. |
| Root `python scripts/audit_repo.py` | **exit1**, 747 history blobs /275 working files scanned: one historical credential finding, zero working-tree findings. No tracked .env, local .env ignored; 62 settings, zero missing/extra example variables. F1 remains open. |
| Eval JSON schema/latest-record/content scan | 452 append-only historical records; all nine documented fields only. Latest 23/23 scenarios pass with event/assertion booleans true; fake counters 1282 tokens/$0.00. Static scenario name ApprovalTokenMissing is permitted; no capability values/canary payloads occur. |

Targeted command: `pytest -q -s tests/test_input_privacy.py tests/test_phase2_hardening.py tests/test_terminal_public_result.py tests/test_started_goal_privacy.py tests/test_agent_controls.py::test_stop_during_inflight_io`.
Measured cancellation: LLM 0.001994s, browser 0.001954s (fake in-flight I/O). The real-browser cleanup tests
also pass in the full suite. The leak wrapper uses the same disposable external managed server setup
as the original audit; it does not reuse the operator's service or print its token.

All 25 full-suite skips remain the documented explicit opt-ins: five live, five live_eval and 15
PinchTab cases. The 15 PinchTab cases passed separately. No paid model requests were made. Existing
HiDPI/input browser files remain byte-for-byte unchanged; the approved fixture input changed with
all original assertion ASTs identical. No timing threshold, assertion, skip rule or policy protection
was loosened. API verification for the readiness change used installed Playwright 1.64.0 plus the
[CDPSession reference](https://playwright.dev/python/docs/api/class-cdpsession) and
[official Emulation protocol definition](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Emulation.pdl).
No new CDP method or public protocol field was introduced.

## Full specification audit

Status counts: FAIL-FIXED=8, FAIL-OPEN=1, PASS=38, PASS-WITH-DEVIATION=7, UNVERIFIED=1. All 55 IDs have a status.

| ID | Status | Evidence / fix commit |
|---|---|---|
| A1 | PASS | `pyproject.toml:21`, `agent/version.py:1`; installed `pip show langgraph`: 1.2.17. Installed imports/signatures verified; `test_interrupt_checkpoint_resumes_with_command`. |
| A2 | PASS | `test_graph_state_is_json_serializable_and_hashes_values`; `agent/state.py` pydantic models; SHA-256 value_hash, BudgetState.handoffs_used. |
| A3 | PASS-WITH-DEVIATION | Nine async node files under `app/agent/nodes/`, confirmed by AST. Nodes deliberately perform injected LLM/browser/event effects; strictly pure nodes would contradict their specified responsibilities. Routing is pure. |
| A4 | PASS | `test_routes_are_pure` parametrization plus `test_revision_routes` and `test_failed_outcome_at_max_routes_to_finish`; AST: nine routes, no await, emit or I/O calls. |
| A5 | PASS | `agent/graph.py:23` compile with MemorySaver, module-level agent_graph; `test_graph_order_events_and_final_counters`, isolated thread tests. Runner/runtime configs use run_id as thread_id. |
| A6 | PASS | `agent/runner.py` discards astream updates, resumes Command on the original task; `test_checkpoint_error_channels_do_not_store_raw_exception_text`, stop tests; no frontend graph-stream bridge. |
| A7 | PASS | `test_stop_during_inflight_io`, `test_graph_stop_interrupts_in_flight_node_within_two_seconds`, pause/reobserve and graph budget tests. Measured stop timings are listed below. |
| A8 | PASS | `test_interrupt_checkpoint_resumes_with_command`, `test_real_graph_approval_interrupt_and_resume`; README graph/checkpointer section documents process residency, no TTL and restart loss. |
| A9 | FAIL-FIXED | Approved fixes 6cdab93 / 7f0ab6f: clean full suite 544 passed/25 opt-in skipped; managed PinchTab 15 passed; original HiDPI test 30/30 isolated invocations passed. Original preview/takeover tests are byte-for-byte unchanged against 66fb45f; all PinchTab assertion ASTs identical, only approved demo-login goal input changed. Historical authorized changes: shared step.validated sequence, explicit local policy fixtures, approval-stub replacement and additive permissions key (913634a). |
| B1 | PASS | `test_ordered_tier_rules` (28 rows), `test_keyboard_submit_and_independent_switches`; policy domain/data-flow tests cover destination overrides. Rules cover type/role/text submit, payment, hidden, generated credential, upload/download/send and read-only/control actions. |
| B2 | PASS | `test_exact_domain_policy_and_blocked_override`, `test_bad_domain_configuration_fails`, `test_domain_override`; config field validator calls parse_domains before startup. |
| B3 | PASS-WITH-DEVIATION | `test_private_and_metadata` (18 hosts), `test_injected_dns_all_answers_checked`, `test_dns_resolution_is_once_per_hostname_per_run_without_network`. DNS unit tests inject answers; socket use elsewhere is intentional loopback HTTP/Chromium integration, not an assertion that the entire suite has zero networking. |
| B4 | PASS | `test_hash_only_cross_domain_and_same_domain`, `test_limits_are_atomic_and_multiple_sources_remain_flagged`; dataflow.py retains SHA-256 keys, source-host lists and byte lengths only. |
| B5 | PASS | `test_policy_three_denials_never_act_and_have_gap_free_events`, `test_real_graph_approval_interrupt_and_resume`, `test_policy_log_formatter_exposes_only_safe_metadata`; policy_check.py emits validated before routing, creates UUID4 approvals. |
| B6 | PASS | Installed langgraph.types.interrupt/Command imports verified; production `test_real_graph_approval_interrupt_and_resume[approved/denied]` checks saved interrupt and explicit resumption. |
| C1 | PASS | `test_verifier_caps_and_untrusted_boundary`, `test_outcome_session_model_and_eighty_token_cap`; strict 50-element/3-summary projection and domain-only URL; captured SDK body max_tokens=80. |
| C2 | PASS | `test_outcome_validation_retry_and_usage` (four paths), `test_projection_truncation_lowers_verifier_confidence`; OutcomeVerdict and cumulative budget tests. |
| C3 | PASS-WITH-DEVIATION | `test_failed_outcome_at_max_routes_to_finish`, `test_two_failures_replan_remaining_work_then_finish_partial_at_limit`, outcome evals. Existing max_attempts means bounded revisions after the initial attempt; preserved and documented instead of changing passing assertions. |
| C4 | PASS-WITH-DEVIATION | `test_revision_is_bounded_and_never_echoes_page_or_target_content`, RevisionMessageFormat eval. Feedback uses fixed reason categories rather than arbitrary verifier prose/target descriptions, preventing page-text leakage; <=300 chars and sub-goal ID retained. |
| C5 | PASS | `test_revision_preserves_completed_work_and_bounds_attempts`, PlannerReentrySkipsCompleted eval; fake LLM captures revision-bearing messages and checks completed prefix preservation. |
| C6 | PASS | `test_multi_subgoal_revision_and_authenticated_approval_timeline`, outcome/revision tests; revise_node.py emits internal revise with a bounded categorized rationale and no value. |
| C7 | FAIL-FIXED | 7f5990b clears pending state/history at terminal exit; 8acb3b5 permits Authorization CORS preflight. Existing `test_wrong_token_stale_id_duplicate_and_unknown`, authenticated decision/timeline tests and stop-during-approval tests pass; new `test_approval_cors_preflight_accepts_authorization_header` passes. |
| C8 | PASS | `test_authenticated_approval_and_denial[deny]`, `test_denial_then_new_request_rejects_old_id`, DenyAndRepropose eval; same bearer authorization helper for both routes. |
| C9 | FAIL-FIXED | 7f5990b; `test_approval_timeout_erases_interrupt_history` uses 1s timeout and proves one terminal snapshot, no next/interrupt, no pending approval ID/payload or active task. Existing timeout/stop tests preserved. |
| C10 | PASS | `test_authenticated_approval_and_denial`, frontend `useTaskOrchestrator.approval.test.jsx` storage/log spies; token held in useState, sent only as Authorization header and cleared at run end. |
| C11 | PASS | `ApprovalDialog.test.jsx` plus approval hook tests: safe fields, badges, disabled duplicate clicks, denial reason, 422 expiration, resumed dismissal; Stop remains active inside the modal. |
| D1 | FAIL-FIXED | ac36d50; `test_subcent_global_cost_ceiling_roundtrips_as_effective_permissions` and `test_subcent_request_rejected_without_breaking_server_default`: stricter server limits serialize correctly; user requests retain the $0.01 floor and global ceiling.  `test_permissions_api_validation_and_effective_response`, `test_permission_bounds_and_global_merge`, invalid-domain parametrization; pydantic/resolve_permissions enforce host syntax, conflicts and env ceilings. |
| D2 | PASS | `test_state_permissions_restrict_domains_and_submission`, `test_disabled_run_capabilities_deny`, `test_per_run_step_ceiling_is_enforced_by_runner`, JSON state tests; effective settings composed per run. |
| D3 | PASS | Real loopback Uvicorn/httpx smoke: POST 201, GET 200, finished; GET permissions included max_steps=30, max_cost_usd=0.5, max_handoffs=3 and default capability booleans. Existing `test_real_server_routes_sse_keepalive_and_websockets` exercises real routes too. |
| D4 | PASS | `PermissionsPanel.test.jsx`, `useTaskOrchestrator.permissions.test.jsx`: collapsed/default omission, explicit overrides, invalid URL inputs and hide-after-start; no server env values fetched. |
| D5 | PASS | `test_browser_blocks_page_driven_navigation[js/meta/form]`, `test_http_redirect_cannot_contact_private_target`, `test_pinchtab_action_keeps_playwright_navigation_hook`; hostname-only callback, warning event and state verified. |
| D6 | PASS | `test_post_navigation_rechecks_dns`, `test_frame_navigation_hook_performs_fresh_dns_check`: injected public-first/private-second answers and about:blank replacement. This does not pin the actual TCP peer. |
| D7 | PASS | `testsite/ssrf-redirect.html`; real headless tests for JS, meta and form pathways. Dedicated source-origin fixture exception does not change production private-address defaults. |
| D8 | PASS | StrictModeFailsRun and NonStrictModeWarns evals check terminal/error vs continued run, warning events and hostname-only ssrf_blocks. |
| D9 | PASS | `test_private_navigation_denied_by_policy_and_browser_boundary`, `test_browser_guard_is_independent_from_policy`; separately injected browser monitor and response-stage HTTP redirect tripwire. |
| E1 | PASS | `backend/tests/eval/` contains conftest.py, eval_recorder.py, scenarios/base.py and all five category modules plus live_eval. |
| E2 | PASS | 23 non-live scenarios: policy 6, outcome 4, approval 5, revision 3, SSRF 5. Standalone final eval command/counts below; latest-per-scenario JSON audit verifies 100%. |
| E3 | PASS | `docs/eval-results.json` append-only records; `test_recorder_excludes_capabilities_and_content` and schema scan allow only nine documented identifier/boolean/numeric fields including static failure_reason. |
| E4 | PASS | `docs/phase2-eval-report.md` contains category rates, historical failures and explicit unverified live cost. This audit adds fresh results without erasing earlier failures. |
| E5 | UNVERIFIED | Five paid live_eval scenarios exist. Configured key is present, but prior explicit no-paid-tests instruction remains in force; no paid calls made. Exact authorized-run steps below. |
| E6 | PASS | `tests/eval/test_recorder.py` injects forbidden canaries; recorder whitelists fields and uses static failure messages. Final JSON content/schema scan listed below. |
| F1 | FAIL-OPEN | BLOCKER: scripts/audit_repo.py reports one credential-shaped historical blob in backend/.env.example:1 (historical version); zero working-tree findings and no tracked .env. git log -p pattern scan: two changed lines (addition/removal). Introducing/removing commits 523fbde / 5d1b7aa. Revocation status unknown; values never printed. Human rotation/history remediation required. |
| F2 | PASS | Phase 2 agent/runtime logging review: policy.verdict and policy.approved/denied contain runId/tier/action; runner errors carry errorType only. No outcome/revision content logs. `test_policy_log_formatter_exposes_only_safe_metadata`, authenticated approval caplog and privacy canary tests. |
| F3 | PASS | Frontend token storage/URL/log spies, authenticated approval caplog and `test_websocket_canary_never_reaches_public_channels`; token fields repr=False, per-run memory dictionaries, no query-string authentication. Eval JSON whitelist/content audit. |
| F4 | PASS-WITH-DEVIATION | DataFlowTracker stores only hashes, byte lengths and source hosts; tests assert no actual value. AgentState intentionally has a redacted live last_observation and sanitized history to support the specified graph; terminal raw projections and historical checkpoints are now purged. |
| F5 | PASS | `test_ssrf_scenarios` asserts hostnames with no colon/slash; NavigationMonitor passes hostname(url), not full URL, to runner callback. No private query/path in recorded warning data. |
| F6 | PASS | `test_verifier_caps_and_untrusted_boundary`: parses captured message JSON and asserts exactly 50 of 60 elements, exactly last 3 of 6 summaries, no value field or query string. |
| F7 | PASS-WITH-DEVIATION | 7f5990b purges raw history; 6723da7 preserves already-sanitized public answers for exact API/live-smoke compatibility. Non-secret facts intentionally requested in the final answer may remain (e.g. a demo welcome username), while raw action/observation/history payloads and password/takeover input do not. `test_terminal_summary_preserves_only_intentionally_public_result` covers this distinction.  `test_terminal_checkpoints_remove_page_content_and_action_values[finished/failed/stopped]` scans all checkpoints and pending writes for page/typing canaries; 1s approval-timeout test verifies pending interrupts purged. Public final answer/error and safe counters remain; arbitrary observation/history content is removed. |
| F8 | PASS | `test_invalid_permission_response_never_echoes_user_domain`: invalid user URL yields 422 with only error envelope and no submitted domain. Main RequestValidationError handler does not serialize pydantic input/context. |
| G1 | PASS | backend/README.md graph, policy, outcome/approval, permissions, navigation-security and eval sections; ASCII approval sequence preserved. Terminal retention change documented in 7f5990b. |
| G2 | FAIL-FIXED | 43416c8: original fake demo attempted DNS verification for reserved example.test. Three-command README now explicitly disables private-address DNS checks only for the fake browser and restores true in real-browser instructions. Real HTTP fake-demo smoke finishes; fresh install/frontend commands verified. |
| G3 | FAIL-FIXED | 39474be adds LANGGRAPH_TESTED_VERSION as a comment, not a setting. scripts/audit_repo.py: 62 settings, no missing/extra example entries; all existing Phase 1 variables retained. |
| G4 | FAIL-FIXED | a71a961; created docs/phase2-acceptance.md in this audit, maps every Task 1–5 acceptance criterion to evidence and human checks; no claim of release acceptance while F1 remains open. |
| G5 | FAIL-FIXED | dee07a4; updated docs/phase2-notes.md: Phase 3 hooks at navigator/policy_check, Phase 4 trusted SkillProvider retrieval at planner re-entry; notes only, no later-phase implementation. |
| G6 | PASS-WITH-DEVIATION | Diff against last pre-LangGraph Phase 1 commit 8fc28ba: no renamed/removed envelope or existing action fields/routes. Authorized additions: internal revise action value, approval event metadata/pause variant, optional navigation warning/domain, approve/deny routes, approvalToken and permissions. Existing preview/control protocols untouched. AST comparison: zero removed event fields, zero removed routes; only approve/deny routes added. |

## Fixed during this audit

- 7f5990b: delete historical graph checkpoints/pending writes on every terminal path, clear approval IDs and retain one sanitized terminal diagnostic snapshot. No public API/event change.
- 8acb3b5: allow Authorization in approved-origin CORS preflight; no new allowed origins.
- 43416c8: correct fake-demo README environment prefix; secure real-browser defaults unchanged.
- 39474be: comment the tested LangGraph version in .env.example without creating a fake environment setting.
- 378f7f1: contextual config typing for the newly added regression tests; assertions unchanged.
- ac36d50: separate user-request cost minimum from resolved permissions; avoid interpreting a server-owned sub-cent ceiling as a new user override. Two new regressions, no existing assertions changed.
- 6723da7: preserve the public final answer with the existing public-result redaction policy; regression tests prove a normal demo username survives but a password value does not.
- dee07a4: replace obsolete readiness notes with current Phase 3/4 integration boundaries.
- a71a961: add the complete acceptance checklist with actual blockers and human checks.
- 6cdab93: coordinate paused HiDPI preview teardown with input-session readiness; preserve original browser assertions and timing.
- 7f0ab6f: explicitly supply fake-login credential provenance and redact labeled goal secrets in run.started; preserve all existing integration assertions.
- Final report/PR/evaluation documentation commit records all final command results.

## Still open (FAIL-OPEN)

| Severity | Item | Required resolution |
|---|---|---|
| blocker | F1: historical credential-shaped content in backend/.env.example, first present in 523fbde and removed in 5d1b7aa; revocation status unknown | Owner must revoke/rotate any real exposed credential, then coordinate an explicitly authorized history purge and remote/clone cleanup if zero history findings are required. Do not print patches containing the value. This audit does not silently rewrite shared history or claim revocation without provider evidence. |

## UNVERIFIED: human must check

1. **Historical credential remediation (release gate):** privately inspect the affected historical environment example, identify its owner, revoke it at the provider, set a new key only in an ignored local environment, and confirm the old key is unusable. Coordinate history cleanup with repository owners and all clones. Rerun `python scripts/audit_repo.py`; rotating alone does not remove a historical pattern finding.
2. **Paid live evaluations (E5):** after explicit billing authorization, activate the backend environment, set OPENROUTER_API_KEY and model variables privately, then run `pytest tests/eval/scenarios/test_live_eval.py -m live_eval -q -ra`. It starts the local fake-data site; examine five newly appended result records for correctness, steps and cost. No paid task result, step count or cost is claimed here.
3. **Human preview/takeover review:** run the real-browser backend and frontend, compare preview text at DEVICE_SCALE_FACTOR=1 and 2, request takeover on the local login page, type demo credentials, submit and resume. Repeat in API headed mode with a visible window. Check resized/letterboxed click alignment and Stop. Automated headed/browser tests do not establish subjective sharpness or human usability.
4. **Approval UI manual review:** run a local form task with explicit local-development network settings, wait for Tier 2 approval, inspect the safe action summary/domain, approve once, then run again and deny. Verify Stop remains reachable, stale requests expire, and preview/control behavior is unchanged.
5. **Long-lived deployment:** terminal summaries, run/event records and capability dictionaries are process-resident without general historical TTL. The finite 10-run stress gate is not proof of unbounded service memory stability. Actual peer-IP pinning/egress enforcement and initial-popup public redirect usability need separately reviewed deployment work.

## Out of scope (Phase 3+)

Injection classifier, adversarial attack suite, trusted skill library/retriever implementation, accounts, durable database/shared multi-worker ownership and durable browser recovery. Integration notes only are in phase2-notes.md. Domain heuristics and hash-only data-flow are intentionally not semantic transaction verification or a general exfiltration detector.
