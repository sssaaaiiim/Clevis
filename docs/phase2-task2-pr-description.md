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

Validation: **74 new policy tests pass**, including production graph interrupt/approved/denied
paths, hash-only cross-domain flow, stop, duplicate decisions, safe logs, mocked DNS and a real
Chromium private-address boundary. Ruff passes; mypy passes for 125 files. Installed Playwright
1.64.0 routing/service-worker APIs and LangGraph 1.2.17 interrupt/Command/GraphInterrupt APIs
were verified directly. No paid live-model tests were run.

**Acceptance blocked:** latest full run is **441 passed, 20 existing opt-in skips, 11 failed**
in 200.68s. Ten legacy browser/preview/takeover cases assume unrestricted localhost/form flows;
one explicitly requires the old approval gate to auto-approve and emit no approval.required.
Both local form cases pass unchanged with explicit per-command development settings, which is
diagnostic evidence only. No existing test file or production safety default was weakened.

Required decisions: authorize explicit local/test approval configuration in legacy fixtures,
and replace the obsolete approval-stub test with real pause/consent assertions. These conflict
with the task's blanket prohibition on editing earlier tests; questions are pending.

Assumptions/limits: exact domain matching, goal-text credential provenance heuristic, transaction
heuristics, exact-prefix extraction hashes (not semantic/all-observation tracking), and a DNS
rebinding window between policy resolution and browser lookup. Network interception is not a
complete egress firewall. Approval auth/IDs/UI and durable recovery remain Task 3. The separate
preview ACK/HiDPI reliability findings are unchanged. Full evidence: docs/phase2-task2-policy.md.
