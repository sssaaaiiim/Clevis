# Phase 2 readiness notes

These are notes, not implemented Phase 2 features.

- `app/interfaces/validator.py` defines ActionValidator and the Phase 1 AllowAllValidator.
  `app/agent/steps.py::validate` calls it before acting; `app/runtime.py` composes the default.
  Replace that composition with a policy validator rather than importing policy into browser drivers.
  A denied action already consumes a step, enters feedback and is not executed.
- `app/interfaces/skills.py` defines SkillProvider/EmptySkillProvider. The runner calls get_skills
  before planning, but currently does not use returned skills. A future trusted skill representation
  needs explicit provenance, applicability and prompt placement; never promote website text to
  trusted skill instructions. No skill library exists in Phase 1.
- Policy tiers need the current action kind, target ref/description, value and plan_step_id, plus
  resolved element generation, current origin, destination URL, form purpose and side-effect context.
  A ref alone cannot tell whether a click sends email, purchases, deletes or merely navigates.
  Keep sensitive values out of approval events and policy logs.
- `step.validated` and `approval.required` are reserved event models, currently not emitted.
  Approval state, durable decisions and permission scopes need a separate design; human login
  handoff is not policy approval. Preserve existing API/event contracts or document additive changes.
- First refactors: introduce explicit run-history retention, shared-store/task ownership before
  multiple workers, and admission scheduling beyond the current per-process MAX_CONCURRENT_RUNS.
  The current finite RSS test does not establish unlimited historical-run memory bounds.
- Preserve cancellation/quiescence contracts at every validator/skill/network boundary. On resume,
  observations and refs must remain fresh. PinchTab reconciliation can omit ambiguous elements;
  treat adapter availability/limitations as capabilities rather than silently switching drivers.
- Domain/private-network URL controls, richer injection defenses, accounts, persistent database,
  approval dialogs and durable skill storage are deliberately absent. Add focused threat models
  and tests before enabling them; do not claim the current local operator product is multi-tenant.
