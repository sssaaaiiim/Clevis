from httpx import ASGITransport, AsyncClient

from app.main import create_app
from tests.settings import PolicySettings


async def test_approval_cors_preflight_accepts_authorization_header() -> None:
    app = create_app(PolicySettings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options("/api/runs/example/approve", headers={
            "Origin": app.state.service.settings.frontend_origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        })
    assert response.status_code == 200
    assert "authorization" in response.headers["access-control-allow-headers"].lower()

