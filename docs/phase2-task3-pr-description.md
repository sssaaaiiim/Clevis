# Outcome verification, planner revision and authenticated approvals

Runs now verify each completed/capped sub-goal with a bounded, low-output LLM call. Unsuccessful
checks produce safe revision feedback, retry Navigator and then re-plan remaining work, preserving
completed goals. Exhausted attempts return an explained partial result.

Tier 2 actions pause with a UUID-bound request. A native frontend approval modal sends an
authenticated approve/deny decision; the original graph task resumes with Command. Stale IDs,
wrong tokens, duplicates, deadlines and Stop are tested. approvalToken stays in React state only.
Preview and takeover implementation are unchanged. Additive API/event/action fields are documented.

Validation: backend **480 passed, 20 opt-in skipped**; Ruff and mypy (132 files) pass;
frontend **49 tests pass** and build succeeds. See phase2-task3-verification.md for actual before/after results, compatibility
expectation corrections, privacy/cleanup coverage and installed LangGraph signature verification.
No paid live-model calls were made.

Assumptions: follow the explicit first-retry/second-replan routing table; include at most 500
redacted visible-text characters for plain confirmations alongside 50 elements/3 summaries;
resume inside the original runner to retain its private dependencies. Known limits: in-memory
approval recovery only, model accuracy/cost and manual visual checks not verified.
