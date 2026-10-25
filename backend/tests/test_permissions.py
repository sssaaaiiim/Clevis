import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.agent.policy.permissions import RunPermissions, resolve_permissions
from app.agent.policy.validator import PolicyValidator
from app.agent.state import AgentState
from app.core.events import Action, Target
from app.interfaces.browser import Element, Observation
from app.main import create_app
from tests.settings import IsolatedSettings


@pytest.mark.parametrize(
    "entry", ["http://google.com", "google.com/path", "google.com:80", "", "a,b"]
)
def test_invalid_permission_domain(entry: str) -> None:
    with pytest.raises(ValidationError):
        RunPermissions(allowed_domains=[entry])


def test_permission_bounds_and_global_merge() -> None:
    settings = IsolatedSettings(max_steps=10, max_cost_usd=0.5, blocked_domains="blocked.test")
    for request in [RunPermissions(max_steps=11), RunPermissions(max_cost_usd=0.6)]:
        with pytest.raises(ValueError):
            resolve_permissions(request, settings)
    resolved = resolve_permissions(
        RunPermissions(allowed_domains=["localhost"], max_steps=2), settings
    )
    assert resolved.allowed_domains == ["localhost"] and resolved.blocked_domains == [
        "blocked.test"
    ]
    assert resolved.max_steps == 2 and resolved.max_cost_usd == 0.5
    with pytest.raises(ValidationError):
        RunPermissions(allowed_domains=["a.test"], blocked_domains=["a.test"])


async def test_permissions_api_validation_and_effective_response() -> None:
    app = create_app(IsolatedSettings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for permissions in [
                {"allowed_domains": ["http://google.com"]},
                {"max_steps": 99999},
                {"max_cost_usd": 999},
            ]:
                response = await client.post(
                    "/api/runs",
                    json={"goal": "Read", "mode": "headless", "permissions": permissions},
                )
                assert response.status_code == 422 and "error" in response.json()
            response = await client.post(
                "/api/runs",
                json={
                    "goal": "Read",
                    "mode": "headless",
                    "permissions": {"allowed_domains": ["localhost"], "max_steps": 2},
                },
            )
            assert response.status_code == 201
            run = (await client.get("/api/runs/" + response.json()["runId"])).json()
            assert run["permissions"]["allowed_domains"] == ["localhost"]
            assert run["permissions"]["max_steps"] == 2


async def test_state_permissions_restrict_domains_and_submission() -> None:
    validator = PolicyValidator(IsolatedSettings())
    state = AgentState(
        goal="Read",
        permissions=RunPermissions(allowed_domains=["localhost"], allow_form_submit=False),
        last_observation=Observation(
            url="http://localhost",
            elements=[Element(ref="e1", role="button", name="Submit", tag="button", type="submit")],
        ),
    )
    verdict = await validator.validate(
        state, Action(action="navigate", value="https://other.test", rationale="Open")
    )
    assert verdict.verdict == "approval"
    verdict = await validator.validate(
        state, Action(action="click", target=Target(ref="e1"), rationale="Submit")
    )
    assert verdict.verdict == "deny"


@pytest.mark.parametrize(
    "flag,name,kind",
    [
        ("allow_form_submit", "Submit", "submit"),
        ("allow_downloads", "Download", "button"),
        ("allow_uploads", "Upload", "file"),
        ("allow_send_message", "Send message", "submit"),
    ],
)
async def test_disabled_run_capabilities_deny(flag: str, name: str, kind: str) -> None:
    permissions = RunPermissions.model_validate({flag: False})
    state = AgentState(
        goal="Read",
        permissions=permissions,
        last_observation=Observation(
            url="http://localhost",
            elements=[Element(ref="e1", role="button", name=name, tag="button", type=kind)],
        ),
    )
    verdict = await PolicyValidator(IsolatedSettings()).validate(
        state, Action(action="click", target=Target(ref="e1"), rationale="Interact.")
    )
    assert verdict.verdict == "deny" and verdict.tier == 3


async def test_per_run_step_ceiling_is_enforced_by_runner() -> None:
    app = create_app(IsolatedSettings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/runs",
                json={"goal": "Read sample", "mode": "headless", "permissions": {"max_steps": 1}},
            )
            run_id = response.json()["runId"]
            await app.state.service.tasks[run_id]
            record = (await client.get(f"/api/runs/{run_id}")).json()
            assert record["status"] == "failed" and "MAX_STEPS" in record["error"]
            assert record["permissions"]["max_steps"] == 1


def test_disabled_global_cost_ceiling_is_serializable() -> None:
    permissions = resolve_permissions(None, IsolatedSettings(max_cost_usd=0))
    state = AgentState(goal="Read", permissions=permissions)
    assert AgentState.model_validate_json(state.model_dump_json()).permissions == permissions
