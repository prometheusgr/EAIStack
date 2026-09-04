"""Static, rarely-changing values the admin nav needs at login.

Issue #40: the "User Management" nav entry needs the full Keycloak admin
console URL as soon as an admin logs in, not only after they open the
Dashboard tab. Deliberately kept separate from
app.services.dashboard_service.resolve_dashboard_status, which performs
non-trivial work on every call (a 24h audit-log aggregation query, live
rate-limit bucket introspection) to report *live operational status* --
piggybacking a static config value onto that endpoint would mean every
consumer of the nav link pays for that aggregation too, once per login,
whether or not the admin ever opens Dashboard.
"""

from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class NavConfig:
    keycloak_users_console_url: str | None


def _build_keycloak_users_console_url() -> str | None:
    """Full URL to this realm's user list in Keycloak's admin console.

    None if no browser-facing console root is configured for this
    deployment (see Settings.keycloak_console_url's docstring) -- the
    frontend omits the nav link rather than rendering one pointed at an
    internal-only address it can never reach. Built here, not in the
    frontend, so the realm name and the admin console's URL shape (a
    Keycloak-version-specific detail) are resolved in exactly one place
    (this repo's own settings.keycloak_realm), rather than duplicated as a
    hardcoded literal in TypeScript that could drift from the actual
    configured realm.
    """
    if not settings.keycloak_console_url:
        return None
    root = settings.keycloak_console_url.rstrip("/")
    return f"{root}/admin/master/console/#/{settings.keycloak_realm}/users"


def resolve_nav_config() -> NavConfig:
    """Assemble the admin nav's static config snapshot."""
    return NavConfig(
        keycloak_users_console_url=_build_keycloak_users_console_url(),
    )
