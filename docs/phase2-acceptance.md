# Phase 2 acceptance checklist

**Release acceptance is blocked by F1 (historical credential remediation) and A9 (the full backend gate fails the unchanged HiDPI iframe checkbox test and two opt-in legacy login fixtures conflict with current policy).**
Automated passing results do not establish key revocation, paid model correctness or human usability.
The authoritative gate counts and 55-item audit are in [phase2-verification.md](phase2-verification.md).

| Criterion | Requirement | Status | Verification |
|---|---|---|---|
| T1.1 | Quality gates and preserved Phase 1 tests | FAIL-OPEN (A9 full gate) | Automated gates; A9 historical authorized deviations; audit A9. |
| T1.2 | Fake multi-sub-goal graph and validated-event ordering | PASS | test_graph_order_events_and_final_counters; audit A5/A6. |
| T1.3 | Stop, pause, budgets and loop detection | PASS | test_stop_during_inflight_io; graph/control/budget tests; audit A7. |
| T1.4 | JSON state and interrupt recovery | PASS | test_graph_state_is_json_serializable_and_hashes_values; test_interrupt_checkpoint_resumes_with_command; audit A2/A8. |
| T1.5 | Pinned LangGraph and verified imports | PASS | langgraph==1.2.17; version constant/import inspection; audit A1. |
| T1.6 | Existing public behavior preserved | PASS | Authorized additive changes only; unchanged preview/control tests; audit G6. |
| T2.1 | All gates and existing tests pass | FAIL-OPEN (A9 full gate) | Final gates in verification report; audit A9. |
| T2.2 | Policy and browser both block private navigation | PASS | test_private_navigation_denied_by_policy_and_browser_boundary; audit B3/D9. |
| T2.3 | Tier 2 interrupt and explicit approved/denied resume | PASS | test_real_graph_approval_interrupt_and_resume; audit B6. |
| T2.4 | Cross-domain extraction requires approval | PASS | test_extraction_to_other_domain_requires_approval; audit B4/B5. |
| T2.5 | Every policy action emits step.validated | PASS | test_policy_three_denials_never_act_and_have_gap_free_events; audit B5. |
| T2.6 | Safe verdict logs | PASS | test_policy_log_formatter_exposes_only_safe_metadata; caplog tests; audit F2. |
| T2.7 | SSRF ranges with injected DNS | PASS | test_private_and_metadata; test_injected_dns_all_answers_checked; audit B3. |
| T3.1 | Backend/frontend quality gates and legacy tests | FAIL-OPEN | Final gate results; audit A9. |
| T3.2 | Failed sub-goal revises, retries/replans and completes | PASS | test_one_failed_check_revises_then_retries_with_fresh_observation; replanning eval; audit C3/C5. |
| T3.3 | Tier 2 approval dialog and authenticated execution | PASS | Graph/API approval tests plus ApprovalDialog.test.jsx; audit C7/C11. |
| T3.4 | Deny returns to navigator and re-proposal | PASS | test_denial_then_new_request_rejects_old_id; DenyAndRepropose eval; audit C8. |
| T3.5 | Stale ID 422, missing token 401, timeout | PASS | test_wrong_token_stale_id_duplicate_and_unknown; timeout regression; audit C7/C9. |
| T3.6 | Verifier prompt bounded and logs private | PASS | test_verifier_caps_and_untrusted_boundary; safe logging review; audit C1/F6. |
| T3.7 | Approval token private in memory | PASS | useTaskOrchestrator.approval.test.jsx storage/log spies; audit C10. |
| T3.8 | Only authorized additive contract changes | PASS | Phase 1 baseline diff and README; audit G6. |
| T4.1 | Full gates and existing tests | FAIL-OPEN | Final verification results; audit A9. |
| T4.2 | Run-scoped domain restriction and approval | PASS | test_state_permissions_restrict_domains_and_submission; audit D1/D2. |
| T4.3 | JS/meta/form redirects blocked; hostname-only state | PASS | test_browser_blocks_page_driven_navigation; SSRF evals; audit D5/D7. |
| T4.4 | 23 non-live scenarios and JSON/report 100% latest pass | PASS | Standalone eval plus latest-record scan; audit E1/E2/E3/E4. |
| T4.5 | At least 4/5 live tasks and per-task costs | NEEDS HUMAN CHECK | NEEDS HUMAN CHECK: explicit paid-eval authorization then run the five live scenarios; audit E5. |
| T4.6 | Tokens absent from evals/logs | PASS | test_recorder_excludes_capabilities_and_content; caplog/storage spies; audit E6/F3. |
| T4.7 | Invalid domain permissions return 422 | PASS | test_permissions_api_validation_and_effective_response; non-echo regression; audit D1/F8. |
| T5.1 | Every audit ID has evidence/status | PASS | 55-row verification table; audit A1–G6. |
| T5.2 | All automated gates pass without weaker tests | FAIL-OPEN | Final gate results; no existing test modified in audit; audit A9. |
| T5.3 | Privacy canary and process-leak check | PASS | 12 targeted privacy/stop/network tests pass; ten mixed hybrid runs plus three concurrent runs leave no owned processes; RSS delta 32.42 MiB; audit F3/F7. |
| T5.4 | No blocker remains | FAIL-OPEN (blocker) | BLOCKED: historical credential finding plus unchanged HiDPI test failure; owner remediation and a separately authorized preview fix are required; audit F1/A9. |
| T5.5 | No invented result | PASS | Actual command summaries and explicit unverified/human checks; audit E5/F1. |
| T5.6 | Non-live latest results 100% pass | PASS | 23 latest scenario records; historical failures retained; audit E2/E3. |

## Required human checks

- **Credential exposure:** privately identify the historical key in backend/.env.example, revoke/rotate it and verify revocation; coordinate history/clone cleanup before declaring a clean history. Never paste the value into a report.
- **Paid accuracy/cost:** after billing authorization, set the key/model privately and run `pytest tests/eval/scenarios/test_live_eval.py -m live_eval -q -ra` from backend. Check each new JSON result and the expected fake-site answers; require at least four of five correct.
- **Approval UX:** run the local form task with deliberate local-development network permissions. Inspect safe summary/domain, approve once, deny on another run, verify fresh proposal and Stop while the dialog is open. Confirm tokens never appear in the address bar or persistent storage.
- **Headless/headed takeover:** open the local login page, pause, type fake demo credentials through the preview, submit, resume and confirm success; repeat in API headed mode. Check input at DSF 1 and 2 in resized and letterboxed previews.
- **Sharpness:** compare the preview to the same normal browser page at 100% zoom at DSF 1 and 2 with `?debug=1`. Match frame/canvas/native pixel sizes, and visually confirm readable text. Automated headed tests are not a substitute for this subjective check.

## Accepted limitations

Nodes perform intentional injected effects; routes are pure. max_attempts retains the documented
revision-after-initial-attempt semantics. Revision feedback uses safe categories instead of arbitrary
page-derived prose. Initial-popup HTTP redirects fail closed; DNS rechecks do not pin the connected
peer. In-memory summaries have no general historical TTL. Later-phase classifiers and skill libraries
are not included. Public final answers may intentionally contain requested non-secret page facts;
arbitrary terminal observations/history are not retained in MemorySaver.

- **HiDPI quality-gate failure:** retain `test_hidpi_takeover_iframe_input_and_capture_resume` unchanged. Reproduce with `pytest -q tests/test_preview_cdp.py::test_hidpi_takeover_iframe_input_and_capture_resume`; authorize a preview/input synchronization investigation separately, then rerun the full backend gate. Current failure is recorded, not waived. Also resolve the two opt-in PinchTab login-fixture provenance conflicts without weakening password policy or privacy assertions.
