"""Pytest configuration and shared fixtures."""

import os
from typing import Generator

# Patch httpx.Client to work with Starlette TestClient
# This is a workaround for Starlette/httpx version incompatibility
import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# testcontainers 3.7.1 misdetects the Docker host as the literal string
# "localnpipe" when the Docker daemon is reached over a Windows named pipe
# (e.g. Docker Desktop/Rancher Desktop), because its scheme-sniffing treats
# "http+docker" as an http(s) URL instead of a pipe URL. TC_HOST is
# testcontainers' documented override for this exact detection step.
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


@pytest.fixture(scope="session")
def postgres_container() -> Generator:
    """Start a Postgres container for integration tests."""
    if not HAS_TESTCONTAINERS:
        yield None
        return

    container = PostgresContainer("pgvector/pgvector:pg16")
    container.start()
    yield container
    container.stop()


@pytest.fixture
def test_db_url(request, tmp_path) -> str:
    """
    Provide a database URL.

    - Unit tests: SQLite file-based (workaround for TestClient threading)
    - Integration tests: real Postgres (from container)
    """
    if "integration" in request.keywords:
        if not HAS_TESTCONTAINERS:
            pytest.skip("testcontainers not installed")

        container = PostgresContainer("pgvector/pgvector:pg16")
        container.start()
        url = container.get_connection_url()
        yield url
        container.stop()
    else:
        # Use file-based SQLite for unit tests to ensure same DB across sessions
        db_file = tmp_path / "test.db"
        yield f"sqlite:///{db_file}?check_same_thread=False"


@pytest.fixture
def db_session(test_db_url):
    """Provide a SQLAlchemy session for testing."""
    from app.db.models import Base

    # For SQLite, we need to handle Vector type which is PostgreSQL-specific
    # Vector columns will be stored as BLOB in SQLite but SQLAlchemy will handle conversion
    connect_args = {"check_same_thread": False} if "sqlite" in test_db_url else {}
    engine = create_engine(test_db_url, echo=False, connect_args=connect_args)

    # Create tables, handling PostgreSQL-specific types
    if "postgres" in test_db_url:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()

    Base.metadata.drop_all(engine)  # Clean up from previous tests
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
def client(db_session, test_db_url):
    """Provide a test client for the app with DB dependency.

    NOTE: Auth is NOT overridden by default. Tests that require authentication
    should manually override get_current_user in their test functions.
    Tests that require auth should verify they properly set up the override.
    """
    from starlette.testclient import TestClient

    from app.db.database import get_db
    from app.main import app

    def get_db_override():
        return db_session

    app.dependency_overrides[get_db] = get_db_override

    client = TestClient(app)
    yield client

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
