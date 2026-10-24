# Replace the internal agent loop with LangGraph

The agent now runs a compiled LangGraph 1.2.17 graph with async planner, navigator, policy,
executor, outcome/revision, approval-stub and finish nodes. The existing background task,
FastAPI routes, event schemas, preview and takeover code are preserved. The previously reserved
step.validated event is now emitted through EventEmitter; graph updates do not feed the frontend.

Pydantic state validates node inputs and JSON serialization, with capped history, hashed values,
redacted checkpoint projections, terminal budget snapshots and private injected run dependencies.
Node errors are sanitized before checkpointing. Cancellation/pause retain the Phase 1 clock and
control gate; external tracing is disabled. MemorySaver has no automatic TTL and clears on restart.

Verified installed imports and version pin, MemorySaver alias, CompiledStateGraph typing and
1.2.17 NodeCancelledError behavior. Direct OpenRouter SDK calls remain; LangGraph's transitive
langchain-core/LangSmith dependencies do not introduce LangChain agents or model integrations.

Validation: Ruff/mypy/pip check pass; 45 new graph tests and 15 PinchTab integration cases pass.
Final full suite: 376 passed, 20 opt-in skips, 3 failures. All failures are unchanged exact-event
assertions omitting step.validated. No existing Phase 1 test was changed, weakened or skipped.
Detailed commands, earlier transient failures and evidence: docs/phase2-task1-graph.md.

Assumptions: preserve completion only on a valid done action; the always-achieved outcome stub
must not finish tasks prematurely. Existing plan text supplies provisional sub-goal success
conditions; real verification/per-sub-goal policy is deferred. ActionValidator retains its Phase 1
RunRecord signature until the policy task deliberately evolves it. Production approvals remain
permissive stubs; the interrupt/Command test proves persistence on a separate async test graph.

Acceptance blocker: authorize updating only the two expected event lists (three tests) for the
newly required validation event, or revise the emission requirement. No production workaround
distinguishes tests from normal runs.
