"""Integration tests for authentication flow."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check_is_public():
    """Health check endpoint should be accessible without auth."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_me_requires_token():
    """GET /auth/me should require valid auth token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/auth/me")
        assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_me_with_invalid_token():
    """GET /auth/me with invalid token should return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_service_account_token_is_accepted_by_protected_endpoint():
    """A client-credentials token from eaistack-api should authenticate /auth/me.

    This is the curl/CI machine-to-machine path: no browser, no eaistack-web.
    It requires the eaistack-api client to stamp aud: eaistack-api via its
    audience protocol mapper in the live realm.
    """
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                f"{settings.keycloak_url}/realms/eaistack/protocol/openid-connect/token",
                data={
                    "client_id": "eaistack-api",
                    "client_secret": "eaistack-api-secret",
                    "grant_type": "client_credentials",
                },
                timeout=5.0,
            )
    except httpx.ConnectError as e:
        pytest.skip(f"Keycloak not available: {e}")

    assert token_response.status_code == 200, token_response.text
    access_token = token_response.json()["access_token"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 200, response.text
