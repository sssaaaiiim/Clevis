# Add isolated Playwright Chromium browser execution

Implement the real async browser layer without changing the frontend, event schema or API routes. `BROWSER_DRIVER` selects the existing fake or the injected Playwright driver; run mode chooses headed/headless Chromium. Each run owns a fresh context with configured viewport/device scale, denied permissions, disabled downloads and bounded navigation/actions. Cleanup covers success, failure, stop, partial startup and cancellation.

Pinned and verified: **Playwright Python 1.64.0**, bundled **Chromium 156.0.8078.4**, build **1248**. See [installed-version API audit](playwright-api-verification.md) for 46 verified members, signatures and the generated event overloads. Both modes use full Chromium via `channel="chromium"`; the separate headless shell is unnecessary. `playwright install chromium` is documented; verification installed full Chromium/FFmpeg using `playwright install --no-shell chromium`.

## Observation approach

Use one `page.evaluate` DOM script per observation rather than `page.accessibility` or an accessibility snapshot. It provides a direct mapping from each observed element to a generation-specific locator, supports explicit visibility/secret filtering and caps the observation before it reaches the model interface. `data-agent-ref="eN"` numbers are unique for the entire driver lifetime, so a ref from an old generation cannot silently point to a new element.

The script computes role/name/state, sorts top-to-bottom then left-to-right, caps elements/text, excludes hidden/transparent/tiny/clipped content and redacts sensitive input values. Names approximate the requested accessible-name precedence; this is not the full accessibility algorithm. Offscreen scrollable elements remain discoverable. `to_prompt_text()` emits compact element lines; the existing short observation summary remains on the timeline.

Add all requested actions, bounded waits/scrolling, clear/select/contenteditable typing and explicit key-press conventions. Results contain sanitized errors and navigation flags. New tabs/popups become active; closing the active page falls back to the newest remaining page. Dialogs are dismissed and reported by type without message text. Expose page/context, active-page callbacks, viewport and pause/resume hooks without implementing preview, input forwarding or takeover.

## Runner integration and privacy

The runner still imports interfaces and receives its driver through injection. It now supplies compact observations to the fake/model interface and preserves target-specific extraction. Since refs change per observation, loop detection compares the observed target's role/name/tag/href, falling back to the existing ref/description behavior for fake observations.

Type values are `[redacted]` in proposed events. Known typed values are also removed from later rationale/description/value, result/observation summaries, completion text and safe failure messages. Driver summaries never echo typed input. Unexpected Playwright errors are sanitized; safe `BrowserFailure` messages are exposed through the interface so missing-display errors remain understandable in run state/SSE.

## Local site and tests

Add framework-free, local-only search, form, demo login, eight-row inventory, scrolling/load-more, popup/dialog and hidden-text pages. `scripts/serve_testsite.py` uses stdlib HTTP serving, loopback by default, `TESTSITE_PORT` (8765 default) or `--port`. Pytest serves the same files on an ephemeral port.

The test-only `ObservedScriptLLM` binds scripted descriptions to current refs. `tests.browser_demo:app` exposes the unchanged production API with this fake for a reproducible local HTTP demo. The regular Task 2 fake LLM remains its original fixed script; this task adds no real model client or general goal interpretation.

Validation:

- `pytest -q` — **167 passed** in **55.00 seconds**, including both headed tests on this machine. One existing upstream Starlette TestClient/httpx deprecation warning remains.
- `ruff check .` — **passed**. `mypy .` — **passed**, strict mode, **47 source files** (Python 3.11 target; runtime verified with Python 3.14.4).
- `mypy scripts/serve_testsite.py` — passed.
- Zed's installed BasedPyright with repository config — **0 errors, 0 warnings**.
- Real Uvicorn + local site: `BROWSER_DRIVER=playwright USE_FAKES=true uvicorn tests.browser_demo:app --host 127.0.0.1 --port 8001 --no-access-log`; POST plus `curl -N /api/runs/{id}/events` completed the seven-action form script in **both headless and visible headed mode**, with **31 contiguous events** ending in `run.finished` and no typed name/email values in SSE.
- Tests verify page observations, hidden text and secret redaction, search/login/form/select/checkbox/contenteditable/key actions, scrolling, table/target extraction, stale/missing/hidden refs, blocked URLs, timeouts, popups/dialogs, permissions, fresh contexts/cookies, cleanup and fake-LLM/real-driver SSE integration.
- Linux process audit captures only this test process's Chromium descendants and verifies their PIDs disappear after action cancellation; it never targets the operator's browser. Browser contexts/connections are closed in the success/failure/stop tests as well.
- `git diff --exit-code 2919ec9 -- 'front end' backend/app/core/events.py backend/app/api` — passed; frontend, event definitions and API route modules remain unchanged.

## Assumptions and limits

- No `AGENTS.md` exists in the repo or ancestors. The completed editor-diagnostics fix was committed separately before the eight Task 3 implementation commits.
- Explicit per-run mode always wins over `BROWSER_HEADLESS`. A headed request without a display fails clearly; marked headed tests skip when no display is configured. A configured but broken display must be corrected locally.
- `navigate()` keeps its `None` return signature and raises a safe `BrowserFailure` on rejection/error; `act(navigate)` converts it to `ActionResult`. Act cancellation propagates after cleanup.
- `ActionResult.error_code` adds `PAUSED` for the requested hook; no event type or REST schema changes were needed.
- A `type` action with an empty target and an exact recognized key name presses that key; otherwise text typing requires an observed ref. Keys and limitations are documented in the README.
- The default fake model does not interpret arbitrary goals. The scripted demo is deliberately test-only; real model behavior is Task 4.
- Main frame only; no iframe or shadow-DOM traversal. Chromium only. No screenshots, streaming, browser input forwarding, real takeover or approval policy.
- Tiny-text filtering is a heuristic and can omit legitimate tiny labels. Ref validity ends on observation/page changes. Same-name duplicate controls can share a conservative semantic loop identity.
- HTTP(S) and exact `about:blank` are allowed. Localhost is intentionally available for testing; domain/private-network/SSRF policy remains the requested Phase 2 validator TODO.
- Existing in-memory store and queue limitations remain from Task 2. Existing local credential files/virtualenv were preserved and no real credentials were introduced.
