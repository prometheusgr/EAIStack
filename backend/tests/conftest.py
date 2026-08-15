"""Pytest configuration and shared fixtures."""

import os
from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

# Use in-memory SQLite for speed in unit tests, real Postgres for integration tests


@pytest.fixture(scope="session")
def postgres_container() -> Generator:
    """Start a Postgres container for integration tests."""
    # Only start if running integration tests
    container = PostgresContainer("pgvector/pgvector:0.5.1")
    container.start()
    yield container
    container.stop()


@pytest.fixture
def test_db_url(request) -> str:
    """
    Provide a database URL.

    - Unit tests: SQLite in-memory (fast)
    - Integration tests: real Postgres (from container)
    """
    if "integration" in request.keywords:
        # Integration tests use real Postgres
        container = PostgresContainer("pgvector/pgvector:0.5.1")
        container.start()
        url = container.get_connection_url()
        yield url
        container.stop()
    else:
        # Unit tests use SQLite in-memory
        yield "sqlite:///:memory:"


@pytest.fixture
def db_session(test_db_url):
    """Provide a SQLAlchemy session for testing."""
    from app.db.models import Base

    engine = create_engine(test_db_url, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def mock_llm():
    """Provide a fake LLM client for unit tests."""
    from app.core.llm_client import FakeChatModel

    return FakeChatModel()
