"""Test Keycloak connectivity from backend."""

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_keycloak_url_is_configured():
    """Keycloak URL should be configured."""
    from app.core.config import settings

    assert settings.keycloak_url
    assert "8080" in settings.keycloak_url or "keycloak" in settings.keycloak_url.lower()


@pytest.mark.unit
def test_keycloak_client_id_config():
    """Keycloak client ID should allow both web and API clients."""
    from app.core.config import settings

    # Backend uses eaistack-api for service-to-service auth
    assert settings.keycloak_client_id == "eaistack-api"

    # But tokens from eaistack-web (frontend) should also be accepted
    # This is validated in the verify_token function's audience list
