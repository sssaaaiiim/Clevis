# Phase 1 acceptance checklist

The current evidence and every A1–G6 item are in [phase1-verification.md](phase1-verification.md).
This checklist does not turn unverified human work into a pass.

- [x] Repo discovery retained; no Node backend; React/Vite design preserved.
- [x] Async FastAPI contracts, strict events/state machine, replay/live SSE and JSON errors tested.
- [x] Fresh-environment install, backend/static gates and frontend build/tests executed.
- [x] Real loopback HTTP and both authenticated WebSockets exercised, including a 15-second SSE comment.
- [x] Headless and headed Chromium observations/actions, isolation, redaction and cleanup tested.
- [x] Real agent flow, mocked OpenRouter routing/retry/usage, budgets, loops and cancellation tested.
- [ ] Real OpenRouter five-goal smoke acceptance: FAILED with invalid API key/no access; replace the
      private credential or restore account access, then run `pytest -q -s -m live` from backend
      with OPENROUTER_API_KEY and LLM_MODEL_PRIMARY exported. Record per-task steps and reported cost.
- [x] CDP preview ACKs, native pixel sizes, bounded viewer queues, recovery/fallback and retention tested.
- [x] Single-controller takeover auth, exact CDP input, handoff/resume, timeouts and canary privacy tested.
- [x] PinchTab 0.15.2 spike rerun PASS; OPTIONAL adapter remains opt-in and default path independent.
- [x] Ten mixed-run leak/RSS sample and three concurrent isolated contexts executed; atomic run cap tested.
- [x] History/worktree credential scan, ignored .env, exact settings/example parity and bounded dependencies checked.
- [x] Local-run docs and Phase 2 integration notes present; no Docker dependency introduced.
- [ ] NEEDS HUMAN CHECK — Sharpness: run API with DEVICE_SCALE_FACTOR=1, real Playwright and a valid
      OpenRouter key; open localhost:5173/?debug=1 and a text-heavy local test page. At 100% zoom compare
      preview text to a normal Chrome window. Check native frame/canvas/CSS dimensions. Restart at DSF=2
      and repeat with a smaller/larger preview. Do not save screenshots containing real personal data.
- [ ] NEEDS HUMAN CHECK — Typing/clicks: start login.html with a goal requesting human sign-in;
      enter takeover through the preview, type the published fake demo credentials, sign in and Resume.
      Repeat headless/headed, DSF 1/2 and resized/letterboxed preview; verify click accuracy, paste, IME,
      Tab focus escape, Stop, and that the agent continues from the resulting page.
- [ ] NEEDS HUMAN CHECK — Billing: after successful live tests compare the recorded per-task usage/cost
      with the OpenRouter account activity page; record any estimates/provider adjustments.

A display was available for automated headed tests. No person performed the subjective checks above.
No claim of production multi-tenant security, unlimited memory bounds or Phase 2 policy protection is made.
