# Per-run permissions, navigation hardening and local evaluations

Runs now accept validated permissions and budget ceilings and expose resolved permissions in
GET run responses. The frontend sends explicit overrides only from a collapsed pre-run panel;
server domain configuration is never fetched or pre-filled.

The policy and browser independently enforce network restrictions. Context routing, CDP response
interception before HTTP redirect following, and fresh post-navigation DNS checks protect page-driven
navigation. Blocks record hostnames only, clear the page, and fail in strict mode or re-observe in
development mode. Initial popup HTTP redirects fail closed before a target session exists; ordinary
popups continue to work. Preview/input implementation files were not modified.

The evaluation harness covers 23 deterministic real-browser/fake-model scenarios across five
categories, plus a recorder privacy unit test and five explicit opt-in paid live scenarios.
Results contain only safe identifiers, booleans and usage counters. Earlier failed attempts remain
in the appended result history; the report uses each scenario's latest result.

Validation: eval **24 passed / 5 paid skipped**; frontend **57 passed**, build succeeds;
Ruff and backend mypy **152 files** pass. Full backend: **531 passed / 25 skipped**, exit 0.
Form and popup tripwires each passed 30/30 separate runs after fixes. See phase2-eval-report.md
for raw results, earlier failures and limits.
No paid model calls were made.
The user approved adding permissions to the existing exact-key GET assertion. Only that
expected set changed; its SSE replay, final-state and cleanup assertions pass unchanged.
All other assertions and timing limits remain unchanged. Verification also exposed real blocked-loader
and popup-selection races; these were fixed in the security guard with new deterministic coverage.
The existing HiDPI checkbox flake was recorded separately without changing preview/input behavior.

Assumptions / limits:

- Empty domain overrides inherit environment defaults; blocked hosts merge and global ceilings win.
  With global cost=0 (disabled), a positive per-run ceiling is allowed; resolved disabled cost is null.
- Capability=true retains global approval checks; it does not enable unsupported upload/download features.
- Task 3's revision-limit semantics are preserved; max_attempts counts revisions after initial failure.
- Ordered evaluation milestones permit intervening observation/budget events; existing unit tests
  continue checking full exact sequences.
- HTTP redirect interception uses installed Playwright 1.64.0 and documented CDP Fetch response-stage
  fields/commands (continueResponse is experimental and exercised in Chromium). Route.fetch with
  max_redirects=0 protects the initial popup gap. These APIs were verified against official docs.
- Extra interception is skipped when network restrictions are explicitly disabled, preserving local
  Chromium address-space classification. Restrictive initial popup redirects are conservatively blocked,
  including public targets; OAuth/popups that redirect may need the destination opened in the current tab.
- DNS rechecking does not pin the actual peer IP; production still needs network egress controls.
- Real PinchTab-server behavior, paid model accuracy/cost and human visual review were not tested here.
