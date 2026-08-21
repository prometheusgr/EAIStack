"""Unit tests for auth module."""

from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException

from app.core.auth import extract_user_from_payload, require_admin, verify_token


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_token_missing_kid():
    """Token without key ID should raise 401."""
    fake_credentials = AsyncMock()
    fake_credentials.credentials = "fake.token.here"

    mock_jwks = {"keys": []}

    with patch("app.core.auth.jwt.get_unverified_header") as mock_get_header, patch(
        "app.core.auth.get_keycloak_public_key", return_value=mock_jwks
    ):
        mock_get_header.return_value = {}

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(fake_credentials)

        assert exc_info.value.status_code == 401
        assert "key id" in exc_info.value.detail.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_user_from_payload_missing_sub():
    """Payload without sub claim should raise 401."""
    payload = {"preferred_username": "testuser"}

    with pytest.raises(HTTPException) as exc_info:
        await extract_user_from_payload(payload)

    assert exc_info.value.status_code == 401
    assert "subject claim" in exc_info.value.detail.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_extract_user_from_payload_success():
    """Valid payload should return user info."""
    payload = {
        "sub": "user-123",
        "preferred_username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
    }

    user = await extract_user_from_payload(payload, access_token="raw.jwt.string")

    assert user["user_id"] == "user-123"
    assert user["username"] == "testuser"
    assert user["email"] == "test@example.com"
    assert user["name"] == "Test User"
    assert user["access_token"] == "raw.jwt.string"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_token_rejects_invalid_audience():
    """Token with only 'account' audience should be rejected.

    Real Keycloak tokens without a protocol mapper targeting eaistack-api
    carry only 'account' in the aud claim. The backend must reject these
    until the realm's audience mapper is configured.
    """
    fake_credentials = AsyncMock()
    fake_credentials.credentials = "header.payload.signature"

    mock_key = AsyncMock()
    mock_jwks = {"keys": [{"kid": "test-key-id"}]}

    with patch("app.core.auth.jwt.get_unverified_header") as mock_get_header, patch(
        "app.core.auth.jwt.PyJWK"
    ) as mock_pyjwk, patch("app.core.auth.jwt.decode") as mock_decode, patch(
        "app.core.auth.get_keycloak_public_key", return_value=mock_jwks
    ):
        mock_get_header.return_value = {"kid": "test-key-id"}
        mock_pyjwk.return_value = mock_key

        # jwt.decode is called twice: once with verify_aud=True (fails),
        # then with verify_aud=False to extract the invalid aud for logging
        mock_decode.side_effect = [
            jwt.InvalidAudienceError("Invalid audience"),
            {
                "sub": "user-123",
                "preferred_username": "testuser",
                "aud": "account",
            },
        ]

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(fake_credentials)

        assert exc_info.value.status_code == 401
        assert "invalid audience" in exc_info.value.detail.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_token_accepts_web_client_audience():
    """Token with eaistack-web audience should be accepted.

    After the Keycloak realm's audience mapper is configured,
    tokens will carry eaistack-web (or eaistack-api for service accounts).
    """
    fake_credentials = AsyncMock()
    fake_credentials.credentials = "header.payload.signature"

    mock_key = AsyncMock()
    mock_jwks = {"keys": [{"kid": "test-key-id"}]}

    with patch("app.core.auth.jwt.get_unverified_header") as mock_get_header, patch(
        "app.core.auth.jwt.PyJWK"
    ) as mock_pyjwk, patch("app.core.auth.jwt.decode") as mock_decode, patch(
        "app.core.auth.get_keycloak_public_key", return_value=mock_jwks
    ):
        mock_get_header.return_value = {"kid": "test-key-id"}
        mock_pyjwk.return_value = mock_key
        mock_decode.return_value = {
            "sub": "user-123",
            "preferred_username": "testuser",
            "aud": ["account", "eaistack-api"],
        }

        result = await verify_token(fake_credentials)
        assert result["sub"] == "user-123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_token_accepts_api_client_audience():
    """Token with eaistack-api audience should be accepted.

    Service-to-service calls (future: MCP, backend-to-backend) may use
    the eaistack-api client audience.
    """
    fake_credentials = AsyncMock()
    fake_credentials.credentials = "header.payload.signature"

    mock_key = AsyncMock()
    mock_jwks = {"keys": [{"kid": "test-key-id"}]}

    with patch("app.core.auth.jwt.get_unverified_header") as mock_get_header, patch(
        "app.core.auth.jwt.PyJWK"
    ) as mock_pyjwk, patch("app.core.auth.jwt.decode") as mock_decode, patch(
        "app.core.auth.get_keycloak_public_key", return_value=mock_jwks
    ):
        mock_get_header.return_value = {"kid": "test-key-id"}
        mock_pyjwk.return_value = mock_key
        mock_decode.return_value = {
            "sub": "service-account",
            "preferred_username": "eaistack-api",
            "aud": "eaistack-api",
        }

        result = await verify_token(fake_credentials)
        assert result["sub"] == "service-account"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_admin_passes_with_admin_realm_role():
    """A user whose token carries the admin realm role should pass through unchanged."""
    user = {
        "user_id": "user-123",
        "username": "testuser",
        "token": {
            "sub": "user-123",
            "realm_access": {"roles": ["admin", "offline_access"]},
        },
    }

    result = await require_admin(user)

    assert result == user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_admin_rejects_user_without_admin_role():
    """A user whose token lacks the admin realm role should get a 403."""
    user = {
        "user_id": "user-456",
        "username": "regular_user",
        "token": {
            "sub": "user-456",
            "realm_access": {"roles": ["offline_access"]},
        },
    }

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user)

    assert exc_info.value.status_code == 403
    assert "admin" in exc_info.value.detail.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_current_user_includes_raw_access_token():
    """get_current_user must expose the raw bearer token string (not just the
    decoded payload), so callers (e.g. the /chat endpoint, for forwarding to
    the doc-search MCP server) can forward it onward without re-encoding it.
    """
    from app.core.auth import get_current_user

    fake_credentials = AsyncMock()
    fake_credentials.credentials = "the.raw.jwt"

    payload = {"sub": "user-123", "preferred_username": "testuser"}

    user = await get_current_user(payload=payload, credentials=fake_credentials)

    assert user["access_token"] == "the.raw.jwt"
    assert user["user_id"] == "user-123"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_admin_rejects_token_with_no_realm_access_claim():
    """A token with no realm_access claim at all (e.g. no realm roles configured)
    should be rejected, not crash on a missing key.
    """
    user = {
        "user_id": "user-789",
        "username": "no_roles_user",
        "token": {"sub": "user-789"},
    }

    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user)

    assert exc_info.value.status_code == 403
