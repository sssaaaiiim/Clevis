# Verify and harden Phase 1

The audit covers all 47 specification items with reproducible evidence and individual fix commits.
**35 PASS, 5 FAIL-FIXED, 4 PASS-WITH-DEVIATION, 1 FAIL-OPEN, 2 UNVERIFIED.**
Phase 1 is not fully accepted: all five real OpenRouter smoke tasks failed before planning with
"invalid API key or no access". The configured model is deepseek/deepseek-v4-flash; no successful
live model was verified in this audit. Existing private configuration was neither changed nor disclosed.

Fixes: atomic MAX_CONCURRENT_RUNS=3 admission with JSON 429; Python-shaped frontend timeline;
truthful server-configured limit controls; strict Vite port to preserve authenticated Origin;
real network/contract and architecture regression checks; missing local-run/acceptance/Phase 2 docs;
and a reproduced preview shutdown race (47 received frames, 46 ACKs) fixed by retaining session
ownership and draining ACKs before detach. No existing test or assertion was weakened or removed.
New-test Node/jsdom and alias configuration errors are disclosed in the report.

Validation: clean installs, backend full/headed/privacy gates, Ruff/mypy/pip check, frontend build/tests,
real loopback HTTP/WS/SSE, PinchTab 0.15.2 spike/integration, and 10 mixed plus 3 isolated concurrent
browser leak/RSS runs. Final results: **310 backend passed / 11 legitimate opt-in skips; 4 headed passed; 4 canary passed; 6 optional adapter passed; 28 frontend passed**. Ruff, mypy and pip check passed. Final leak sample RSS 51.77 → 73.77 MiB, with no owned browsers left. Exact outputs are in [phase1-verification.md](phase1-verification.md).
The optional PinchTab recommendation remains OPTIONAL; the default path needs neither it nor Docker.

Top five risks:

1. **Blocker:** current OpenRouter credential/account access rejects live completions.
2. Human sharpness, tactile takeover/IME/resized click accuracy and account billing remain unverified.
3. Runs/events are process-local and historical metadata persists until restart; finite RSS checks do
   not establish unlimited-run memory bounds. Use one worker and the admission cap.
4. This is a local single-operator product with Phase 1 AllowAllValidator; production policy/SSRF,
   approvals, accounts and injection classification remain explicitly Phase 2, not implemented here.
5. Optional PinchTab adds a privileged version-sensitive service and ambiguous-ref reconciliation;
   keep it authenticated on loopback with recording disabled and opt in only when useful.

Recommended next action: restore a valid private OpenRouter key/account/model entitlement, rerun
`pytest -q -s -m live` with exported key/model, then perform the exact human checks in the report.
Do not publish acceptance as complete before those pass. No secrets belong in this PR or chat.

Assumptions/deviations: actual frontend folder is `front end/`; no frontend lint script exists; browser
JS is not a Node backend; the deliberate injection URL is literal hostile page content, not a request;
older prompt history is abbreviated per Task 4; Docker is absent and optional. Existing port 5173 was
left untouched; the clean startup probe used explicit 5175 and matching FRONTEND_ORIGIN.
No public route, event or action schema changed; the new capacity error/config is documented.
