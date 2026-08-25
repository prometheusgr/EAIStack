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

from app.server import _build_mcp, build_app


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


@pytest.mark.unit
def test_mcp_server_disables_dns_rebinding_host_header_protection():
    """This server is only ever reached by the backend's server-side HTTP
    client -- by its docker-compose service name ("doc-search") or K8s
    Service DNS name, never by a browser -- so the MCP SDK's default
    DNS-rebinding Host-header allowlist (127.0.0.1/localhost only, see
    mcp.server.fastmcp.server.Settings.__init__) must be disabled here.
    Regression test for a bug where every real cross-network request
    (Host: doc-search:8100) was rejected with 421 "Invalid Host header"
    from inside the Streamable HTTP transport, after passing
    BearerTokenMiddleware's genuine bearer-token check -- i.e. a correctly
    authenticated request from the backend was still rejected, because the
    transport's own Host-header allowlist never recognized a
    docker-compose/K8s service DNS name as valid.

    Asserted directly against the built FastMCP instance's settings rather
    than by sending a request: TransportSecurityMiddleware.validate_request
    only runs inside the Streamable HTTP transport's own request handling
    (reached after BearerTokenMiddleware), which a token-less TestClient
    request can never get far enough to exercise.
    """
    mcp = _build_mcp()

    assert mcp.settings.transport_security is not None
    assert mcp.settings.transport_security.enable_dns_rebinding_protection is False
