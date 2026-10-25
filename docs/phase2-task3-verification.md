# Phase 2 Task 3 verification

Task: real outcome checks, planner revision, authenticated approval API and frontend modal.
No paid live-model tests were requested or run. Preview and input relay implementation files
were not changed. All behavior uses the existing EventEmitter/SSE pipeline.

## Implementation and commits

- `0a3d344`: bounded verifier prompts, OutcomeVerdict and dedicated model configuration.
- `cff8799`: completion checks and verifier usage accounting.
- `d9d5f74`: safe bounded revision and reserved internal revise action.
- `47c7c22`: unique pending approval IDs and graph decision binding.
- `a9fd49f`: authenticated approve/deny endpoints and approval timeout.
- `764febb`: graph and real-browser approval round-trip tests.
- `6c189de`: frontend modal, private token state and hook integration.
- `3f3ad15`: sanitized revision categories, confidence and original-task ainvoke resumption.
- `9273a06`: compatibility expectations for explicit sub-goal completion and verifier usage.
- `0ed84f6`: user-requested Phase 2 AGENTS additions.

## Commands and results

Commands run from backend unless specified. Browser suites run outside restricted sandbox
because local Chromium/test-server IPC is not permitted there. No test timing limits were changed.

Before compatibility corrections, the first full run reported **14 failed, 458 passed,
20 skipped in 153.13s**. Five failures were corrected in application code: unnecessary observation
on a no-op done changed pause/stale recovery behavior, and the verifier lacked visible-text evidence
needed by the injection baseline. The next full run reported **9 failed, 470 passed, 20 skipped
in 158.50s**. Remaining failures were obsolete node/event/usage expectations and scripted fixtures
that did not express completion under the new per-sub-goal semantics.

New outcome/API/frontend-browser tests: **26 passed in 7.69s**. Following the switch to
ainvoke(Command) in the original runner task, approval API plus real frontend round trips:
**10 passed in 6.65s**. Installed LangGraph **1.2.17** inspection confirmed:
`interrupt(value, *, response_schema=None)` and `Command(..., resume=...)` from langgraph.types.
No new CDP/Playwright operations were introduced in this task.

Final static/frontend gates:

- `.venv/bin/ruff check .`: **All checks passed!**
- `.venv/bin/mypy .`: **Success: no issues found in 132 source files**.
- In `front end/`, `npm test`: **10 files passed, 49 tests passed**, 11.26s.
- In `front end/`, `npm run build`: **success**, 1.94s.
- `git diff --check`: clean.

Final `.venv/bin/pytest -q`: **480 passed, 20 skipped in 167.88s (0:02:47)**, exit 0.
The expected opt-in skips
are five paid live-model tests (explicit authorization required) and fifteen PinchTab integration
tests (`PINCHTAB_URL` not configured for this run); these skip conditions were not changed.

## Coverage evidence

- `test_outcomes.py`: prompt bounds, untrusted blocks, parsing/retry/failure, usage,
  confidence when input is truncated or projected.
- `test_outcome_model.py`: dedicated model or primary default, 80 output tokens,
  shared SDK lifecycle via mocked HTTP (no paid requests).
- `test_outcome_graph.py`: verified multi-goal completion, failed check/retry,
  check at step cap, revision/re-plan, bounded safe feedback and terminal partial results.
- `test_approval_api.py`: authenticated approve/deny, missing/wrong token, stale ID,
  duplicate decisions, fresh IDs after denial, timeout, Stop, multi-goal revision and approval.
- `test_approval_frontend.py`: built React application driven in headless Chromium;
  Approve, Deny and Stop over real local HTTP/SSE, with external network requests blocked.
- Frontend ApprovalDialog tests: summary/risk/domain, authenticated request body, disabled
  decisions, optional denial reason, expired requests and dismissal.
- Existing privacy/checkpoint, takeover canary, stop, isolation and cleanup tests remain in
  the full suite. Browser form tests retain finished-status, subscriber/task cleanup and no-typed-value assertions
  after their exact event-list comparisons. Separate failure/stop tests check browser teardown.

## Compatibility corrections (not timing or privacy relaxations)

The shared successful_run_events helper includes a budget.update after each verification.
The default fake script now explicitly completes both sub-goals: four actions, two checks,
70 tokens including planning. Node order, counters and proposal counts assert that exact behavior.
Custom action scripts default to one sub-goal unless they provide a plan.
The history-cap fixture explicitly permits 30 actions per sub-goal so its eleven-action script
can exercise the unchanged eight-record history limit independently of completion caps.
The old revision stub expectation (skip a failed goal inside revise) was replaced by exact
first-retry/second-replan routing and preservation assertions; max-attempt termination is covered
by test_failed_outcome_at_max_routes_to_finish and the full partial-result graph test.
No test was deleted or skipped to conceal failure; timing, privacy, cleanup and sequence strictness
were preserved. These expectation changes are required by the Task 3 behavior rather than a
production compatibility mode.

## Assumptions and limits

1. The detailed routing table takes precedence over the conflicting acceptance sentence:
   first revision retries Navigator; the second calls Planner. Completed work remains intact.
2. The verifier includes up to 500 redacted visible-text characters, in addition to the strict
   50-element/3-summary limits, so noninteractive confirmations are verifiable.
3. API decisions are queued to the original runner, which performs ainvoke(Command) with the
   run thread ID. Starting a second graph task from the HTTP handler would lose private context
   and could race the existing producer.
4. Raw optional denial reason and verifier prose are mapped to safe categories before planner
   feedback/checkpointing. Approval summaries never display raw values or element refs.
5. MemorySaver and capability tokens are process-resident, not durable across restarts.
6. Paid real-model accuracy/cost and human visual review remain UNVERIFIED; run only after
   explicit authorization. Existing preview flake investigation remains separate; no preview
   timing or assertions were altered here.


## Completion

All automated gates above pass. The exact event comparisons in test_full_ordered_run,
test_real_browser_runner_and_sse, and test_headed_scripted_form_runner passed in the final
suite; their subsequent finished-state, sequence/counter, privacy and cleanup assertions also
executed and passed. Existing stop/pause, canary and checkpoint-isolation tests passed.
The headed scripted test ran in this environment; this is automated evidence, not a claim that
a human inspected sharpness or typed credentials manually. The separate historical preview
flakes did not fail this final run; their timing limits and assertions were not changed.

No automated Task 3 failure remains in the default suite. Paid live-model accuracy/cost and
opt-in PinchTab integration were not verified by this run. Review these before production use.
