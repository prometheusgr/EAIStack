"""Pytest configuration and shared fixtures for doc-search."""

import os
from typing import Generator

# Patch httpx.Client to work with Starlette TestClient
# This is a workaround for a Starlette/httpx version incompatibility (see
# backend/tests/conftest.py for the original fix, needed here too since
# test_health.py uses starlette.testclient.TestClient directly): Starlette
# versions before 0.37 pass app= to httpx.Client.__init__, but httpx>=0.28
# dropped that parameter in favor of transport=. Neither package declares
# an upper/lower bound against the other, so pip alone won't catch this —
# whatever Starlette happens to be installed (here, pinned indirectly by
# fastapi's <0.33.0 ceiling, since both projects share one dev venv) is
# what determines whether TestClient still works with a modern httpx.
import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# See backend/tests/conftest.py for why TC_HOST is forced: testcontainers
# 3.7.1 misdetects the Docker host when reached over a Windows named pipe.
os.environ.setdefault("TC_HOST", "localhost")

_original_httpx_init = httpx.Client.__init__


def _patched_httpx_init(self, *args, app=None, **kwargs):
    """Patch to ignore app parameter passed by Starlette TestClient."""
    return _original_httpx_init(self, *args, **kwargs)


httpx.Client.__init__ = _patched_httpx_init

try:
    from testcontainers.postgres import PostgresContainer

    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False


@pytest.fixture
def test_db_url(request) -> Generator[str, None, None]:
    """Provide a real Postgres URL for integration tests.

    Unlike backend/tests/conftest.py, doc-search has no unit-test SQLite
    fallback: every test here that touches the database needs pgvector's
    cosine distance operator, so all DB-touching tests are integration-marked
    and always get real Postgres.
    """
    if not HAS_TESTCONTAINERS:
        pytest.skip("testcontainers not installed")

    container = PostgresContainer("pgvector/pgvector:pg16")
    container.start()
    url = container.get_connection_url()
    yield url
    container.stop()


@pytest.fixture
def db_session(test_db_url):
    """Provide a SQLAlchemy session against a real, freshly-migrated Postgres."""
    from app.models import Base

    engine = create_engine(test_db_url, echo=False)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()
