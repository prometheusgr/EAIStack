"""Pytest configuration and shared fixtures."""

from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

try:
    from testcontainers.postgres import PostgresContainer

    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False


@pytest.fixture(scope="session")
def postgres_container() -> Generator:
    """Start a Postgres container for integration tests."""
    if not HAS_TESTCONTAINERS:
        yield None
        return

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
        if not HAS_TESTCONTAINERS:
            pytest.skip("testcontainers not installed")

        container = PostgresContainer("pgvector/pgvector:0.5.1")
        container.start()
        url = container.get_connection_url()
        yield url
        container.stop()
    else:
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


@pytest.fixture
def client(db_session):
    """Provide a test client for the app with DB dependency."""
    from starlette.testclient import TestClient
    from app.main import app
    from app.api.apikeys import get_db

    def get_db_override():
        return db_session

    app.dependency_overrides[get_db] = get_db_override

    # TestClient now takes the app as a positional argument, not keyword
    client = TestClient(app)
    yield client

    # Clean up dependency override
    app.dependency_overrides.clear()


@pytest.fixture
def mock_keycloak_token():
    """Provide a mock Keycloak JWT token structure.

    This fixture returns a valid JWT payload that would be issued by Keycloak
    after a successful login. It's used to test token validation without
    requiring a live Keycloak instance.
    """
    return {
        "sub": "f1943c60-cb5a-4887-9331-73ba51b6bd89",
        "preferred_username": "testuser",
        "email": "testuser@eaistack.local",
        "name": "Test User",
        "email_verified": True,
        "iss": "http://localhost:8080/realms/eaistack",
        "aud": "eaistack-web",
        "iat": 1629312000,
        "exp": 1629398400,
    }
