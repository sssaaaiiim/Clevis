# Phase 2 Task 1: LangGraph skeleton

**Acceptance remains blocked by contradictory event-test requirements.** The requested
step.validated emission is implemented using its existing schema. Phase 1 tests were not edited,
and their exact event lists omit that event. No test skipping, filtering or test-only runtime mode
was introduced to conceal the conflict.

Implemented: pinned LangGraph 1.2.17, serializable pydantic AgentState/SubGoal/StepRecord/BudgetState,
async nodes, pure routing, one compiled MemorySaver-backed graph, and a lifecycle bridge preserving
injected browser/preview/validator/skills/store/LLM/emitter interfaces. The original ActionValidator
signature still receives RunRecord. Direct OpenRouter code and public routes/schemas are untouched.

The production graph emits step.validated; the production approval/outcome/revision nodes remain
explicit stubs. External completion still requires a nonempty successful done result. Otherwise,
an always-achieved outcome stub would finish tasks before the model's done action. The final
sub-goal remains active until done. Per-sub-goal metadata uses the two new configuration defaults;
real success-condition evaluation belongs to the later outcome task. Completed goal IDs are
preserved on planner re-entry, with new remaining IDs allocated after them.

Privacy: raw executable action values and original observations are held outside graph state.
Checkpoint actions omit value; StepRecord hashes it. Stored observation/history projections are
redacted. Exceptions are sanitized before the checkpointer's error channels see them. Frames,
browser/LLM objects, tokens and API keys are excluded from state. External tracing is disabled
in a scoped tracing_context even if the process has unrelated tracing environment settings.

Version/API verification: installed 1.2.17 imports interrupt/Command from langgraph.types,
MemorySaver from langgraph.checkpoint.memory (alias InMemorySaver), StateGraph/START/END from
langgraph.graph, and CompiledStateGraph from langgraph.graph.state (four generic parameters).
The new NodeCancelledError behavior was verified in installed langgraph/errors.py and handled in
the bridge. The async checkpoint interrupt test uses Command to resume the same thread ID.
Official sources consulted:
- https://pypi.org/project/langgraph/1.2.17/
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.langchain.com/oss/python/langgraph/interrupts

LangGraph transitively depends on langchain-core and LangSmith; no LangChain LLM integration or
agent/chain framework is used in application code. pip check reports no broken requirements.
pip's large-wheel download stalled, so installation completed with uv pip against the same venv.

Initial full suite: **364 passed, 20 opt-in skips, 3 failures in 148.88s**. The failures are:
- tests/test_runner.py::test_full_ordered_run
- tests/test_browser_integration.py::test_real_browser_runner_and_sse
- tests/test_playwright_headed.py::test_headed_scripted_form_runner (shares the same expected list)
All three runs reached finished; the assertions reject the new step.validated events.
No existing Phase 1 test file or assertion was changed. A transient five-second security-test
timeout in an earlier focused run passed on its isolated rerun and on the full suite; its timeout
and assertion were not changed.

The new tests cover JSON serialization, every router branch, actual node/event order, budget
snapshots, separate concurrent threads, capped history, value and error-channel privacy,
approval stub routing, interrupt/Command recovery, and <2s cancellation in navigator/executor.
Final results:

| Gate | Actual result |
|---|---|
| `pytest -q` | **376 passed, 20 skipped, 3 failed in 147.42s**. Only the three exact-event assertion failures listed above remain. |
| `pytest -q tests/test_graph_revision.py tests/test_graph_execution.py tests/test_graph_budgets.py tests/test_graph_routing.py tests/test_graph_state.py` | **45 passed in 0.57s**. |
| `PINCHTAB_URL=managed pytest -q -m pinchtab` | **15 passed, 382 deselected in 41.77s**. The fixture creates an authenticated ephemeral loopback service; managed is a sentinel, never a remote destination. |
| `ruff check .` | **All checks passed**. |
| `mypy .` | **Success, 111 source files**. |
| `pip check` | **No broken requirements found**. |

The 20 skips are the existing opt-in five paid live cases and fifteen local PinchTab cases;
the latter were exercised separately above. No skip conditions were added. A previous full run
also hit two unchanged preview assertions (animation throttle and HiDPI iframe takeover);
both passed in isolation (2 passed in 4.06s) and in the final full run. Those failures are recorded,
not concealed by adjusting test timing or preview code. Another focused run of graph, runner,
prompts, budgets, pause/resume and privacy tests passed 80 cases in 11.10s.

The PinchTab command was initially rejected by automatic approval review because managed was
mistaken for an unverified destination. Read-only inspection established the fixture's generated
token, 127.0.0.1 bind, ephemeral port and owned-process cleanup. The same local-only test was
then approved and completed; no safety check was bypassed.

No real-model/browser-account actions were taken. Stop tests explicitly cancel a ten-second
navigator or executor operation, assert completion under two seconds, verify client/browser
closure, run.stopped emission, and a terminal stopped checkpoint.

Remaining decision: to meet the all-tests-pass criterion, authorize adding step.validated to
the two expected-event lists (three test cases share them), preserving all other assertions.
Alternatively remove the new event emission, which would fail the explicit Phase 2 requirement.
No test-dependent production mode or suppression was introduced. This task is not fully accepted
until that requirement conflict is resolved.

Scope: no frontend, preview, input relay, route or event-schema changes. No policy engine,
real outcome checker, approvals UI, database, accounts, or paid/live model calls were added.
