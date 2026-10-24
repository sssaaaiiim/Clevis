# Authorized event expectations and preview repetition study

Date: 2026-10-24. Event expectation commit: `7f0d99c`.

## Scope and method

The user authorized adding step.validated between step.proposed and step.executed and
deduplicating the expectation. `tests/event_sequences.py` now defines the per-action sequence
once. The fake-run test, shared headless/headed form helper, and graph event-order test use it.
Every other assertion and its order are unchanged. No application, preview, input, timing,
fixture, or skip logic was modified. No paid live-model tests were selected.

Commands run from backend with the existing .venv:

```sh
.venv/bin/pytest -q tests/test_runner.py::test_full_ordered_run tests/test_browser_integration.py::test_real_browser_runner_and_sse tests/test_playwright_headed.py::test_headed_scripted_form_runner
.venv/bin/ruff check .
.venv/bin/mypy .
```

Targeted result: **3 passed in 5.82s**, with the headed case actually executed, not skipped.
Ruff: **All checks passed**. Mypy: **Success: no issues found in 112 source files**.
The sandbox printed stream-fd permission diagnostics during lint/type commands; both exited 0.

## Previously unreached assertions

Both browser cases now pass all assertions after the event-list comparison:

- The run state endpoint reports finished.
- Neither demo@example.test nor Demo Example occurs in SSE text.
- The SSE subscriber count is zero after the client exits.
- The task registry is empty after lifespan shutdown.

The fake-run case also passes gap-free sequence, three-step/40-token budget, finished state,
and driver.closed assertions. Evidence: the three named tests above completed without failure.
Limits: the browser helper asserts finished status, not the exact final result text or an OS
process listing. Its privacy check covers the two demo values, not a complete canary audit.
No stronger assertion is claimed, and no new assertion was added within the restricted scope.

## Repetition method

Each targeted invocation used a fresh `.venv/bin/pytest -q <node-id>` subprocess and unchanged
test fixtures against a temporary loopback test site. First run animation 30 times sequentially,
then HiDPI 30 times sequentially with no other pytest suite active. Repeat both batches while
a separate process runs `.venv/bin/pytest -q`; restart full suites until the batches finish,
allow the last background suite to complete, then run one final suite alone.

The experiment driver is `/tmp/clevis_preview_repetitions.py`; raw per-invocation logs and
exit codes are in `/tmp/clevis-preview-repetitions/` with `results.json`. These temporary
artifacts are local evidence, not tracked product files. Reproduce isolated batches with:

```sh
for i in {1..30}; do .venv/bin/pytest -q tests/test_preview_cdp.py::test_animation_throttle_and_nonreading_viewer_do_not_block_browser; done
for i in {1..30}; do .venv/bin/pytest -q tests/test_preview_cdp.py::test_hidpi_takeover_iframe_input_and_capture_resume; done
```

For the loaded condition, keep a separate terminal running repeated `.venv/bin/pytest -q`
throughout those same two loops. Ordinary collection skips paid live tests even if a key exists;
no `-m live` invocation occurred.

## Targeted results (120 invocations)

| Test | Isolated passed / failed | Alongside full suites passed / failed |
|---|---|---|
| Animation/throttling/non-reading viewer | 29 / 1 | 26 / 4 |
| HiDPI iframe takeover/capture resume | 28 / 2 | 21 / 9 |

Failure iterations, counting from 1 separately within each batch:

| Condition | Iterations | Exact failing assertion / message |
|---|---|---|
| Isolated animation | 28 | test_preview_cdp.py:249: `assert channel.received == channel.acked`; `assert 47 == 46` |
| Loaded animation | 15, 18, 25, 27 | Same assertion and values: 47 received, 46 acknowledged. |
| Isolated HiDPI | 4, 13 | test_preview_cdp.py:336: `await expect(checkbox).to_be_checked()`; `Locator expected to be checked`, `Actual value: unchecked`. |
| Loaded HiDPI | 3, 5, 6, 8, 10, 13, 20, 21, 27 | Same checkbox assertion/message. Playwright's existing expectation timeout is 5000ms. |

No targeted failures occurred at the observe-time limit, queue bound, frame-rate bounds,
image dimensions, or fallback/resume assertions. The HiDPI failures occur before the latter
assertions, so they do not establish that fallback/resume passed on those failed attempts.

## Interpretation, without a preview fix

Both failures reproduce without concurrent pytest load. The loaded rates were higher in this
sample (animation 13.3% versus 3.3%; HiDPI 30% versus 6.7%). These are observations from one
ordered experiment, not proof that CPU load is the cause or a stable population failure rate.

Animation reaches its post-stop ACK equality assertion with exactly one missing successful ACK.
In app/preview/cdp.py, _receive increments received before awaiting the ACK and increments acked
only after success; _detach stops screencast and drains queued ACK tasks before detaching.
The test output alone cannot distinguish a failed send from a late callback or another shutdown
race. A focused diagnostic follow-up should establish which occurs before changing cleanup.

HiDPI accepts both relay.send calls but the iframe checkbox remains unchecked. Successful CDP
dispatch is therefore insufficient evidence that the intended element received the click.
Coordinate/emulation state and cross-origin iframe hit-testing during the takeover transition
are candidates for further diagnostics, not established causes. No new instrumentation or
behavior changes were introduced in this investigation.

## Full-suite results after the authorized update

| Invocation | Actual result |
|---|---|
| First full suite alongside repetition batches | **1 failed, 378 passed, 20 skipped in 174.04s**. Sole failure: HiDPI checkbox, test_preview_cdp.py:336, same message above. |
| Second background suite (continued until repetitions completed, then allowed to finish) | **379 passed, 20 skipped in 147.99s**. |
| Final suite, no concurrent repetition process | **379 passed, 20 skipped in 146.22s**. |

All used `.venv/bin/pytest -q`. No test was weakened or newly skipped. The 20 existing skips
are five explicitly opt-in paid live-model cases and fifteen opt-in PinchTab integration cases
(PINCHTAB_URL not exported for this experiment). The three previously failing lifecycle tests
pass in the final suite as well as their dedicated invocation. Passing final-suite results do
not resolve the preview failures reproduced in the repetition study.
