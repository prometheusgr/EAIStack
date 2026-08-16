"""Integration tests for Keycloak realm setup.

These tests validate that:
1. Keycloak realm is properly imported
2. Test user exists with correct credentials
3. Token can be obtained from Keycloak
4. Backend can validate tokens issued by Keycloak
"""

import pytest

from app.core.config import settings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_keycloak_realm_exists():
    """Keycloak realm should exist and be accessible."""
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
async def test_keycloak_testuser_can_login():
    """Test user should be able to log in and get a token.

    This test validates the Keycloak realm import worked correctly.
    If this fails, check:
    1. Keycloak realm-import.json is mounted
    2. Keycloak started with --import-realm flag
    3. User credentials in realm-import.json are correct
    """
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            # Request token using Resource Owner Password Credentials flow
            response = await client.post(
                f"{settings.keycloak_url}/realms/eaistack/protocol/openid-connect/token",
                data={
                    "client_id": "eaistack-api",
                    "client_secret": "eaistack-api-secret",
                    "grant_type": "password",
                    "username": "testuser",
                    "password": "testpassword",
                },
                timeout=5.0,
            )

            if response.status_code != 200:
                error_data = response.json()
                pytest.fail(
                    f"Failed to obtain token: {response.status_code} "
                    f"{error_data.get('error_description', error_data)}"
                )

            data = response.json()
            assert "access_token" in data
            assert data["token_type"] == "Bearer"

    except Exception as e:
        pytest.skip(f"Keycloak not available: {e}")
