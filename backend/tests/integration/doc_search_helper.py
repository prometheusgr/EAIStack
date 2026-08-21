"""Shared helper for integration tests that need a real, running doc-search
MCP server: tests/integration/test_mcp_client.py and
tests/unit/test_chat_agent.py's tool-call integration tests both need this.

doc-search runs as a genuine subprocess in its own venv (not imported into
the backend's process) — this mirrors the production topology (separate
pods, separate dependency sets) rather than blurring the boundary Phase 3
establishes between the two services.
"""

import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import jwt
import pytest

DOC_SEARCH_DIR = Path(__file__).resolve().parents[3] / "mcp-servers" / "doc-search"
DOC_SEARCH_PYTHON = DOC_SEARCH_DIR / (
    "venv/Scripts/python.exe" if sys.platform == "win32" else "venv/bin/python"
)


def make_signed_token(user_id: str, private_key) -> str:
    """Sign a token with the given test keypair (e.g.
    conftest.FAKE_KEYCLOAK_PRIVATE_KEY), matching whatever JWKS the target
    doc-search subprocess was pointed at via fake_keycloak_jwks_server.
    """
    return jwt.encode(
        {
            "sub": user_id,
            "aud": "eaistack-web",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "backend-integration-test-key"},
    )


@contextmanager
def running_doc_search_subprocess(database_url: str, keycloak_jwks_url: str, port: int):
    """Start doc-search as a real subprocess pointed at the given Postgres
    and a JWKS URL the test controls (see conftest.fake_keycloak_jwks_server).
    """
    if not DOC_SEARCH_PYTHON.exists():
        pytest.skip(
            f"doc-search venv not found at {DOC_SEARCH_PYTHON}; "
            "run `pip install -e '.[dev]'` in mcp-servers/doc-search first"
        )

    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "KEYCLOAK_URL": keycloak_jwks_url,
        "KEYCLOAK_REALM": "eaistack",
    }
    process = subprocess.Popen(
        [
            str(DOC_SEARCH_PYTHON),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(DOC_SEARCH_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 15
        mcp_url = f"http://127.0.0.1:{port}/mcp"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read().decode(errors="replace") if process.stdout else ""
                raise RuntimeError(f"doc-search subprocess exited early:\n{output}")
            try:
                httpx.get(f"http://127.0.0.1:{port}/", timeout=0.5)
                break
            except httpx.TransportError:
                time.sleep(0.2)
        else:
            output = process.stdout.read().decode(errors="replace") if process.stdout else ""
            raise RuntimeError(f"doc-search subprocess never became reachable:\n{output}")
        yield mcp_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
