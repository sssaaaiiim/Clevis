"""Request minimums must not invalidate a stricter server-owned budget."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.policy.permissions import RunPermissions, resolve_permissions
from app.agent.state import AgentState
from app.main import create_app
from tests.settings import IsolatedSettings


def test_subcent_global_cost_ceiling_roundtrips_as_effective_permissions() -> None:
    settings = IsolatedSettings(max_cost_usd=0.005)
    permissions = resolve_permissions(None, settings)
    state = AgentState(goal="Read", permissions=permissions)
    restored = AgentState.model_validate_json(state.model_dump_json())
    assert restored.permissions and restored.permissions.max_cost_usd == 0.005
    with pytest.raises(ValueError):
        resolve_permissions(RunPermissions(max_cost_usd=0.005), settings)


async def test_subcent_request_rejected_without_breaking_server_default() -> None:
    app = create_app(IsolatedSettings(max_cost_usd=0.005))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            rejected = await client.post("/api/runs", json={
                "goal": "Read", "mode": "headless", "permissions": {"max_cost_usd": 0.005},
            })
            assert rejected.status_code == 422
            created = await client.post("/api/runs", json={"goal": "Read", "mode": "headless"})
            assert created.status_code == 201
            run_id = created.json()["runId"]
            await app.state.service.tasks[run_id]
            record = (await client.get("/api/runs/" + run_id)).json()
            assert record["status"] == "finished"
            assert record["permissions"]["max_cost_usd"] == 0.005
