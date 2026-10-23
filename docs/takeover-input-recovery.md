# Takeover input recovery

## Reproduction and cause

The supplied screenshot shows a paused handoff at a Cloudflare verification page. It does not
by itself prove whether a click was dropped or the service rejected the browser. No production
challenge was solved or bypassed during this work.

A local cross-origin iframe checkbox reproduced an application bug at DSF 2: input packets
reached the relay at the correct CSS point, but the checkbox stayed unchecked when the preview
used an enlarged compositor viewport. Direct relay input without capture succeeded at DSF 1
and 2. Controlled local capture experiments produced these results (1280×720 CSS viewport):

| Capture configuration | Encoded pixels | Iframe checkbox click |
| --- | --- | --- |
| Existing viewport scale 2 | 2560×1440 | FAIL |
| Native viewport, DSF 2 | 1280×720 screencast | PASS |
| Global image scale 2 | 1280×720 | FAIL |
| Global scale 2 and viewport scale 1 | 2560×1440 | FAIL |

Resetting an existing enlarged viewport alone was insufficient for an immediate click. A native
reset followed by 100 ms of compositor settling passed. These experiments used fake local data,
never the supplied website; frames were decoded in memory for dimensions and never saved.

## Fixes

- During HiDPI takeover, restore native CSS geometry and use device-resolution screenshots at
  SCREENCAST_FALLBACK_FPS (default 2). This preserves sharpness with a lower frame rate while
  the human controls the page. Resume restores normal screencast; DSF 1 stays on screencast.
- The relay resets capture geometry on a newly attached paused HiDPI page and waits 100 ms
  for hit-test regions before delivering the first input. There is no per-keystroke delay.
- The takeover banner passes clicks through to the canvas underneath. Its reconnect button
  remains clickable.
- Relay errors and connection failures are visible. Reconnect control replaces only the input
  WebSocket; the agent stays paused and the preview stays connected. Single-controller and
  token/Origin checks are unchanged. Error text uses constant messages and never echoes input.

## API verification

Playwright 1.64.0 is installed. Installed async signatures were checked for FrameLocator.get_by_label
and LocatorAssertions.to_be_checked. CDP fields were checked against the official
[Input reference](https://chromedevtools.github.io/devtools-protocol/tot/Input/) and
[protocol schema](https://github.com/ChromeDevTools/devtools-protocol/blob/master/json/browser_protocol.json):
Input.dispatchMouseEvent uses main-viewport CSS pixels, while Emulation.setDeviceMetricsOverride
has distinct deviceScaleFactor and optional viewport/image scaling. Omitting viewport clears its
override. The local experiments establish the observed Chromium interaction; the docs do not
promise a production challenge will accept automation.

No public API route, event shape or input message schema changed. No agent iframe observation,
DOM inspection in the relay, stealth settings or challenge-solving automation was added.

## Tests and evidence

- `npm test`: 40 passed; `npm run build`: passed.
- `ruff check .`: passed; `mypy .`: passed, 91 source files.
- `pytest -q -m headed`: 4 passed, 322 deselected in 9.69 seconds.
- `pytest -q tests/test_frontend_preview.py`: 2 passed in 12.75 seconds. At DSF 1 and 2, assert
  actual canvas input changes a cross-origin checkbox; both mouse events reach the expected
  CSS point; controller reconnect preserves paused state; login/resume works. Popup, sizing,
  first paint and forced-detach recovery assertions remain. Detach is exercised before handoff,
  since HiDPI takeover intentionally has no screencast session. Resize assertions now wait for
  ResizeObserver layout completion while preserving the original aspect-ratio requirement.
- `test_hidpi_takeover_iframe_input_and_capture_resume`: passed. The checkbox responds,
  retained device frame dimensions are 2560×1440, and resume returns to live screencast.
- Earlier failing iframe runs were investigated; neither assertions nor tests were removed to
  obtain a pass. The initial test fixture's iframe border was made explicitly zero so its
  synthetic coordinate checks have an unambiguous content origin.
- Final `pytest -q`: **314 passed, 11 skipped, 1 failed** in 145.54 seconds. The only failure
  is `test_env_example_exactly_matches_settings`: the pre-existing user-edited
  backend/.env.example is incomplete and remains untouched. Opt-in live-model/PinchTab tests
  stay skipped. Privacy canaries and cleanup tests passed; no paid LLM calls were made.
- The strengthened fresh-native-frame/resume assertion was rerun separately: **1 passed**
  in 2.75 seconds.

## Remaining limits and operator steps

Restart the API and start a fresh run after refreshing the frontend. During handoff, use the
right-side canvas directly. If an input error appears, click Reconnect control; this does not
resume the agent. After completing the page interaction, use Resume agent in CLEVIS COMMAND.

Cloudflare's [supported-browser documentation](https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/)
explicitly excludes automated browsers for solving production challenges. Correctly delivered
human clicks therefore do not guarantee that this website's verification will pass. That live
site remains UNVERIFIED; the local iframe, login and reconnection behaviors are verified.

Fix commits: `435580d` (input feedback/reconnect), `2b03cad` (HiDPI capture/input and regressions).
