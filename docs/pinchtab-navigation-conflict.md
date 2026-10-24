# Fix the reproduced NUML search-result click failure

Reproduced the user's DuckDuckGo → official NUML LMS result click with the installed PinchTab
0.15.2, real headless Chromium, and no LLM calls. The search loaded and seven matching LMS links
were observed. Clicking the first returned HTTP 409 with code navigation_changed and detail keys
hint/recovery/remedy/url; the page URL changed. No raw response body/page text was logged or saved.
The adapter previously mapped this response to fatal BROWSER_ERROR with misleading token guidance.

The adapter now maps exactly navigation_changed to the existing STALE_REF result. The runner's
existing bounded stale-ref path obtains a fresh observation and asks the model for the next action.
No automatic repeat click, invented success result, driver fallback, or security-policy bypass occurs.
Other conflict codes, including tab_paused_handoff and unauthorized, retain their failure behavior.
No API routes, public event/action shapes, preview behavior, or takeover behavior changed.

A second public-site check after the fix reported STALE_REF on the click, then the next observation
was on the official NUML domain. This verifies the reported navigation path, not the live LLM's
complete final answer or a logged-in student session. No paid model calls or credentials were used.

The exact response code was verified experimentally against installed 0.15.2. Tagged v0.15.2
endpoint/click documentation was consulted for the action route and distinction from handoff:
https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/endpoints.md
https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/click.md
No new upstream API field or endpoint is assumed.

Validation: 39 focused adapter/runner tests passed in 0.40s. Three new transport cases distinguish
navigation_changed from handoff/auth errors, assert canary text stays private, and assert one request.
A real-browser local integration sends the link click once, injects the reproduced conflict after
navigation, verifies the destination in the next model prompt, and requires run.finished.
Integration gate: 15 passed, 339 deselected, one existing warning in 45.16s. Ruff passed and mypy
passed for 91 files. Initial full suite: 333 passed, 20 opt-in skips, one failure in the unchanged
test_hidpi_takeover_iframe_input_and_capture_resume (iframe checkbox remained unchecked).
The isolated takeover test also failed in 7.10s with the same unchecked-checkbox assertion.
This is an open, separate regression-gate issue; no takeover code or test assertion was changed
in this fix. The full suite is not claimed clean. The reproduced search-result click path and
the 15-case integration gate pass. No paid live model completion is claimed.
