"""Unit tests for auth module."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core.auth import extract_user_from_payload, verify_token


@pytest.mark.unit
@pytest.mark.asyncio
async def test_verify_token_missing_kid():
    """Token without key ID should raise 401."""
    fake_credentials = AsyncMock()
    fake_credentials.credentials = "fake.token.here"

    with patch("app.core.auth.jwt") as mock_jwt:
        mock_jwt.get_unverified_header.return_value = {}

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(fake_credentials)

        assert exc_info.value.status_code == 401
        assert "key ID" in exc_info.value.detail.lower()


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

    user = await extract_user_from_payload(payload)

    assert user["user_id"] == "user-123"
    assert user["username"] == "testuser"
    assert user["email"] == "test@example.com"
    assert user["name"] == "Test User"
