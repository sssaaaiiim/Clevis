# Phase 2 completion check

**Phase 2 implementation check completed; the final automated quality gates pass. Release remains blocked by the historical credential finding.**

This check follows commit 6915031 and reads AGENTS.md first. No paid model calls are authorized.
The checklist below expands combined bullets (interrupt/Command; DNS injection/no external DNS;
three-deny regression existence/behavior; both approval authorization paths; README topics)
to the requested summary counts. It does not invent additional implementation requirements.

## Environment

- Python 3.14.4; backend/.venv exists. `pip show langgraph`: Version 1.2.17;
  LANGGRAPH_TESTED_VERSION=1.2.17, exact match. Playwright 1.64.0; installed FastAPI 0.156.4.
- AGENTS.md: Phase 2 additions present, including LangGraph, policy/SSRF/privacy and working rules.
- backend/.venv `pip check`: `No broken requirements found.`
- OPENROUTER_API_KEY in backend/.env: **yes** (presence only inspected, no value printed or copied).
- Display configured: yes; headed gate requested. Paid `live`/`live_eval` opt-ins remain disabled.
- Installed imports and signatures inspected before use: langgraph.types.interrupt(value, *, response_schema=None),
  langgraph.types.Command(*, graph=None, update=None, resume=None, goto=()),
  langgraph.checkpoint.memory.MemorySaver and langgraph.graph.StateGraph/START/END.
  Graph import compiled successfully; runtime checkpointer identity true; JSON roundtrip true.
- Fresh /tmp/phase2-check-venv: Python 3.14.4, LangGraph 1.2.17 (constant matches), Playwright 1.64.0, FastAPI 0.162.0, pydantic 2.14.1; all required LangGraph imports re-verified. Newer FastAPI/pydantic resolution is permitted by bounded dependencies.
- Frontend folder is `front end/`, not the template's `frontend/`; npm lockfile preserved.

## Summary table

| Area | Items checked | EXISTS-PASS | EXISTS-FAIL | MISSING | PARTIAL |
|---|---:|---:|---:|---:|---:|
| 1A LangGraph graph | 10 | 10 | 0 | 0 | 0 |
| 1B Policy engine | 12 | 12 | 0 | 0 | 0 |
| 1C Outcome + approvals | 14 | 14 | 0 | 0 | 0 |
| 1D Permissions + SSRF | 9 | 9 | 0 | 0 | 0 |
| 1E Config vars | 16 | 16 | 0 | 0 | 0 |
| 1F Docs | 6 | 6 | 0 | 0 | 0 |

These are final implementation-item statuses backed by the gates below. They do not waive the separate historical-secret security failure. No requested implementation item is missing.

## Item evidence

### 1A LangGraph graph

| ID | Check | Status | Evidence |
|---|---|---|---|
| 1A.1 | Graph exists and compiles | EXISTS-PASS | backend/app/agent/graph.py:29 build_graph; import succeeded in environment probe. |
| 1A.2 | All eight required node modules | EXISTS-PASS | backend/app/agent/nodes/; planner, navigator, policy_check, executor, outcome_check, revise, approval_gate, finish imported by graph.py:7–15. |
| 1A.3 | AgentState required fields | EXISTS-PASS | backend/app/agent/state.py:63; all 18 requested fields inspected; pydantic model with JSON-mode serialization. |
| 1A.4 | JSON serialization | EXISTS-PASS | Environment probe round trip true; test_graph_state_is_json_serializable_and_hashes_values. |
| 1A.5 | Runner uses graph streaming | EXISTS-PASS | backend/app/agent/runner.py:159 agent_graph.astream; the outer loop only bridges interrupt/resume, not action execution. |
| 1A.6 | MemorySaver attached | EXISTS-PASS | backend/app/agent/graph.py:27/55; runtime identity check agent_graph.checkpointer is checkpointer returned true. |
| 1A.7 | interrupt import verified | EXISTS-PASS | langgraph.types.interrupt imports successfully; installed signature inspected; approval_gate.py:4. |
| 1A.8 | Command import verified | EXISTS-PASS | langgraph.types.Command imports successfully; installed signature inspected; runner.py:10/178. |
| 1A.9 | Pure routing | EXISTS-PASS | backend/app/agent/routing.py:6; AST scan and test_routes_are_pure verify no mutation/I/O; test_revision_routes and test_failed_outcome_at_max_routes_to_finish. |
| 1A.10 | Existing Phase 1 tests preserved and pass | EXISTS-PASS | Full before/final suite below includes existing tests; no application/test changes made in this check. |

### 1B Policy engine

| ID | Check | Status | Evidence |
|---|---|---|---|
| 1B.1 | Required policy modules | EXISTS-PASS | backend/app/agent/policy/{tiers,domains,dataflow,validator}.py exist. |
| 1B.2 | ActionValidator implementation | EXISTS-PASS | backend/app/agent/policy/validator.py:25/83 supports validate(RunRecord or AgentState, Action); structural protocol backend/app/interfaces/validator.py:33. Full mypy gate verifies injection. |
| 1B.3 | All risk tiers | EXISTS-PASS | backend/app/agent/policy/tiers.py:20 classify_action; test_ordered_tier_rules and test_keyboard_submit_and_independent_switches. |
| 1B.4 | Private ranges and metadata | EXISTS-PASS | domains.py:9 METADATA_HOSTS and :76 is_private_address use ipaddress.is_global, including mapped IPv6. test_private_and_metadata parameterizes all requested ranges. |
| 1B.5 | Injected DNS resolver | EXISTS-PASS | domains.py:76 Resolver argument; validator.py:26 resolver injection; test_injected_dns_all_answers_checked. |
| 1B.6 | DNS tests do not use external DNS | EXISTS-PASS | test_policy_domains.py:60 patches event-loop getaddrinfo; policy/browser guard tests supply lambda resolvers. Socket references include intentional local HTTP/WebSocket fixtures, not evidence of external DNS. |
| 1B.7 | Hash-only data flow | EXISTS-PASS | dataflow.py:22 FlowEntry only domains/byte_len; :27 first-500-char SHA-256; :44 stores hash-keyed entries. test_hash_only_cross_domain_and_same_domain. |
| 1B.8 | Approval interrupt | EXISTS-PASS | nodes/approval_gate.py:47 interrupt payload; test_real_graph_approval_interrupt_and_resume. |
| 1B.9 | Validation event on every verdict | EXISTS-PASS | nodes/policy_check.py:56 emits before verdict branch; test_policy_three_denials_never_act_and_have_gap_free_events plus approval/allow graph tests. |
| 1B.10 | approval.required includes approval_id | EXISTS-PASS | nodes/policy_check.py:88/109 creates UUID4 and populates ApprovalData; API/graph approval tests. |
| 1B.11 | Three-deny regression exists | EXISTS-PASS | tests/test_policy_graph.py:125 test_policy_three_denials_never_act_and_have_gap_free_events. |
| 1B.12 | Three-deny termination works | EXISTS-PASS | policy_check.py:76 checks consecutive_denials>=3; the named regression runs in full gate, asserts no browser act and gap-free events. |

### 1C Outcome + approvals

| ID | Check | Status | Evidence |
|---|---|---|---|
| 1C.1 | Real outcome call | EXISTS-PASS | nodes/outcome_check.py:64 calls check_outcome via injected LLM; agent/outcomes.py:66 calls llm.propose; test_verified_subgoals_complete_and_count_verifier_usage. |
| 1C.2 | Real revision builder | EXISTS-PASS | nodes/revise.py:14 calls build_revision_message; test_revision_is_bounded_and_never_echoes_page_or_target_content; test_revision_preserves_completed_work_and_bounds_attempts. |
| 1C.3 | No auto-approval stub | EXISTS-PASS | nodes/approval_gate.py:47 interrupt; test_real_graph_approval_interrupt_and_resume. |
| 1C.4 | Approve endpoint | EXISTS-PASS | api/runs.py:77 POST /{run_id}/approve; test_authenticated_approval_and_denial (approve path). |
| 1C.5 | Deny endpoint | EXISTS-PASS | api/runs.py:92 POST /{run_id}/deny; test_authenticated_approval_and_denial (deny path). |
| 1C.6 | Approve bearer auth | EXISTS-PASS | api/runs.py:65/85 authorize_approval constant-time token comparison; test_wrong_token_stale_id_duplicate_and_unknown. |
| 1C.7 | Deny bearer auth | EXISTS-PASS | api/runs.py:100 uses same authorization function; test_authenticated_approval_and_denial plus frontend hook token-header test. |
| 1C.8 | Pending ID match and 422 | EXISTS-PASS | runtime.py:162 snapshot pending_approval_id comparison; api/runs.py:87/102 StaleApproval→422; test_wrong_token_stale_id_duplicate_and_unknown. |
| 1C.9 | Approval timeout | EXISTS-PASS | config.py:61; runner.py:174 asyncio.wait_for; test_approval_timeout_erases_interrupt_history uses 1 second. |
| 1C.10 | Create returns approvalToken | EXISTS-PASS | api/runs.py:39/53; test_authenticated_approval_and_denial and frontend approval hook test. |
| 1C.11 | Frontend dialog | EXISTS-PASS | front end/src/components/ApprovalDialog.jsx; ApprovalDialog.test.jsx and test_real_react_approval_dialog_round_trip. |
| 1C.12 | Token kept out of localStorage | EXISTS-PASS | useTaskOrchestrator.js:58 React state; :435 Authorization only. Storage/log spy tests in useTaskOrchestrator.approval.test.jsx; security review below. |
| 1C.13 | Verifier limits | EXISTS-PASS | agent/outcomes.py:39 elements[:50], :44 history[-3:]; test_verifier_caps_and_untrusted_boundary; test_outcome_session_model_and_eighty_token_cap. |
| 1C.14 | Outcome model config | EXISTS-PASS | config.py:60 llm_outcome_model; test_outcome_session_model_and_eighty_token_cap validates override and primary default. |

### 1D Permissions + SSRF

| ID | Check | Status | Evidence |
|---|---|---|---|
| 1D.1 | RunPermissions model | EXISTS-PASS | agent/policy/permissions.py:13; test_permission_bounds_and_global_merge. |
| 1D.2 | Optional request permissions | EXISTS-PASS | api/runs.py:25 permissions optional; test_permissions_api_validation_and_effective_response. |
| 1D.3 | GET resolved permissions | EXISTS-PASS | api/runs.py:108 returns RunRecord; test_permissions_api_validation_and_effective_response checks effective values. |
| 1D.4 | Collapsed permissions panel | EXISTS-PASS | front end/src/components/PermissionsPanel.jsx:33 native details/summary; PermissionsPanel.test.jsx tests collapsed/default/hidden states. |
| 1D.5 | Frame navigation hook | EXISTS-PASS | browser/playwright_driver.py:695 registers framenavigated on each page; test_browser_blocks_page_driven_navigation, test_pinchtab_action_keeps_playwright_navigation_hook. |
| 1D.6 | SSRF testsite page | EXISTS-PASS | testsite/ssrf-redirect.html contains selectable JS, meta-refresh and form scenarios; test_browser_blocks_page_driven_navigation. |
| 1D.7 | Strict mode config and behavior | EXISTS-PASS | config.py ssrf_strict_mode; test_ssrf_scenarios[StrictModeFailsRun] and [NonStrictModeWarns] in tests/eval/scenarios/test_ssrf_eval.py. |
| 1D.8 | Domain-only block state | EXISTS-PASS | agent/state.py:65 ssrf_blocks; navigation monitor and eval assertions check domains; test_frame_navigation_hook_performs_fresh_dns_check. |
| 1D.9 | Evaluation harness | EXISTS-PASS | backend/tests/eval/ has conftest.py, recorder, base and policy/outcome/approval/revision/SSRF scenario files; standalone gate below. |

### 1E Config vars

| ID | Check | Status | Evidence |
|---|---|---|---|
| 1E.1 | ALLOWED_DOMAINS | EXISTS-PASS | backend/.env.example:48; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.2 | BLOCKED_DOMAINS | EXISTS-PASS | backend/.env.example:49; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.3 | BLOCK_PRIVATE_NETWORK | EXISTS-PASS | backend/.env.example:50; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.4 | REQUIRE_APPROVAL_FOR_SUBMIT | EXISTS-PASS | backend/.env.example:51; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.5 | REQUIRE_APPROVAL_FOR_DOWNLOAD | EXISTS-PASS | backend/.env.example:52; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.6 | REQUIRE_APPROVAL_FOR_UPLOAD | EXISTS-PASS | backend/.env.example:53; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.7 | REQUIRE_APPROVAL_FOR_SEND | EXISTS-PASS | backend/.env.example:54; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.8 | AUTO_ALLOW_SAME_DOMAIN_DATA_FLOW | EXISTS-PASS | backend/.env.example:55; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.9 | MAX_DATA_FLOW_BYTES | EXISTS-PASS | backend/.env.example:56; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.10 | POLICY_LOG_VERDICTS | EXISTS-PASS | backend/.env.example:57; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.11 | APPROVAL_TIMEOUT_S | EXISTS-PASS | backend/.env.example:47; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.12 | SSRF_STRICT_MODE | EXISTS-PASS | backend/.env.example:64; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.13 | LLM_OUTCOME_MODEL | EXISTS-PASS | backend/.env.example:46; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.14 | SUBGOAL_MAX_STEPS | EXISTS-PASS | backend/.env.example:44; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.15 | SUBGOAL_MAX_ATTEMPTS | EXISTS-PASS | backend/.env.example:45; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |
| 1E.16 | MAX_HANDOFFS | EXISTS-PASS | backend/.env.example:43; corresponding Settings field; test_env_example_exactly_matches_settings and audit parity scan. |

### 1F Docs

| ID | Check | Status | Evidence |
|---|---|---|---|
| 1F.1 | Verification report | EXISTS-PASS | docs/phase2-verification.md exists; all 55 IDs have statuses/evidence, including unresolved historical credential finding. |
| 1F.2 | Acceptance checklist | EXISTS-PASS | docs/phase2-acceptance.md exists; 34 criteria and exact human-check instructions. |
| 1F.3 | Evaluation JSON | EXISTS-PASS | docs/eval-results.json exists; latest 23 scenario records checked below; append-only earlier failures retained. |
| 1F.4 | Evaluation report | EXISTS-PASS | docs/phase2-eval-report.md exists; policy6/outcome4/approval5/revision3/SSRF5 counts and paid-test exclusions. |
| 1F.5 | README graph/outcome/approval | EXISTS-PASS | backend/README.md:3 graph section; :1008 outcome/revision/approval including ASCII sequence. |
| 1F.6 | README permissions/SSRF | EXISTS-PASS | backend/README.md:1088 per-run permissions; :1126 SSRF/redirect/rebinding and strict-mode limitations. |

## Gate results — before and after

All commands ran from backend unless the path indicates root. The first full suite ran before
the fix; static, standalone evaluation and privacy checks followed during investigation. The final
full suite ran only after a84d00e, using newly installed dependencies in /tmp/phase2-check-venv.
No paid calls were made. Source/test assertions were not changed to get a green result.

| Stage | Exact command / scope | Raw summary | Exit |
|---|---|---|---:|
| before-backend | `.venv/bin/python -m pytest -q -ra` | `1 failed, 543 passed, 25 skipped in 266.63s (0:04:26)` | 1 |
| before-headed | `.venv/bin/python -m pytest -q -m headed -ra` | `4 passed, 565 deselected in 17.42s` | 0 |
| before-eval | `.venv/bin/python -m pytest tests/eval/ -q -ra` | `24 passed, 5 skipped in 75.38s (0:01:15)` | 0 |
| before-ruff | `.venv/bin/python -m ruff check .` | `All checks passed!` | 0 |
| before-mypy | `.venv/bin/python -m mypy .` | `Success: no issues found in 161 source files` | 0 |
| before-pip | `.venv/bin/python -m pip check` | `No broken requirements found.` | 0 |
| privacy | `.venv/bin/python -m pytest tests/ -k "canary or privacy or log" -v -ra` | `================ 20 passed, 5 skipped, 545 deselected in 37.88s ================` | 0 |
| create-venv | `python3 -m venv /tmp/phase2-check-venv` | `Created successfully.` | 0 |
| install | `/tmp/phase2-check-venv/bin/python -m pip install -e './backend[dev]'` | `Completed successfully; dependency installer/browser setup exit 0.` | 0 |
| chromium | `/tmp/phase2-check-venv/bin/playwright install chromium` | `Completed successfully; dependency installer/browser setup exit 0.` | 0 |
| final-backend | `/tmp/phase2-check-venv/bin/python -m pytest -q -ra` | `545 passed, 25 skipped in 218.14s (0:03:38)` | 0 |
| final-ruff | `/tmp/phase2-check-venv/bin/python -m ruff check .` | `All checks passed!` | 0 |
| final-mypy | `/tmp/phase2-check-venv/bin/python -m mypy .` | `Success: no issues found in 161 source files` | 0 |
| final-pip | `/tmp/phase2-check-venv/bin/python -m pip check` | `No broken requirements found.` | 0 |
| separate gate | `PINCHTAB_URL=managed .venv/bin/pytest -q -m pinchtab -ra` | `15 passed, 555 deselected in 39.30s` | 0 |
| separate gate | `npm ci --no-audit --no-fund --cache /tmp/wto-npm-cache` | `added 435 packages in 6s` | 0 |
| separate gate | `npm run build` | `✓ built in 3.45s` | 0 |
| separate gate | `npm test` | `Test Files  12 passed (12); Tests  57 passed (57)` | 0 |

The original failing assertion was `channel.received == channel.acked`: 48 versus 47 at
backend/tests/test_preview_cdp.py:249. The new deterministic shutdown regression failed before the
fix with “Supervisor cancellation must not cancel an in-flight frame ack”; targeted after-fix
result was `3 passed in 2.73s`. No result is substituted for the original failure.

Skip investigation:

- Full suite: five live_eval cases require explicit -m live_eval; five live cases require explicit
  -m live; 15 PinchTab cases require an authenticated service opt-in. PinchTab cases passed separately.
- Standalone eval: five paid live_eval skips are legitimate. All 23 non-live scenarios plus recorder
  privacy test passed. A configured key is not permission to incur charges.
- Privacy selector: one live_eval and one live case skip for billing opt-in; three PinchTab cases
  skip for service opt-in, then pass as part of the separate managed run. Other deselections reflect
  the requested -k filter, not test disabling.
- Headed: actual display-backed gate ran; its result above is not a human visual-quality claim.

## Fixed during this check

- a84d00e — preview: shield outstanding ack tasks while the supervisor drains them during detach.
  Baseline full suite failed test_animation_throttle_and_nonreading_viewer_do_not_block_browser
  (`received=48`, `acked=47`, tests/test_preview_cdp.py:249). New deterministic regression
  test_shutdown_keeps_inflight_ack_alive_when_supervisor_is_cancelled first failed (ack task cancelled),
  then passed after the implementation fix. Targeted run with both original ack/throttling tests:
  `3 passed in 2.73s`. Existing assertions and cleanup deadlines are unchanged. README updated.
- No missing Phase 2 node/API/component/config implementation found. All final quality gates pass.
- No existing test source, public API route, event field name or protocol was modified in this check.

## Still missing or broken — NEEDS DECISION

**Blocker — historical credential finding.** The previous audit found a credential-shaped blob in
backend/.env.example in history (introduced 523fbde, removed 5d1b7aa; no value disclosed). A local
code fix cannot establish provider revocation or safely rewrite all shared clones. The repeated scan still reports exactly that finding (see below). Proposed approach: owner privately verifies and
revokes/rotates any real exposed key, then chooses coordinated history cleanup with affected
remotes/clones. Do not rewrite shared history or claim revocation without explicit authorization/evidence.

## Security spot checks

| Check | Result | Evidence |
|---|---|---|
| 1. Secret scan / env parity | **FAIL — NEEDS DECISION (blocker)** | scripts/audit_repo.py reports one historical credential-shaped blob at backend/.env.example (historical line 1), object 461022d91abc; zero working-tree findings, .env ignored, none tracked. 62 settings, no missing/extra example variables. Final scan: exit 1; 756 historical blobs /277 working files scanned, exactly one history finding. No zero-findings acceptance claim. |
| 2. Approval token storage/logging | PASS | Production references only at front end/src/hooks/useTaskOrchestrator.js:58/253/429/435/443 (state, response destructuring, guard, bearer header, callback dependency). No storage/log/URL sink. Existing storage/log spies run in frontend tests. The supplied grep would discard every line containing approvalToken due to its final exclusion; direct reference/sink review was used instead. |
| 3. Data-flow raw values | PASS | dataflow.py:27–28 hashes transient value[:500]; :43–54 stores digest keys, domains and byte lengths; :56–73 only inspects transient input and looks up digest. Every value/text/content hit reviewed. test_hash_only_cross_domain_and_same_domain asserts original text absent from serialized state. |
| 4. Eval long strings | PASS — 521 historical records; longest string 63 chars; zero strings over 300. Latest 23/23 scenarios pass. | Scan every string-valued field; no content printed. |
| 5. Log/privacy capture tests | PASS — 20 passed, 5 opt-in skipped, 545 deselected in 37.88s; skips investigated above | Exact requested -k selector and skips recorded above. |
| 6. MemorySaver terminal state | PASS | tests/test_phase2_hardening.py:23–63 parametrizes finished/failed/stopped and asserts page/typed canaries absent from all checkpoint histories; :66–83 checks timed-out interrupts and approval IDs purged. test_terminal_summary_preserves_only_intentionally_public_result permits only intentionally public sanitized answers. These tests run in the full suite. |

## UNVERIFIED: human must check

1. **Approval flow:** start authenticated local PinchTab, backend and frontend using the README;
   serve the fake testsite (`python scripts/serve_testsite.py`). For local-only testing explicitly set
   BLOCK_PRIVATE_NETWORK=false; never use that exception on real sites. Use the goal
   "Open http://127.0.0.1:8765/form.html, fill the contact form with fake demo details and submit it."
   Leave submit approval enabled. Inspect the safe summary/domain in the modal, click Approve once,
   confirm run.resumed precedes execution and the final confirmation/result. Verify Stop remains usable.
2. **Denial flow:** repeat that goal, click Deny with an optional short explanation. Confirm the
   timeline records denial, the actor re-proposes without executing the denied action, then approve
   an acceptable proposal and confirm completion. If the real model cannot adapt, record its result;
   do not assume the scripted test proves model reliability.
3. **Agent/browser SSRF flow:** with BLOCK_PRIVATE_NETWORK=true and SSRF_STRICT_MODE=true,
   an explicit agent navigation to the localhost fixture itself must be denied. To test its redirects,
   use the test-only exact source-URL exception and injected public resolver in
   `pytest -q tests/test_navigation_monitor.py::test_browser_blocks_page_driven_navigation -ra`.
   Repeat with a visible Chromium display if desired using an isolated test harness. Check each
   JS/meta/form target is blocked before network contact, browser clears the page, and stored blocks
   contain only domains. Do not globally disable protection and claim a redirect-security test.
4. **Preview/takeover:** use the local login page with deliberate local-development permissions.
   Run headless, Take over, type only fake demo credentials, submit and Resume. Verify fresh observation
   and completion; repeat headed with a visible window. At DSF 1 and 2 resize/letterbox the preview and
   check click alignment, typing, final frame, Stop and subjective text sharpness at 100% zoom.
5. **Live eval, only after explicit billing approval:** activate backend/.venv and privately configure
   OPENROUTER_API_KEY/LLM_MODEL_PRIMARY, then from backend run
   `pytest tests/eval/scenarios/test_live_eval.py -m live_eval -q -ra`.
   Inspect the five newly appended docs/eval-results.json records: correct fake-site results,
   pass status, event/assertion booleans, steps, token and cost counters. Compare timestamps/model
   and costs in the OpenRouter activity/billing page; confirm remaining budget. Do not put credentials
   in commands, screenshots, reports or URLs. No live correctness/cost is claimed by this check.

## Final artifact checks

All 67 checklist rows have a status; summary counts agree with the per-item table. The final JSON
scan checks all records, not just successes; old failures remain recorded. Only hash/length data
is retained by the data-flow tracker. Terminal MemorySaver privacy permits an already-sanitized,
intentionally public final answer, not raw observations or action values. This is the documented
Phase 2 deviation, covered by test_terminal_summary_preserves_only_intentionally_public_result.

**Acceptance limitation:** security checks 2–6 pass; check 1 fails solely on the historical credential.
All quality gates pass, but “all six security checks pass with zero findings” is not met. Owner
remediation is required; no paid model or human UX verification is claimed.

## Out of scope (Phase 3+)

Injection classifier/adversarial attack suite; skill library/retriever implementation; accounts,
shared durable database/multi-worker ownership. Existing DNS rechecks do not pin the actual connected
peer; production egress controls remain a documented deployment limitation. Initial popup redirects
fail closed. In-memory run summaries have no general historical TTL; no unbounded-memory guarantee.
