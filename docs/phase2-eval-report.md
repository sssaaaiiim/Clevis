# Phase 2 Task 4 evaluation report

Feature implementation is present; full acceptance is blocked by one incompatible legacy
response-key assertion requiring approval to update. No paid live-model evaluation was run.
Existing tests were not modified.

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

## Final quality gates

- In backend: `.venv/bin/pytest -q`: **1 failed, 528 passed, 25 skipped in 210.41s (0:03:30)**.
  The only failure is test_create_state_stream_and_replay's exact old response-key set; details below.
  All unchanged preview, take-over, privacy/canary, stop/pause, cleanup and other backend tests passed.
- `.venv/bin/ruff check .` from backend: **All checks passed!**
- `.venv/bin/mypy .` from backend: **Success: no issues found in 151 source files**.
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

## Compatibility approval required

Task 4 requires GET /api/runs/{id} to add permissions, but also forbids changing any passing test.
`backend/tests/test_api.py:69` asserts the exact old seven-key set. These requirements conflict.
The application implements the required additive field; the existing assertion is untouched.
The user was asked to approve adding only permissions to that expected set, preserving every other
assertion. Until that approval arrives, this single compatibility assertion remains a known failure.
There is no response-shape special case for tests/fakes or omitted permission requests.

## Known limits / recommended next actions

1. Approve the one-key assertion update so the backend suite can accept the mandated additive response.
2. Initial-popup HTTP redirects are conservatively blocked even for public destinations before the
   security session is attached. Open the destination in the current tab; future target auto-attachment
   could remove this restriction. This is a functional limitation, not an unguarded redirect bypass.
3. The fresh DNS check is independent of policy but cannot pin Chromium's actual connected peer;
   enforce private-network egress restrictions outside the browser for hostile workloads.
4. Keep Task 3 revision semantics: max_attempts is a revision allowance, so max_attempts=1 can include
   the initial failed check plus one retry before a partial result. The task's wording about one total
   attempt conflicts with the existing Task 3 behavior and unchanged tests; no silent semantic change.
5. Paid evaluations, real PinchTab-server integration and human sharpness/control review remain unverified.
   Existing historical preview flake investigation remains separate; its limits/assertions were not changed.
