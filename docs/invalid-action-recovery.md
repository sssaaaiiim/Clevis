# Recover from invalid browser action arguments

Reported failure: `Browser action failed: INVALID_ACTION` on a public search/navigation task.
That code alone does not identify the original action or its arguments. A separate isolated
Google search check confirmed navigation, filling and Enter succeeded, then reached Google's
verification page; it does not establish the cause of the user's original failed run.

The confirmed runner problem was that a single invalid action immediately ended the task.
The runner now counts the rejected step, records safe feedback, re-observes, and asks for corrected
arguments. Three consecutive invalid results fail clearly; existing step/time/token/cost budgets,
loop detection and URL validation remain active. No arbitrary model text is executed.

The trusted prompt clarifies wait seconds, scroll directions, full URLs and typing/ref conventions.
The PinchTab invalid-wait summary gives a static numeric example without echoing the supplied value.
API routes and public action/event schemas are unchanged. Preview and takeover are unchanged.

Validation:
- 21 focused runner/prompt tests passed, including one/two rejected actions recovering and three
  consecutive rejected actions failing with all attempts counted and fresh observations obtained.
- 13 PinchTab integration cases passed in 33.31s: both five-goal smoke suites, privacy/stale/pause/
  outage coverage, and real PinchTab/Playwright runs recovering from a malformed wait argument.
- Ruff passed; mypy passed for 91 files.
- Full backend suite: 325 passed, 16 opt-in tests skipped, one existing Starlette/httpx
  deprecation warning in 147.61s. This run was collected before the two additional real-driver
  recovery cases were added; both passed in the separate 13-case integration gate above.

Assumptions and limits: bounded correction is preferable to failing on the first invalid argument.
No paid LLM calls were made; successful completion of the original public NUML task is unverified.
Human verification may still require takeover, and Google may reject automated browsers.
