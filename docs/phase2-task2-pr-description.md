# Add deterministic agent policy and real approval interruption

Production runs now use per-run PolicyValidator with four risk tiers, exact-host allow/block
lists, cached async DNS/SSRF checks, a browser request boundary, credential/submit/payment/file
heuristics and bounded hash-only extraction tracking. Every verdict emits step.validated;
Tier 2 emits approval.required and interrupts until an explicit approved/denied Command.
Denied actions never execute; three consecutive policy denials fail the sub-goal/run.

The existing task keeps resources alive during approval and Stop closes them. Duplicate decisions
cannot preapprove a later action. Logs contain runId/tier/action type only. Preview/input protocols,
routes and action schema are unchanged. The explicitly requested additive run.paused variant
contains reason=approval and a sanitized ApprovalRequest. No approval endpoints/UI are added
before Task 3. Verdict.decision is compatible with the existing approval event vocabulary.

Validation: **75 policy tests pass**, including production graph interrupt/approved/denied
paths, hash-only cross-domain flow, stop, duplicate decisions, safe logs, mocked DNS and a real
Chromium private-address boundary. Ruff passes; mypy passes for 125 files. Installed Playwright
1.64.0 routing/service-worker APIs and LangGraph 1.2.17 interrupt/Command/GraphInterrupt APIs
were verified directly. No paid live-model tests were run.

**Final full suite: 454 passed, 20 existing opt-in skips in 147.51s.** The user explicitly
approved local configuration for legacy fixtures and replacement of the obsolete auto-approval
test (`6d55807`). IsolatedSettings now explicitly permits the local demo workflows; PolicySettings
and production Settings retain secure defaults, verified by a regression test. The updated
approval case verifies no act before consent, checkpoint interruption, approved resumption,
events, result and cleanup. All other legacy assertions and timing limits are unchanged.

The approval case, both local headless/headed form cases and all strict policy cases also
passed together (78 passed in 6.61s). The previous eleven compatibility failures are resolved;
their historical outputs remain in the verification report rather than being erased.

Assumptions/limits: exact domain matching, goal-text credential provenance heuristic, transaction
heuristics, exact-prefix extraction hashes (not semantic/all-observation tracking), and a DNS
rebinding window between policy resolution and browser lookup. Network interception is not a
complete egress firewall. Approval auth/IDs/UI and durable recovery remain Task 3. The separate
preview ACK/HiDPI reliability findings are unchanged. Full evidence: docs/phase2-task2-policy.md.
