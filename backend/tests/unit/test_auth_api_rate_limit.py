"""Tests for rate-limit enforcement on POST /api/auth/token.

Separate file from test_token_exchange.py, per this repo's existing
convention of one file per concern within tests/unit/. Unlike the chat
endpoint, this endpoint has no authenticated identity yet (it's the token
exchange itself), so the limiter keys on client IP instead of user_id -
see app.services.rate_limiter_service.check_auth_rate_limit.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import SystemSettings

# Bucket state is reset automatically before/after every test by the
# autouse _reset_rate_limit_state fixture in tests/conftest.py.


def _set_auth_capacity(db_session, capacity: int) -> None:
    db_session.add(
        SystemSettings(
            id="default",
            rate_limit_auth_capacity=capacity,
            rate_limit_auth_refill_per_minute=1,
            updated_by="admin-1",
        )
    )
    db_session.commit()


def _mock_keycloak_success():
    """Patch app.api.auth.httpx.AsyncClient to return a successful token
    response, mirroring test_token_exchange.py's mocking shape - this
    endpoint's rate limiting must be checked before any Keycloak call is
    even attempted, but the happy-path (not-yet-limited) requests still
    need a mocked downstream response to reach 200.
    """
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(
        return_value={
            "access_token": "fake-token",
            "token_type": "Bearer",
            "refresh_token": "fake-refresh",
            "expires_in": 300,
        }
    )
    mock_client_instance = AsyncMock()
    mock_client_instance.post = AsyncMock(return_value=mock_response)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)
    return patch("app.api.auth.httpx.AsyncClient", return_value=mock_client_instance)


@pytest.mark.unit
def test_token_endpoint_returns_429_after_capacity_exhausted_for_same_ip(client, db_session):
    _set_auth_capacity(db_session, capacity=1)

    with _mock_keycloak_success():
        first = client.post(
            "/api/auth/token",
            json={"code": "auth_code", "redirect_uri": "http://localhost:3000/"},
        )
        second = client.post(
            "/api/auth/token",
            json={"code": "auth_code", "redirect_uri": "http://localhost:3000/"},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == "rate_limit_exceeded"


@pytest.mark.unit
def test_token_endpoint_429_response_includes_retry_after_header(client, db_session):
    _set_auth_capacity(db_session, capacity=1)

    with _mock_keycloak_success():
        client.post(
            "/api/auth/token",
            json={"code": "auth_code", "redirect_uri": "http://localhost:3000/"},
        )
        response = client.post(
            "/api/auth/token",
            json={"code": "auth_code", "redirect_uri": "http://localhost:3000/"},
        )

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0
