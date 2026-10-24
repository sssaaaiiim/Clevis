# Phase 2 Task 2 — policy engine verification

Status: **automated acceptance passed** — 454 passed, 20 existing opt-in skips; Ruff and mypy pass.

The user explicitly approved the two legacy test updates after reviewing their consequences.
Commit `6d55807` configures local fixtures and replaces the obsolete auto-approval expectation
with real interrupt/consent/resume assertions. Production protections remain enabled. The
pre-approval failures below are historical evidence; the authorized follow-up is recorded below.
No preview/input protocol, UI, route, or action schema was changed. Paid live-model tests were not run.

## Implementation and commits

| Commit | Change |
|---|---|
| f1f55d9 | Secure configuration, startup domain parsing, ordered risk rules, observation metadata models. |
| b532370 | Injected-resolver SSRF tests and per-run async production DNS cache. |
| f66443f | Serializable hash-only data-flow tracker and atomic byte limits. |
| d6e0983 | PolicyValidator, verdict compatibility, graph allow/deny/approval routing and event emission. |
| 01996e0 | Production interrupt/Command lifecycle, retained resources, approved/denied graph tests. |
| bf66a98 | Default service injection, browser request guards, DOM policy metadata and SSRF boundary test. |
| 5707386 | Paused checkpoint status, sanitized approval error channels and safe structured logs. |
| 8b27510 | Reject duplicate decisions after queue consumption during graph resume. |
| 6d55807 | Authorized local fixture configuration, strict policy fixtures and real approval test. |

RunService now constructs PolicyValidator for each run. AllowAllValidator remains an explicitly
injectable trivial dependency for existing unit callers; production has no fake/localhost bypass.
State-aware validators receive current AgentState through an interface extension while the
legacy ActionValidator RunRecord signature remains usable. Verdict.decision exposes approve;
the existing step.validated event still uses its original approval wire spelling.

Approval.required keeps its existing schema and contains a redacted action. Section 7 of this
task expressly requires an additive run.paused data variant: reason=approval with a typed
request. This addition is documented in backend/README.md; takeover/handoff payloads and
routes remain intact. There are no approval HTTP endpoints yet. An internal decision bridge
feeds Command(resume=...) into the same live background task/thread, with the browser retained.
Takeover resume rejects an approval pause. Stop cancels the interrupt wait and cleans up.

## Evidence

From backend:

```sh
.venv/bin/pytest -q tests/test_policy_tiers.py tests/test_policy_domains.py tests/test_policy_dataflow.py tests/test_policy_validator.py tests/test_policy_graph.py tests/test_policy_browser_boundary.py
.venv/bin/ruff check .
.venv/bin/mypy .
```

- New policy tests: **74 passed in 1.98s**. These include an additional duplicate-decision
  regression after the main full-suite attempt was started.
- Ruff: **All checks passed**.
- Mypy: **Success: no issues found in 125 source files**.
- All unit/graph policy tests inject fake DNS answers or mock getaddrinfo. They call no LLM
  service and open no browser. One separate browser-boundary test launches local Chromium
  and proves policy-denied loopback navigation is also BLOCKED_URL in the installed driver;
  direct page.goto is blocked by context routing before reaching a local server.
- test_real_graph_approval_interrupt_and_resume[approved/denied] proves checkpoint interruption,
  no premature act/cleanup, one approval.required and paused/resumed pair, continued execution,
  cleared pending state, and final resource closure. The denied action never reaches act.
- test_policy_three_denials_never_act_and_have_gap_free_events proves SSRF denial, three
  validations and terminal failure without a browser action.
- test_extraction_to_other_domain_requires_approval proves extract recording on source.example,
  FLAG/Tier 2 before type on destination.example, hash-only tracker state and sanitized logs.
- test_stop_during_approval_closes_resources_within_two_seconds exercises cancellation while
  paused, closed browser, run.stopped and a terminal checkpoint with no pending graph nodes.
- test_duplicate_decision_cannot_preapprove_the_next_action proves consuming the queue does
  not reopen a window for a second decision to consent to a later action.
- test_policy_log_formatter_exposes_only_safe_metadata verifies tier/action/runId are present
  in serialized logs and an arbitrary canary-valued extra field is excluded.

Restricted-sandbox graph diagnostics initially stalled with stream-fd permission errors. The
same tests pass with normal asyncio signaling outside that restriction. No timing limit or
assertion was changed to address that environment issue.

## Pre-approval legacy tests: historical conflict

First complete secure-default attempt:

```sh
timeout 300 .venv/bin/pytest -q > /tmp/clevis-policy-full-suite.log 2>&1
```

Actual result: **11 failed, 439 passed, 20 skipped in 199.98s**. This invocation collected
71 new policy cases; the log-format and DNS/duplicate regression additions were verified in
the later focused runs. The skips are the existing five paid live and fifteen opt-in PinchTab
cases. No new skip or test suppression was introduced.

The subsequent full run (`.venv/bin/pytest -q`, raw log
`/tmp/clevis-policy-final-suite.log`) finished with **11 failed, 441 passed, 20 skipped in
200.68s**. It reproduced the same eleven legacy failures and included the DNS-cache and
log-format regressions. The duplicate-decision regression was added after its collection;
the focused policy run at that point included it and passed all 74 cases. These historical
full runs failed; they are not evidence of the authorized follow-up result.

| Failing legacy case | Failure evidence |
|---|---|
| test_real_browser_runner_and_sse | test_browser_integration.py:47 expected seven successful actions; localhost navigation was denied and the scripted target was never observed. |
| test_headed_scripted_form_runner | Same shared helper/assertion, via test_playwright_headed.py:43. |
| test_approval_stub_executes_and_emits_validation | test_graph_execution.py:130 expects finished without consent. The new gate waits; the helper's existing five-second timeout cancels it to stopped. The test also requires approval.required to be absent. |
| test_one_frontend_preview_navigation_popup_recovery_and_takeover[1,2] | test_frontend_preview.py:199 times out waiting for the local popup page that policy has blocked. |
| test_headless_browser_preview_websocket[1] | test_preview_browser_ws.py:109 times out waiting for a nonblank goal-page frame after the local navigation is denied. |
| test_headed_browser_preview_websocket | test_preview_browser_ws.py:97 times out waiting for its frame. This alone does not establish a distinct preview root cause; the scenario also uses policy-blocked localhost. |
| test_headless_login_handoff[1,2] / test_headed_login_handoff | Locator.bounding_box times out after 8000ms waiting for #username, because the local login page was not reached. |
| test_user_takeover_form_popup_disconnect_and_stop | Locator.bounding_box times out waiting for #name on the unreached local form. |

The two most direct conflicting cases were run separately, unchanged: **2 failed in 7.39s**
(old approval stub and headless form). The stub conflict cannot be fixed by preserving its
assertions and also implementing real approval. Automatically granting approval to legacy
validators or detecting pytest would conceal the conflict, so neither was implemented.

A separate diagnostic, with an explicit per-command development configuration:

```sh
BLOCK_PRIVATE_NETWORK=false REQUIRE_APPROVAL_FOR_SUBMIT=false REQUIRE_APPROVAL_FOR_SEND=false .venv/bin/pytest -q tests/test_browser_integration.py::test_real_browser_runner_and_sse tests/test_playwright_headed.py::test_headed_scripted_form_runner
```

Result: **2 passed in 5.89s**, including the subsequent status/redaction/subscriber/task cleanup
assertions. This is diagnostic evidence for the fixture configuration conflict, not a passing
secure-default gate or a change to production defaults. No test file or .env was altered.

## Approved scope and follow-up verification

The user approved both exceptions to the earlier test-edit prohibition:

1. Explicit local-network/automatic-submit configuration in legacy integration fixtures.
2. Replacing the obsolete approval-stub expectation with interrupt/consent/resume assertions.

IsolatedSettings now explicitly permits private-network traffic and automated submit/send
for the legacy demo workflows only. PolicySettings restores all three secure defaults for
the policy tests; production Settings is unchanged. A new regression test verifies those
production/policy flags remain true while only the legacy fixture flags are false.

test_approval_pauses_until_approved_and_emits_validation retains the prior finished-state and
validation assertions, replaces only the obsolete no-approval assertion, and verifies:
checkpoint interruption; paused state; no browser act or premature resource closure; explicit
consent; exactly one approval.required, run.paused and run.resumed; then result and cleanup.
No other legacy assertion or timing limit was changed.

The updated approval case, headless/headed form cases and all policy tests passed together:
**78 passed in 6.61s**. This includes 75 strict policy tests. Ruff passes; mypy reports no
issues in 125 source files. No per-command insecure env overrides are needed for this run.

Final full command, with no local-development env overrides:

```sh
.venv/bin/pytest -q > /tmp/clevis-policy-approved-full-suite.log 2>&1
```

Actual final result: **454 passed, 20 skipped in 147.51s**. The skips remain five paid live
model cases and fifteen opt-in PinchTab integration cases. No new skip was added. All eleven
previously conflicting legacy scenarios now pass, including the strengthened approval test;
the full run also includes the strict policy and production-default regression tests. Ruff:
All checks passed. Mypy: Success: no issues found in 125 source files.

This resolves the test-compatibility blocker. It does not resolve or erase the earlier
30-run preview reliability findings. Approval UI/authenticated HTTP decisions remain Task 3,
as specified; the production policy pause and internal interrupt/resume bridge are tested here.

## Version/API verification and limits

Installed Playwright **1.64.0** and LangGraph **1.2.17** were inspected directly: BrowserContext.route,
Route.abort("blockedbyclient"), Route.continue_, Request.is_navigation_request, Browser.new_context
service_workers="block", langgraph.types.interrupt/Command, and langgraph.errors.GraphInterrupt.
Installed docs explain that interrupt re-executes its node and routing misses service-worker
requests unless workers are blocked. The implementation preserves GraphInterrupt while
sanitizing real errors before checkpointing; it emits the pause once across re-entry.

Known limits: domain matching is exact, credential provenance is a goal-text heuristic, transaction
classification is heuristic, hash tracking covers exact extracted prefixes rather than transformed
or all observed content, and validation/Chromium DNS lookups retain a DNS-rebinding window.
Browser HTTP request interception is not a complete egress firewall. Approval HTTP auth/IDs,
tokens, frontend dialogs and durable recovery are Task 3; none was implemented prematurely.

An unrelated edit to AGENTS.md appeared during this work and was left untouched
and uncommitted by this task. Its Phase 2 safety instructions were read. Preview/takeover code
was not repaired or retimed; the previously documented intermittent failures remain separate.
