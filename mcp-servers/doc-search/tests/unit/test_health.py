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
from mcp.server.transport_security import TransportSecurityMiddleware
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
def test_mcp_server_keeps_dns_rebinding_protection_enabled():
    """DNS-rebinding Host-header protection must stay enabled: docker-compose
    publishes this service's port to the host ("8100:8100", for direct
    curl/debugging), which also makes http://localhost:8100 reachable from
    any browser tab -- exactly the threat model the protection defends
    against. Regression test for a prior bug fix that disabled the check
    entirely (enable_dns_rebinding_protection=False) instead of allowlisting
    the real Host values this server is legitimately reached under.
    """
    mcp = _build_mcp()

    assert mcp.settings.transport_security is not None
    assert mcp.settings.transport_security.enable_dns_rebinding_protection is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "host_header",
    [
        "doc-search:8100",  # docker-compose service DNS name
        "eaistack-doc-search",  # K8s Service short name (in-namespace)
        "eaistack-doc-search:8100",  # K8s Service short name with port
        "127.0.0.1:8100",  # published host port, local/dev direct access
        "localhost:8100",  # published host port, local/dev direct access
    ],
)
def test_mcp_transport_security_allows_known_host_headers(host_header):
    """Every Host value this server is legitimately reached under -- the
    docker-compose service name, the K8s Service name, and the published
    host port used for local debugging -- must pass Host-header validation.
    Regression test for a bug where every real cross-network request (Host:
    doc-search:8100) was rejected with 421 "Invalid Host header" from
    inside the Streamable HTTP transport, after passing
    BearerTokenMiddleware's genuine bearer-token check -- i.e. a correctly
    authenticated request from the backend was still rejected, because the
    transport's own Host-header allowlist never recognized a
    docker-compose/K8s service DNS name as valid.

    Asserted directly against TransportSecurityMiddleware rather than by
    sending a request: TransportSecurityMiddleware.validate_request only
    runs inside the Streamable HTTP transport's own request handling
    (reached after BearerTokenMiddleware), which a token-less TestClient
    request can never get far enough to exercise.
    """
    mcp = _build_mcp()
    middleware = TransportSecurityMiddleware(mcp.settings.transport_security)

    assert middleware._validate_host(host_header) is True


@pytest.mark.unit
def test_mcp_transport_security_rejects_unknown_host_header():
    """An arbitrary, attacker-controlled Host header (the DNS-rebinding
    scenario the protection exists to catch: a browser tab tricked into
    sending a request that resolves to this server) must still be rejected,
    even though the known docker-compose/K8s/localhost hosts are now
    allowlisted. Allowlisting real hosts must not have degraded into
    accepting everything.
    """
    mcp = _build_mcp()
    middleware = TransportSecurityMiddleware(mcp.settings.transport_security)

    assert middleware._validate_host("evil.example.com") is False
