"""Pytest configuration and shared fixtures."""

import json
import os
from datetime import datetime, timezone
from typing import Generator

# Patch httpx.Client to work with Starlette TestClient
# This is a workaround for Starlette/httpx version incompatibility
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import to_base64url_uint
from sqlalchemy import create_engine, event, text
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

    if "sqlite" in test_db_url:
        _enable_sqlite_savepoints(engine)

    Base.metadata.drop_all(engine)  # Clean up from previous tests
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


def _enable_sqlite_savepoints(engine) -> None:
    """Make Session.begin_nested() (SAVEPOINT) work correctly against SQLite.

    pysqlite's default driver-level transaction handling issues its own
    implicit BEGIN on the first DML statement and only understands the
    outermost transaction, so a nested SAVEPOINT silently behaves like a
    full commit instead of a scoped rollback point -- exactly the failure
    mode that broke GuardrailPatternRepository.ensure_built_ins_seeded's
    "does not commit; the caller owns the transaction" contract under this
    fixture (see test_guardrail_pattern_repository.py). This is SQLAlchemy's
    own documented workaround: disable pysqlite's implicit transaction
    handling and issue BEGIN explicitly, so SAVEPOINT/RELEASE work as real
    nested transactions. Production runs against Postgres, where this is
    unnecessary -- begin_nested() already works correctly there.
    """

    @event.listens_for(engine, "connect")
    def _do_connect(dbapi_connection, connection_record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _do_begin(conn):
        conn.exec_driver_sql("BEGIN")


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


FAKE_KEYCLOAK_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def fake_keycloak_jwks_server():
    """Serve FAKE_KEYCLOAK_PRIVATE_KEY's public JWKS over real HTTP, at the
    same path Keycloak serves its realm JWKS
    (/realms/{realm}/protocol/openid-connect/certs).

    Used by tests/integration/test_mcp_client.py: doc-search runs as a real
    subprocess and needs a real, network-reachable JWKS URL to verify tokens
    against — it cannot share an in-process mock with the backend's test
    process. Session-scoped since the keypair and server are cheap to reuse
    across every test that needs a live doc-search subprocess.

    Yields the base URL (e.g. http://127.0.0.1:PORT) to set as
    doc-search's KEYCLOAK_URL.
    """
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    public_numbers = FAKE_KEYCLOAK_PRIVATE_KEY.public_key().public_numbers()
    jwks_body = json.dumps(
        {
            "keys": [
                {
                    "kid": "backend-integration-test-key",
                    "kty": "RSA",
                    "use": "sig",
                    "n": to_base64url_uint(public_numbers.n).decode("utf-8"),
                    "e": to_base64url_uint(public_numbers.e).decode("utf-8"),
                }
            ]
        }
    ).encode("utf-8")

    class _JWKSHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.endswith("/protocol/openid-connect/certs"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(jwks_body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Silence per-request logging; tests already report failures.

    server = HTTPServer(("127.0.0.1", 0), _JWKSHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def now_fixed():
    """Provide a fixed UTC datetime for time-dependent function tests.

    Use this fixture in tests of functions that accept `now: datetime` as a parameter.
    Ensures all time-dependent tests use the same reference moment.
    """
    return datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def now_fixed_naive():
    """Provide a fixed naive datetime (no timezone) for time-dependent function tests.

    Use this fixture only when testing code that expects naive datetimes.
    Prefer now_fixed (UTC) for new code.
    """
    return datetime(2026, 8, 21, 12, 0, 0)
