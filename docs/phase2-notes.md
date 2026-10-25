# Phase 2 completion and later-phase integration notes

These are extension notes, not implementations of Phase 3 or Phase 4.

## Current composition

`backend/app/runtime.py` injects a per-run `PolicyValidator`, browser, LLM sessions,
`SkillProvider`, store and emitter into the LangGraph bridge. `backend/app/agent/graph.py`
compiles the node graph once; `routing.py` contains pure conditional edges. Approvals use
`interrupt()` and authenticated decisions delivered to the original run task with `Command`.
The outcome verifier checks completion boundaries; revisions preserve completed sub-goals.
Per-run permissions and independent browser navigation checks supplement policy decisions.

## Phase 3: untrusted-content defenses

- `backend/app/agent/nodes/navigator.py`: place a future classifier after the fresh observation
  is redacted and before actor prompt construction. Classifier output must stay separate from
  website instructions; preserve random untrusted delimiters and bounded prompt projections.
- `backend/app/agent/nodes/policy_check.py`: combine that signal with deterministic policy
  before executor routing. An injection signal must never override a Tier 3 deny or silently
  authorize a Tier 2 action. Keep decisions and reasons structured and free of page content.
- Define a serializable classification result, cancellation behavior and adversarial evaluation
  criteria before implementation. The current visible-injection baseline is not an attack suite.
- Keep SSRF egress enforcement and actual-peer/DNS binding separate from an LLM classifier.

## Phase 4: skills

`backend/app/interfaces/skills.py` remains the injection boundary. The bridge currently calls
`get_skills` before planning but does not use its result. Move trusted retrieval into
`planner_node` when implementing skills so planner re-entry can retrieve appropriate skills too.
A future retriever should receive goal/current origin, return bounded provenance-bearing entries,
and keep website content outside trusted skill instructions. No skill library is implemented here.

## Refactors before wider deployment

- Add bounded retention for terminal run/store/capability summaries; terminal graph history now
  drops observation/action/approval payloads, but process-resident run summaries still accumulate.
- Add durable shared task/store ownership before multiple workers. MemorySaver is not a durable
  browser-session recovery mechanism; process restart clears runs and graph state.
- Maintain exact approval-ID binding, independent input/preview/approval tokens and takeover
  cancellation epochs. Resume must always obtain a fresh observation before proposing actions.
- Preserve the documented conservative initial-popup redirect rejection and plan a separately
  reviewed network-egress/peer-binding design; do not claim DNS rechecks pin the actual peer IP.
- Resolve the historical credential finding documented in phase2-verification.md before release.
