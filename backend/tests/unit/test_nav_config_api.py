"""Unit tests for the admin-only GET /api/settings/nav-config endpoint
(issue #40) - TDD discipline."""

from unittest.mock import patch

import pytest

from app.core.auth import get_current_user
from app.core.config import settings
from app.main import app

ADMIN_USER = {
    "user_id": "admin-user-1",
    "username": "admin",
    "email": "admin@example.com",
    "name": "Admin User",
    "token": {"realm_access": {"roles": ["admin"]}},
}

NON_ADMIN_USER = {
    "user_id": "regular-user-1",
    "username": "regular",
    "email": "regular@example.com",
    "name": "Regular User",
    "token": {"realm_access": {"roles": ["offline_access"]}},
}


def _override_user(user: dict):
    def _override():
        return user

    return _override


@pytest.mark.unit
def test_nav_config_endpoint_is_admin_only(client):
    app.dependency_overrides[get_current_user] = _override_user(NON_ADMIN_USER)

    response = client.get("/api/settings/nav-config")

    app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.unit
def test_nav_config_endpoint_reports_the_keycloak_users_console_url(client):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    with patch.object(settings, "keycloak_console_url", "https://keycloak.example.com"):
        response = client.get("/api/settings/nav-config")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["keycloak_users_console_url"] == (
        "https://keycloak.example.com/admin/master/console/#/eaistack/users"
    )


@pytest.mark.unit
def test_nav_config_endpoint_reports_null_when_console_url_unconfigured(client):
    app.dependency_overrides[get_current_user] = _override_user(ADMIN_USER)

    with patch.object(settings, "keycloak_console_url", None):
        response = client.get("/api/settings/nav-config")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["keycloak_users_console_url"] is None
