# Phase 2 evaluation report

## Task 5 verification update

Latest standalone command from a fresh environment: `pytest -q tests/eval/ -ra` →
**24 passed, 5 skipped in 58.53s**: 23 real-headless-browser/fake-LLM scenarios and one
recorder privacy unit test. The five paid live cases were not run under the prior billing
restriction. The following table and the latest-per-scenario JSON scan both show 23/23 passes.
No live accuracy, token usage or provider cost is claimed.

| Category | Passed / total | Rate |
|---|---:|---:|
| Policy | 6 / 6 | 100% |
| Outcome | 4 / 4 | 100% |
| Approval | 5 / 5 | 100% |
| Revision | 3 / 3 | 100% |
| SSRF | 5 / 5 | 100% |
| Total non-live scenarios | 23 / 23 | 100% |

The artifact now contains 452 historical records, each with the nine documented fields.
All latest event/assertion booleans are true; all latest statuses pass. Their scripted fake usage
counters sum to 1282 tokens and $0.00 fake cost. Live costs remain UNVERIFIED. The schema/static
identifier scan and forbidden capability/canary scan passed. Previous failures remain as history;
100% describes the latest 23 scenario results, not every historical attempt.

**Passing evaluations do not establish release acceptance.** After the approved HiDPI/input
coordination and explicit fake-login provenance fixes, the final full backend suite passes
**544 tests, 25 opt-in skips**. The managed PinchTab gate passes all 15 tests; headed 4, targeted
privacy/stop 12 and the ten-run/three-concurrent leak check also pass. Before these approved fixes,
the audit reported 540 passed/one intermittent HiDPI failure, and the separate PinchTab gate had
13 passes/two credential-fixture failures. Those failures remain in the full audit record; existing
assertions and timing limits were preserved. One historical credential finding still blocks release.
See [the full audit](phase2-verification.md). No paid model calls were made.

## Historical Task 4 record (preserved)

The user approved adding permissions to the legacy response-key assertion. That single
expected-key set was updated; all other assertions and timing limits remain unchanged.
No paid live-model evaluation was run. Final backend result: **531 passed, 25 skipped**.

## Scope and evidence

23 local scenarios use real headless Chromium and injected fake actors/verifiers. The scenarios
exercise the production graph, policy, outcome, revision and authenticated approval endpoints.
SSRF fixtures permit only their dedicated source URL and inject DNS results; forbidden/private
redirect targets are aborted. The HTTP tripwire proves that neither existing-tab nor initial-popup
redirects contact the private destination. The PinchTab regression exercises PinchtabDriver.act
with fake PinchTab transport and real Playwright-owned Chromium; no real PinchTab server is claimed.

The latest record per scenario in eval-results.json is the report's source. Previous failures are
retained as history, not erased. A scenario is pass only after pytest's call report passes. Each
record contains timestamp, fixed scenario identifier, status, ordered-event match, assertion booleans,
steps, tokens, cost and a sanitized fixed failure description. No capability tokens, values, page
content or exception text are written. A separate privacy test injects canaries into forbidden
record fields and proves they are omitted. Writes are locked and atomically replaced.

| Category | Local scenarios | Latest passed | Latest failed | Pass rate |
|---|---:|---:|---:|---:|
| Policy | 6 | 6 | 0 | 100% |
| Outcome | 4 | 4 | 0 | 100% |
| Approval | 5 | 5 | 0 | 100% |
| Revision | 3 | 3 | 0 | 100% |
| SSRF | 5 | 5 | 0 | 100% |
| Total | 23 | 23 | 0 | 100% |

Five live smoke evaluations are skipped unless explicitly selected with -m live_eval and a configured
key/model. Their tokens/cost/accuracy are UNVERIFIED; **no paid calls, no reported paid cost**.
A set key alone does not authorize billing. With authorization, run from backend:
`pytest tests/eval/scenarios/test_live_eval.py -m live_eval -q`. Results append counters and cost;
no prompt, response or token capability is recorded.

## Failures found and corrected

- A multi-navigation data-flow scenario needed an evaluation-specific wait for the real sequence;
  its original new-fixture three-second wait expired. The harness now uses an eight-second scenario
  wait; no pre-existing timing limit was changed.
- approval.required precedes checkpointed interrupt readiness. The eval client now waits for the
  actual interrupt instead of racing the API with a decision before the run pauses.
- A blocked meta-refresh can interrupt the executing click. The driver now returns BLOCKED_URL
  after settling navigation; non-strict runs re-observe while strict runs fail. Other browser errors
  retain their original failure behavior.
- Routing alone missed HTTP redirect hops: the new private-target tripwire initially received a
  request. Response-stage CDP Fetch interception now validates Location before following it.
- A popup's initial request may have no Playwright Frame yet. Accessing it unconditionally aborted
  valid popup loads. Early responses now use no-redirect fetch and fail closed on redirects.
- Proxy-fulfilled local popups change Chromium's address-space classification and can block localhost
  iframes. Extra interception is skipped when the operator explicitly disables private-network checks
  and has no restrictive domain lists. Existing popup/preview/takeover regressions then pass unchanged.
- New optional warning/domain fields initially serialized null on ordinary events, failing an exact
  legacy event check. Serialization now omits those fields unless a navigation warning is present.

Early full run: **2 failed, 515 passed, 25 skipped in 219.70s** (new GET field and ordinary event
serialization). An intermediate full run after HTTP interception exposed popup lifecycle regressions:
**4 failed, 522 passed, 25 skipped in 232.73s**. These results are not replaced by claims of success.
Focused post-fix run covering unchanged preview at DSF 1 and 2, initial/existing-tab private HTTP
redirect tripwires, and iframe regressions: **6 passed in 19.64s**.

Before the approved compatibility update, the full run reported **1 failed, 528 passed,
25 skipped in 210.41s** at the old GET response-key assertion.

## Final quality gates

- In backend: `.venv/bin/pytest -q`: **531 passed, 25 skipped in 211.24s (0:03:31)**, exit 0.
  This run used the approved response-key assertion and final form/popup guard fixes, with no competing
  browser diagnostics. All preview, take-over, privacy/canary, stop/pause and cleanup tests passed.
- `.venv/bin/ruff check .` from backend: **All checks passed!**
- `.venv/bin/mypy .` from backend: **Success: no issues found in 152 source files**.
- In front end: `npm test`: **12 files passed, 57 tests passed**, 14.26s.
- In front end: `npm run build`: **success**, 2.82s.
- `git diff --check`: clean.
- Recorder schema check: all rows contain only the permitted ten output keys; latest **23/23**
  scenarios pass and no approvalToken/controlToken fields exist.

Skipped tests: five existing paid live tests, fifteen existing opt-in PinchTab integrations, and
five new paid live evaluations. These require separate explicit opt-in; no existing skip condition
or timing limit was loosened. The final full-suite command exercised the non-live evaluation scenarios.
Standalone `.venv/bin/pytest tests/eval/ -q`: **24 passed, 5 skipped in 47.44s**
(23 scenarios plus the recorder privacy unit test; five paid live scenarios skipped).

An additional root-level `.venv/bin/mypy .` invocation (outside the documented backend command/config)
reported 11 Settings-constructor diagnostics in existing scripts/tests; it did not load the backend's
pydantic mypy configuration. The required backend-directory invocation above passes. No unrelated
scripts or pre-existing test assertions were changed to accommodate that unsupported invocation.

## Post-approval blocked-loader regression

The approved key-set assertion passed, but the next full run found a separate intermittent form
page-clearing failure: **1 failed, 528 passed, 25 skipped in 211.68s**. The private request was blocked;
the old form loader interrupted both replacement navigations and left the original page displayed.
The existing test and its timing limits were retained. Browser cleanup now calls the documented
CDP Page.stopLoading before navigating to about:blank. A deterministic mock-loader regression fails
without this ordering and checks hostname-only reporting. Initial focused guard tests: **10 passed
in 6.56s**. The stop-loading-only implementation passed 29/30 repeated browser runs; one still failed
page clearing. A bounded 50 ms settle was added before the existing retry, with a separate
regression for delayed renderer cancellation. The unchanged real form test then passed
**30/30 separate pytest runs**, with no assertion or timing-limit changes. Both new deterministic
ordering tests pass (**2 passed in 0.09s**). An intermediate full run passed **530 tests,
25 skipped in 226.68s** before adding the second ordering regression.

A subsequent run (with focused browser diagnostics overlapping) reported **2 failed, 529 passed,
25 skipped in 219.90s**: initial-popup clearing selected the parent too early, and the separately
known HiDPI iframe checkbox flake recurred (unchecked checkbox, test_preview_cdp.py:336).
The popup handler now registers/waits for the new Page before selecting the frame to clear.
No preview/input implementation, assertion or timing limit was changed. Its focused guard/preview
run passed **11 tests in 21.40s**. The popup tripwire passed **30/30 separate pytest runs** after that correction.
The unchanged HiDPI test passed in isolation (**1 passed in 2.69s**); this is not a claim that its
historical flakiness is fixed. The final suite runs without competing browser diagnostics.

Commits: `913634a` (approved expected-key update), `8dcbc2d` (stop pending loader),
`05f37a4` (bounded renderer settle and its regression), `67f68d3` (clear the new popup).

## Approved compatibility update

Task 4 requires GET /api/runs/{id} to add permissions. The old exact seven-key assertion in
backend/tests/test_api.py excluded that field. After explicit user approval, only permissions
was added to the expected key set. No other assertion in that test changed.
The targeted test passed: **1 passed in 1.06s**, including the previously unreachable final-state,
Last-Event-ID/query replay, terminal-transition and subscriber cleanup assertions.
Ruff and mypy (152 files, including the new regression module) also passed after these updates. No application response special case
was introduced for tests, fakes or omitted permissions.

## Known limits / recommended next actions

1. Initial-popup HTTP redirects are conservatively blocked even for public destinations before the
   security session is attached. Open the destination in the current tab; future target auto-attachment
   could remove this restriction. This is a functional limitation, not an unguarded redirect bypass.
2. The fresh DNS check is independent of policy but cannot pin Chromium's actual connected peer;
   enforce private-network egress restrictions outside the browser for hostile workloads.
3. Keep Task 3 revision semantics: max_attempts is a revision allowance, so max_attempts=1 can include
   the initial failed check plus one retry before a partial result. The task's wording about one total
   attempt conflicts with the existing Task 3 behavior and unchanged tests; no silent semantic change.
4. Paid evaluations, real PinchTab-server integration and human sharpness/control review remain unverified.
   Existing historical preview flake investigation remains separate; its limits/assertions were not changed.
