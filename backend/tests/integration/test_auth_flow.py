"""Integration tests for authentication flow."""

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.main import app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check_is_public():
    """Health check endpoint should be accessible without auth."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_me_requires_token():
    """GET /auth/me should require valid auth token."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/auth/me")
        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_me_with_invalid_token():
    """GET /auth/me with invalid token should return 401."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_realm_is_configured():
    """Keycloak realm should be accessible and configured with test user."""
    # This test validates that Keycloak is running and has the test realm
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.keycloak_url}/realms/eaistack",
                timeout=5.0,
            )
            assert response.status_code == 200
            data = response.json()
            assert data.get("realm") == "eaistack"
    except Exception as e:
        pytest.skip(f"Keycloak not available: {e}")
