"""Pytest configuration and shared fixtures for doc-search."""

import os
from typing import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# See backend/tests/conftest.py for why TC_HOST is forced: testcontainers
# 3.7.1 misdetects the Docker host when reached over a Windows named pipe.
os.environ.setdefault("TC_HOST", "localhost")

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
