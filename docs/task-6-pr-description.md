# Let users take over the browser and hand control back to the agent

Users can pause a running agent, click/type in its live preview, and Resume agent after login,
CAPTCHA or 2FA. Agents can request the same flow with handoff and a short reason. Input uses a
separate active-page CDP session; preview capture, frame acknowledgements and bounded queues
continue independently. WebSocket finalization shields resource cleanup from repeated ASGI cancellation;
this fixes a teardown race without changing the preview protocol. The UI retains its layout and adds controls beside Stop and a privacy banner.

## Changes and contract

- POST /api/runs adds a separate random **controlToken**; previewToken stays read-only. Both are
  in process/UI memory only. Input requires the run token in its first message within five seconds,
  exact FRONTEND_ORIGIN and exclusive controller ownership. Never send credentials in URLs.
- Input WebSocket validates mouse/wheel/key/text/ping with strict Pydantic models, rejects invalid
  fields/types/UTF-8 sizes, closes after 50 rejects, rate-limits independently and reports codes only.
  State includes accepting/controller and an additive limits object (maxTextLength/maxMessageBytes)
  so configurable Unicode/UTF-8 paste limits also work in the frontend. No SSE contract changes here.
- Takeover is idempotent for an existing takeover pause. Before input becomes accepting, the service
  pauses driver actions, cancels and waits for in-flight browser/LLM work (1.8-second bound).
  Resume closes/relinquishes control, releases held input and discards stale work before a fresh
  observation. Final browser cleanup is serialized against takeover so a closed browser cannot
  be handed to a controller. Paused time stays outside MAX_SECONDS.
- Additive **handoff** action, and handoff run.paused data `{reason:"handoff",message}`; existing
  takeover/resume reason events are unchanged. Handoffs count as steps, skip loop-repeat detection
  and fail beyond MAX_HANDOFFS=3. Agent prompts request a human rather than inventing credentials.
- Independent total/idle control deadlines fail with **Take-over timed out**. Stop works during
  takeover. Dropped sockets free the slot and detach/release input; the agent remains paused.
  Popups/tab changes reattach input to the active page without touching the preview session.
- Frontend maps the actual displayed canvas rect to CSS viewport coordinates; DSF and scroll offsets
  are never added. Moves throttle to 60/s; wheels normalize line/page deltas. Printable text, IME
  commits and paste use a transparent DOM editor cleared after send, with no React input state,
  console, analytics or storage. Capture is limited to that editor/canvas while controlling.
  Browser shortcuts remain native; Tab also permits leaving the preview for Resume.
- Privacy tests verify a unique WebSocket canary is absent from all-level logs, errors, events/SSE,
  RunStore/state and every recorded LLM body. All editable values are hidden after takeover;
  ephemeral salted HMAC fingerprints suppress literal echoed tokens without a plaintext history.
  Public input is deliberately conservative too: browser `Welcome, demo-user` becomes agent result
  `Welcome, [redacted]-[redacted]`. Secrets cannot become a public result just because a page echoes them.

## Installed API verification

**Playwright Python 1.64.0**, **Chromium 156.0.8078.4 / build 1248**. Verified against the
[official CDP Input documentation](https://chromedevtools.github.io/devtools-protocol/tot/Input/),
[official protocol JSON](https://github.com/ChromeDevTools/devtools-protocol/blob/master/json/browser_protocol.json)
and [Playwright CDPSession documentation](https://playwright.dev/python/docs/api/class-cdpsession),
plus installed signatures/implementation and real Chromium tests.

| API | Verified and exercised |
|---|---|
| Input.dispatchMouseEvent | mousePressed/mouseReleased/mouseMoved/mouseWheel; viewport-relative CSS x/y; button, buttons (left 1/right 2/middle 4), clickCount, deltaX/Y, modifiers. Clamp coordinates, never add scroll. |
| Input.dispatchKeyEvent | keyDown/keyUp/rawKeyDown/char, key/code/text/windowsVirtualKeyCode/modifiers. Use keyDown/up, with lookup codes for special keys. Alt=1/Ctrl=2/Meta=4/Shift=8. |
| Key generated text | Reproduced: Enter keyDown with virtual code 13 but no text did not submit the demo form. Adding documented text `\r` fixed it. Space similarly carries generated text; no text on keyUp. Tab/Backspace and Enter are tested on the real login page. |
| Key editing commands | Documented optional experimental commands supports selectAll/copy/cut for Ctrl/Meta+A/C/X; real Ctrl+A replacement works. Clipboard/platform restrictions remain documented. |
| Input.insertText | text parameter supports typed Unicode/IME/paste without synthesizing printable key events. Verified real typing/non-Latin unit calls and actual frontend typing. |
| CDP lifecycle | Async context.new_cdp_session(page), session.send, close event and detach; separate input session; hooks removed on close, held buttons/keys released before detach, including error cleanup. |
| Playwright cancellation | Inspected installed `_connection.py` cancellation: sends protocol `__abort__` and waits for response. A real blocked auto-wait click is cancelled, then made clickable while paused; it never fires and Chromium remains open. No private API is invoked by application code. |

[AnyIO cancellation/shielding documentation](https://anyio.readthedocs.io/en/stable/cancellation.html#shielding)
was checked against installed AnyIO 4.15.1; it is now declared directly because both socket routes
use its cleanup shield. A repeated-disconnect test checks viewer queues are released.

No Playwright keyboard/mouse fallback is used. The relay never reads/modifies the DOM or reads a
server clipboard. A Chromium UI check also showed PointerEvent.detail=0 even on double-click;
the frontend honors nonzero detail and otherwise derives the count from transient click timing/
position (not React state or persisted data), with a unit regression test.

## Verification

Final regression commands and results: Normal tests use scripted fake LLMs;
no API key, paid model request or model configuration change was needed.

- Backend `.venv/bin/pytest -q`: **296 passed, 5 skipped** in 134.31 seconds. The five paid live-LLM cases skip by default; one upstream Starlette/httpx deprecation warning remains.
- `ruff check .`: **passed**; strict `mypy .`: **passed, 84 source files**; editor BasedPyright: **0 errors, 0 warnings, 0 notes**.
- Frontend `npm test`: **25 passed**; `npm run build`: **passed** (Vite 6.4.3).
- `python -m tests.takeover_ui_demo`: actual product login through resized canvas and Resume
  **passed in headless DSF 2 and headed DSF 1**, with a real source window in headed mode.
  Checks create through the UI, handoff/banner, separate socket auth, username/password typing,
  successful Sign in, resume, fresh observations and run.finished. No frames/traces/videos saved.
- Browser network regressions: headless DSF 1/2 and headed login; canary in a real password field;
  user-initiated form takeover; popup input; socket drop/reconnect; Stop while controlling;
  actual Tab/Backspace/Enter behavior; native action cancellation and owned Chromium process exit.
- Unit/integration regressions: Origin/auth timeout/wrong/run-mismatched/preview-token rejection,
  exclusive ownership, invalid/oversize/rate-limited messages, exact CDP call sequences, no-input
  state, handoff cap, total/idle deadlines, frozen LLM/budgets while paused, fresh turn boundaries,
  preview preservation, coordinate/letterbox math, Unicode chunking and private DOM editor clearing.

## Assumptions and limits

- Broader legacy timeline rewiring remains Task 8; this task wires only pause/resume/handoff,
  control tokens, safe error display and the existing run-control/preview integration.
- Input requires a real Playwright page; the default fake-browser test pattern has no DOM and
  reports INPUT_UNAVAILABLE. Demo/model smoke uses fakes for decisions and Chromium for input.
- HMAC echo filtering suppresses literal tokens, not arbitrary website transformations or a
  website's own exfiltration. Main-frame scope, no uploads/downloads, no server clipboard read,
  platform-limited shortcuts and automation-detecting CAPTCHAs remain documented limitations.
- Agent result assertions redact the supplied demo username because input privacy takes priority
  over reproducing its literal welcome string. Actual website success is checked separately.
- Single-process in-memory runs/tokens/controllers remain the Task 2 architecture. No authentication
  framework, database, persistent input/frames or unrelated endpoint changes were added.

## Human manual checklist

The automated equivalent passed in both modes. No human operator has performed this checklist
in this session; the boxes remain honest pending human checks (automation is not a human sign-off).
Use only fake demo credentials and do not record screenshots/traces containing typing.

- [ ] Headless: click Take over in the frontend, type into a real password field through the preview,
      sign in, click Resume agent and confirm the agent continues.
- [ ] Headed: repeat with the visible Chromium source window, confirming preview typing and Resume;
      optionally interact directly with the source window while the agent remains paused.
- [ ] Resize/letterbox the preview, verify clicking, IME/paste, double/right click, Tab/Escape and
      browser shortcuts; stop during control and confirm the source browser exits.

Changes follow the requested nine commits. This document is a ready-to-use PR description;
no PR has been published from this workspace.
