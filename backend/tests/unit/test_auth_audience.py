"""Test JWT audience validation."""

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core.auth import verify_token


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audience_validation_with_real_jwt():
    """Test that audience validation works correctly with PyJWT.

    This test creates a real JWT token and verifies the audience check.
    """
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.utils import to_base64url_uint

    # Generate a test key pair
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    # Create a JWT with eaistack-web audience
    token_data = {
        "sub": "test-user",
        "preferred_username": "testuser",
        "email": "test@example.com",
        "aud": "eaistack-web",  # Frontend client
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }

    token = jwt.encode(token_data, private_key, algorithm="RS256", headers={"kid": "test-key"})

    # Mock the JWKS endpoint with properly base64url-encoded values
    public_numbers = public_key.public_numbers()
    mock_jwks = {
        "keys": [
            {
                "kid": "test-key",
                "kty": "RSA",
                "use": "sig",
                "n": to_base64url_uint(public_numbers.n).decode("utf-8"),
                "e": to_base64url_uint(public_numbers.e).decode("utf-8"),
            }
        ]
    }

    # Mock the credentials
    fake_credentials = AsyncMock()
    fake_credentials.credentials = token

    with patch("app.core.auth.get_keycloak_public_key") as mock_get_key:
        # Mock must be async since get_keycloak_public_key is async
        async def mock_async_get_key():
            return mock_jwks
        mock_get_key.side_effect = mock_async_get_key

        result = await verify_token(fake_credentials)

        assert result["sub"] == "test-user"
        assert result["aud"] == "eaistack-web"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_audience_validation_rejects_invalid_audience():
    """Token with invalid audience should be rejected."""
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.utils import to_base64url_uint

    # Generate a test key pair
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    # Create a JWT with wrong audience
    token_data = {
        "sub": "test-user",
        "preferred_username": "testuser",
        "aud": "wrong-client",  # Invalid audience
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }

    token = jwt.encode(token_data, private_key, algorithm="RS256", headers={"kid": "test-key"})

    # Mock the JWKS with properly base64url-encoded values
    public_numbers = public_key.public_numbers()
    mock_jwks = {
        "keys": [
            {
                "kid": "test-key",
                "kty": "RSA",
                "n": to_base64url_uint(public_numbers.n).decode("utf-8"),
                "e": to_base64url_uint(public_numbers.e).decode("utf-8"),
            }
        ]
    }

    fake_credentials = AsyncMock()
    fake_credentials.credentials = token

    with patch("app.core.auth.get_keycloak_public_key") as mock_get_key:
        # Mock must be async since get_keycloak_public_key is async
        async def mock_async_get_key():
            return mock_jwks
        mock_get_key.side_effect = mock_async_get_key

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(fake_credentials)

        assert exc_info.value.status_code == 401
        assert "Invalid audience" in exc_info.value.detail or "Invalid token" in exc_info.value.detail
