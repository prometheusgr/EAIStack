"""Tests for the unauthenticated health/readiness endpoint.

Kubernetes' kubelet only treats HTTP 200-399 as a passing readiness/liveness
probe (see infra/k3s/doc-search-deployment.yaml). BearerTokenMiddleware is
inserted at position 0 of the middleware stack and rejects any request
without a valid Keycloak bearer token with 401 — including probes, which
never carry one. Without a genuinely unauthenticated health path, the
doc-search pod can never become Ready in a real cluster even though the
process itself is healthy.

These are unit tests: no real Postgres or Keycloak is needed, since the
health endpoint must respond without touching either.
"""

import pytest
from starlette.testclient import TestClient

from app.server import build_app


@pytest.mark.unit
def test_health_endpoint_returns_200_without_bearer_token():
    """The health path must be reachable by a probe that sends no
    Authorization header at all.
    """
    client = TestClient(build_app())

    response = client.get("/healthz")

    assert response.status_code == 200


@pytest.mark.unit
def test_mcp_endpoint_still_rejects_requests_without_bearer_token():
    """The health exclusion must not accidentally open up the real MCP
    endpoint — every other route still requires a valid bearer token.
    """
    client = TestClient(build_app())

    response = client.post("/mcp", json={})

    assert response.status_code == 401
