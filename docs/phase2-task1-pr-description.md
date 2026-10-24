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

Validation after the user-approved event expectation update (`7f0d99c`): **379 passed,
20 opt-in skips in 146.22s**; Ruff and mypy pass (112 source files). The three affected
lifecycle tests pass together, including their subsequent status, privacy and cleanup checks.
The per-action sequence is shared by lifecycle and graph tests; all other assertions are preserved.
Earlier verification also passed 45 new graph tests and 15 opt-in PinchTab integration cases;
PinchTab and paid live cases were not selected for this follow-up.

Preview investigation, without code/timing changes: animation failed 1/30 isolated and 4/30
alongside full suites (47 received versus 46 acknowledged); HiDPI iframe takeover failed 2/30
isolated and 9/30 alongside suites (checkbox remained unchecked). The first loaded suite had
that HiDPI failure; the next loaded suite and final standalone suite passed. These remain
reliability issues despite the passing final gate. Details: docs/preview-repetition-results.md.

Assumptions: preserve completion only on a valid done action; the always-achieved outcome stub
must not finish tasks prematurely. Existing plan text supplies provisional sub-goal success
conditions; real verification/per-sub-goal policy is deferred. ActionValidator retains its Phase 1
RunRecord signature until the policy task deliberately evolves it. Production approvals remain
permissive stubs; the interrupt/Command test proves persistence on a separate async test graph.

The event expectation blocker is resolved with explicit authorization. Next action: diagnose
ACK shutdown completion and HiDPI iframe click delivery before proposing preview fixes. No
production workaround distinguishes tests from normal runs; no paid model calls were made.
