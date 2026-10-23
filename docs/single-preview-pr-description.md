# One frontend browser preview

Frontend-created runs always request headless mode. The existing parameter area now says
“Browser runs inside preview”; headed API/driver support remains available for diagnostics.
Popup tabs replace the active content in the same right-side canvas.

## Causes and fixes

- The UI previously allowed `mode="headed"`, which explicitly launches a visible Chromium
  window regardless of the environment default. UI runs now always use `headless`.
- A server `live` status could clear the overlay before any image was decoded and painted,
  leaving an unexplained empty area. Loading now lasts until the first successful paint.
- Received-frame deduplication prevented an idle resend from retrying a failed decode. Only
  successfully painted frames are deduplicated; ImageBitmap failures try the native image
  decoder, with object URLs released after use. Decode failures have an explicit message.
- Disconnections retain the last canvas image. Reconnects ignore stale socket callbacks;
  auth/Origin/missing-run failures stop retrying and show an actionable message.
- DSF 1 can look soft on HiDPI screens. The approved local private profile is DSF 2/JPEG 90;
  portable defaults remain 1/85. Internal canvas pixels match frame pixels and CSS sizing
  stays within the source viewport. No server resize or re-encoding was added.

These code paths explain possible empty/soft previews; a paid live-model reproduction of the
user's original run was not performed. Subjective sharpness still needs a human check.

## Scope and assumptions

The product is opened at `http://localhost:5173`, matching FRONTEND_ORIGIN. Backend public
routes, event shapes, input relay, capture/ACK logic and headed support are unchanged. The
frontend test uses a scripted fake LLM with real Chromium and isolated local Vite/API servers.
No screenshots, traces, input payloads or frames are saved. The opt-in UI demo now covers
headless DSF 1 and 2; dedicated headed tests continue to cover visible Chromium.

Playwright 1.64.0 is installed. The integration helper was checked against installed async
API signatures for BrowserContext.route, Route.continue_/abort and Page.set_viewport_size.
Vite's installed createServer declaration was checked for the isolated test proxy. No new
production CDP method or parameter is used.

## Verification

- `npm test`: 39 passed across 7 files.
- `npm run build`: passed, Vite 6.4.3.
- `ruff check .`: passed.
- `mypy .`: passed, 91 source files.
- `pytest -q -m headed`: 4 passed, 319 deselected.
- Real frontend/browser tests at DSF 1 and 2: first paint, a single headless agent, popup tab
  switching, forced CDP detach recovery, resized canvas dimensions, preview login and resume,
  and retained final frame. Final rerun: **2 passed in 14.25s**.
- `pytest -q`: **311 passed, 11 skipped, 1 failed** in 148.34s. The only failure is
  the pre-existing incomplete environment example described below. Opt-in live-model and
  PinchTab tests remain skipped; no paid model calls were made. Existing privacy and
  capture/backpressure tests passed. One existing Starlette/httpx deprecation warning remains.

## Existing configuration edit needing a decision

Before this task, `backend/.env.example` had been replaced with two credential assignments.
It is missing the complete settings template and fails
`test_env_example_exactly_matches_settings`. Its contents are deliberately neither printed nor
committed. The user was asked whether to move those values into ignored `backend/.env` and
restore the safe template, or preserve their edit. Pending an answer, the file is untouched.

## Human checks

Restart the API, refresh `http://localhost:5173/?debug=1`, and start a new real-browser run.
Confirm no separate agent window opens. Compare text at 100% zoom against Chrome at DSF 1
and 2; inspect frame/canvas/CSS dimensions. Confirm takeover typing and resume on the actual
site. These subjective/operator checks are not claimed as completed.

Commits: `06d4daa` (frontend headless-only), `39a7259` (preview recovery and regression coverage).
