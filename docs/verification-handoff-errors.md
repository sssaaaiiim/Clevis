# Verification handoff and visible error summary

The supplied screenshot shows `Failed`, `Run ended`, and a no-progress error after five waits.
That retained preview is read-only. It is distinct from a paused, live controller session.

The task summary now places the result/error directly below its header and above the plan,
with a bounded scroll area for long text. This keeps it above CLEVIS COMMAND. A real React
browser regression injects a long server error, closes the command panel and asserts that the
error's lower edge is above the launcher's upper edge at DSF 1 and 2.

The runner also converts a model-proposed wait into the existing handoff action when the latest
observation contains a human-verification checkbox, or a “Just a moment” title with matching
visible verification text. The action is pydantic validated and still passes through the action
validator, handoff cap and pause/resume machinery. Ordinary waits and loop failures remain.
This is a narrow human-control safeguard, not an injection classifier or challenge solver.
The prompt asks for immediate handoff at interactive human-verification widgets.

Implementation was included in commit `523fbde` during this work; subsequent audit/test commits
retain it. API routes, event shapes and action schema are unchanged. No real LLM or production
challenge was used for testing. The earlier documented Cloudflare limitation still applies.

Verification:

- Targeted backend tests (agent loop, prompts and real frontend): 20 passed in 13.49 seconds.
- `npm test`: 42 passed across 8 files; `npm run build`: passed.
- `ruff check .`: passed; `mypy .`: passed, 91 source files.
- The unit test fixture mocks scrollTo because jsdom does not implement it; production browser
  scrolling and assertions were not disabled or weakened.
- Final full backend suite: pending completion when this note was written.

Security finding: commit `523fbde` includes credential assignments in `backend/.env.example`.
Values were not printed, copied into this report or staged by this task's commits. Rotate the
exposed credentials, restore a placeholder-only example, and decide whether shared history
needs cleaning. This task does not rewrite the user's commit history or overwrite credentials.
