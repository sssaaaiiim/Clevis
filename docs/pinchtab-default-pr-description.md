# Default PinchTab hybrid agent

AGENT_DRIVER now defaults to pinchtab. Playwright still launches and owns isolated Chromium,
preview and takeover; the existing Playwright observe/act path remains explicitly selectable.
Startup requires authenticated loopback PinchTab 0.15.2 and rejects public/unauthenticated or
version-mismatched services with setup guidance. No API/event or frontend changes.

The new stdlib helper starts a disposable loopback service with only local attach enabled,
token supplied through environment, recording disabled and child output suppressed. Attach
names are unique so concurrent runs do not collide. The environment example is complete and
contains no credentials. Previously committed credentials still need rotation/history cleanup.

Verified installed `pinchtab --version`, `server --help`, `config schema --print`, and official
v0.15.2 configuration/instances documentation linked in backend/README.md. PINCHTAB_CONFIG,
PINCHTAB_TOKEN, explicit allocation and local attach configuration are from those sources.

Validation: eleven integration cases cover five scripted smoke tasks for the unset default,
the same five for explicit Playwright, and PinchTab privacy/stale/pause/outage. The WebSocket
privacy canary passes. Ten mixed lifecycle runs and three concurrent runs pass with no owned
browser processes left; RSS growth +30.33 MiB within the existing bound. Final gate results are
recorded in docs/phase1-verification.md.

Assumptions: the operator installs/runs PinchTab separately and exports its token in both
terminals; existing private environment overrides are preserved. Fake LLMs were used to avoid
external calls and charges. Real-model and human visual checks were not rerun. This default
change follows the requested product decision; it makes no new token-efficiency claim.
