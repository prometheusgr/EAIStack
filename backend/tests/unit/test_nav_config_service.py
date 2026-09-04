"""Unit tests for the admin nav's static config service - TDD discipline.

Covers issue #40: the "User Management" nav entry's Keycloak admin console
deep link must be built server-side (so the realm name and console URL
shape are resolved in one place) and must never fall back to an
internal-only address that would silently produce a broken link.
"""

from unittest.mock import patch

import pytest

from app.core.config import settings
from app.services.nav_config_service import resolve_nav_config


@pytest.mark.unit
def test_resolve_nav_config_keycloak_users_console_url_is_none_when_unconfigured():
    """No browser-facing console URL configured -- the frontend must omit
    the nav link rather than render one pointed at settings.keycloak_url,
    which is typically an internal-only address (docker-compose's
    "keycloak:8080", or a .svc.cluster.local hostname under Helm)."""
    with patch.object(settings, "keycloak_console_url", None):
        config = resolve_nav_config()

    assert config.keycloak_users_console_url is None


@pytest.mark.unit
def test_resolve_nav_config_keycloak_users_console_url_is_none_for_empty_string():
    """An explicit empty-string override (e.g. a misconfigured env var) must
    behave the same as unset, not build a malformed URL from an empty
    root."""
    with patch.object(settings, "keycloak_console_url", ""):
        config = resolve_nav_config()

    assert config.keycloak_users_console_url is None


@pytest.mark.unit
def test_resolve_nav_config_builds_the_full_admin_console_users_url():
    with (
        patch.object(settings, "keycloak_console_url", "https://keycloak.example.com"),
        patch.object(settings, "keycloak_realm", "eaistack"),
    ):
        config = resolve_nav_config()

    assert (
        config.keycloak_users_console_url
        == "https://keycloak.example.com/admin/master/console/#/eaistack/users"
    )


@pytest.mark.unit
def test_resolve_nav_config_strips_a_trailing_slash_from_the_console_root():
    with patch.object(settings, "keycloak_console_url", "https://keycloak.example.com/"):
        config = resolve_nav_config()

    assert config.keycloak_users_console_url == (
        "https://keycloak.example.com/admin/master/console/#/eaistack/users"
    )


@pytest.mark.unit
def test_resolve_nav_config_uses_the_configured_realm_name():
    """A fork that renames its realm must get a link pointed at the new
    realm, not a hardcoded "eaistack" -- this is what moving the URL
    construction server-side (rather than hardcoding it in the frontend)
    is meant to guarantee."""
    with (
        patch.object(settings, "keycloak_console_url", "https://keycloak.example.com"),
        patch.object(settings, "keycloak_realm", "mycompany"),
    ):
        config = resolve_nav_config()

    assert config.keycloak_users_console_url == (
        "https://keycloak.example.com/admin/master/console/#/mycompany/users"
    )
