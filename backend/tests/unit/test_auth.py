"""Unit tests for auth module."""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException
from app.core.auth import verify_token, get_current_user


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
async def test_get_current_user_missing_sub():
    """Payload without sub claim should raise 401."""
    payload = {"preferred_username": "testuser"}

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(payload)

    assert exc_info.value.status_code == 401
    assert "subject claim" in exc_info.value.detail.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_current_user_success():
    """Valid payload should return user info."""
    payload = {
        "sub": "user-123",
        "preferred_username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
    }

    user = await get_current_user(payload)

    assert user["user_id"] == "user-123"
    assert user["username"] == "testuser"
    assert user["email"] == "test@example.com"
    assert user["name"] == "Test User"
