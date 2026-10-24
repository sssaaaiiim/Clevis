# PinchTab navigation deadlines and transport diagnostics

The reported screenshot showed BROWSER_ERROR with the Browser update "Start local PinchTab
0.15.2 and check PINCHTAB_URL." The local authenticated/version startup check passed during
diagnosis. That message previously covered every HTTP transport exception and invalid JSON,
so it did not establish that the server had stopped. The historical exception type is unknown.

Confirmed configuration mismatch: PINCHTAB_TIMEOUT_S=8 bounded all requests while NAV_TIMEOUT_MS
allowed 20 seconds for navigation. The HTTP client could abandon a slow navigation prematurely.
Navigation now receives at least its browser budget plus two seconds of transport overhead;
actions receive their action budget plus two seconds. The configured HTTP timeout remains a
lower bound. No request is retried automatically, avoiding duplicate click/form submissions.

Read/other HTTP timeouts now become TIMEOUT. Connection failures still name the local service
setup fix; interrupted connections and invalid responses use distinct sanitized messages.
No raw exception, response body, typed value, token or page content is included in diagnostics.
The terminal failure includes the action kind and refers to the preceding Browser update.
The public API, event/action schemas, preview and takeover are unchanged.

Verification references: installed httpx API type checks plus transport tests; PinchTab 0.15.2
tagged navigation/click docs were consulted:
https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/navigate.md
https://github.com/pinchtab/pinchtab/blob/v0.15.2/docs/reference/click.md
No undocumented PinchTab request parameter was introduced.

Tests: six new unit cases verify the three operation deadlines and distinguish ReadTimeout,
ConnectError and RemoteProtocolError with canary exception text removed. A real PinchTab
integration navigates to a delayed local page using a shorter ordinary request timeout.
Focused PinchTab/runner unit gate: 36 passed in 0.38s. PinchTab integration gate: 14 passed,
336 deselected, one existing Starlette/httpx deprecation warning in 36.11s. The new delayed-page
test initially assumed an unmodified title; PinchTab prefixes it with the bridge port. The corrected
test checks the title suffix and the exact destination URL; it retains the delayed response and
short ordinary deadline. Ruff passes and mypy passes for 91 source files.
Full backend suite: 331 passed, 18 opt-in cases skipped, one existing deprecation warning in
151.69s. Collection preceded addition of the delayed-page test, which passed separately in the
14-case real integration gate. No existing tests were removed or weakened.

Limit: the original model-generated destination/action cannot be reconstructed from the
screenshot. The public NUML task has not been claimed successful and no paid LLM calls were made.
