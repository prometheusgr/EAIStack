"""Unit tests for app.main's lifespan hook - TDD discipline.

Verifies the startup wiring itself, not just its pieces in isolation:
resolve_tracing_config is called against a real (if short-lived) DB session
sourced from app.db.database.SessionLocal, and its result is passed into
configure_tracing before the app starts serving.

Uses `with TestClient(app) as client:` deliberately, not the bare
`TestClient(app)` this repo's `client` fixture builds - confirmed by hand
(see this branch's investigation) that Starlette 0.32's TestClient only
runs ASGI lifespan startup/shutdown when used as a context manager. A bare
TestClient(app) - what every other test file's `client` fixture uses - never
triggers this hook at all, which is exactly why a dedicated test is needed
here rather than relying on the existing suite to cover it.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.db.models import Base
from app.main import app


@pytest.fixture
def lifespan_db_sessionmaker(tmp_path):
    """A real, throwaway SQLite sessionmaker for the lifespan hook to read
    from - separate from the `db_session`/`client` fixtures in conftest.py,
    since those wire into `get_db` (a FastAPI dependency override), not
    app.main.SessionLocal (a module-level object the lifespan hook uses
    directly, since it runs before any request - and therefore any
    dependency injection - occurs).
    """
    db_file = tmp_path / "lifespan_test.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


@pytest.mark.unit
def test_lifespan_resolves_tracing_config_and_passes_it_to_configure_tracing(
    lifespan_db_sessionmaker,
):
    """The lifespan hook must open a session from SessionLocal, resolve
    tracing config from it, and forward the resolved `enabled` value into
    configure_tracing - proving the DB override actually reaches the
    tracer setup, not just the settings API response.
    """
    with (
        patch("app.main.SessionLocal", lifespan_db_sessionmaker),
        patch("app.main.configure_tracing") as mock_configure_tracing,
    ):
        with TestClient(app):
            pass

    mock_configure_tracing.assert_called_once()
    _, kwargs = mock_configure_tracing.call_args
    # No SystemSettings row exists in this fresh DB, so this must resolve to
    # the env default (False in every test process, since TRACING_ENABLED
    # is never set for the test suite) - not crash, and not silently skip
    # the call.
    assert kwargs["enabled"] is False
