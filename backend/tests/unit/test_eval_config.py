"""Unit tests for the eval-run timeout setting (issue #84 slice B) - TDD.

eval_case_run_timeout_seconds is an admin knob rather than a constant
because the right value depends on hardware: a review loop on a CPU-only 8B
model takes minutes, on a GPU seconds.
"""

import pytest

from app.core.auth import get_current_user
from app.core.config import settings
from app.db.models import AuditLog, SystemSettings
from app.main import app
from app.services.eval_config_service import resolve_eval_config

ADMIN_USER = {
    "user_id": "admin-user-1",
    "username": "admin",
    "email": "admin@example.com",
    "name": "Admin User",
    "token": {"realm_access": {"roles": ["admin"]}},
}


@pytest.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    yield
    app.dependency_overrides.clear()


@pytest.mark.unit
def test_timeout_falls_back_to_the_env_default_without_a_settings_row(db_session):
    assert resolve_eval_config(db_session).case_run_timeout_seconds == (
        settings.eval_case_run_timeout_seconds
    )


@pytest.mark.parametrize("db_value, expected", [(None, 300), (10, 10), (900, 900)])
@pytest.mark.unit
def test_a_db_override_wins_over_the_env_default(db_session, monkeypatch, db_value, expected):
    monkeypatch.setattr(settings, "eval_case_run_timeout_seconds", 300)
    db_session.add(
        SystemSettings(id="default", eval_case_run_timeout_seconds=db_value, updated_by="admin-1")
    )
    db_session.commit()

    assert resolve_eval_config(db_session).case_run_timeout_seconds == expected


@pytest.mark.unit
def test_admin_can_set_the_timeout_via_update_settings(client, as_admin):
    response = client.put("/api/settings", json={"eval_case_run_timeout_seconds": 600})

    assert response.status_code == 200
    data = response.json()
    assert data["eval_case_run_timeout_seconds"] == 600
    assert data["eval_case_run_timeout_seconds_is_db_override"] is True


@pytest.mark.parametrize("value", [9, 3601])
@pytest.mark.unit
def test_a_timeout_outside_ten_seconds_to_an_hour_is_rejected(client, as_admin, value):
    response = client.put("/api/settings", json={"eval_case_run_timeout_seconds": value})

    assert response.status_code == 422


@pytest.mark.unit
def test_changing_the_timeout_is_audit_logged(client, db_session, as_admin):
    client.put("/api/settings", json={"eval_case_run_timeout_seconds": 600})

    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.field_name == "eval_case_run_timeout_seconds")
        .one()
    )
    assert entry.action == "eval_config.config_update"
    assert (entry.old_value, entry.new_value) == (None, "600")
