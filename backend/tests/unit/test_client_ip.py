"""Tests for resolve_client_ip - the trusted-proxy-aware client IP resolver.

Pure logic (a dict of headers + a transport-reported peer IP in, one string
out), no request/ASGI machinery needed, so these are ordinary unit tests
per AGENTS.md's TDD standard.
"""

import pytest

from app.core.client_ip import resolve_client_ip


@pytest.mark.unit
def test_no_trusted_proxies_uses_transport_peer_ip():
    """Default posture (trusted_proxy_count=0): X-Forwarded-For is never
    consulted, even if present - a direct, un-proxied deployment must not
    let a client spoof their own rate-limit identity via a request header.
    """
    ip = resolve_client_ip(
        peer_ip="203.0.113.7",
        forwarded_for_header="198.51.100.1",
        trusted_proxy_count=0,
    )

    assert ip == "203.0.113.7"


@pytest.mark.unit
def test_no_trusted_proxies_and_no_peer_ip_falls_back_to_unknown():
    """A missing transport peer IP (possible under some ASGI test
    transports, or an unusual deployment) with no trusted proxy configured
    falls back to a single shared bucket rather than crashing.
    """
    ip = resolve_client_ip(peer_ip=None, forwarded_for_header=None, trusted_proxy_count=0)

    assert ip == "unknown"


@pytest.mark.unit
def test_one_trusted_proxy_uses_rightmost_forwarded_for_entry():
    """With exactly one trusted hop (e.g. a single K8s ingress in front of
    the backend), the real client IP is the rightmost entry in
    X-Forwarded-For - the one the trusted proxy itself appended - never the
    leftmost, which is client-supplied and trivially spoofable.
    """
    ip = resolve_client_ip(
        peer_ip="10.0.0.5",  # the ingress's own pod IP
        forwarded_for_header="203.0.113.7",
        trusted_proxy_count=1,
    )

    assert ip == "203.0.113.7"


@pytest.mark.unit
def test_multiple_trusted_proxies_walks_back_that_many_hops():
    """With N trusted proxies chained, the real client is N entries from the
    right of X-Forwarded-For - anything appended further left is untrusted,
    attacker-controlled input and must be ignored.
    """
    # left-to-right: [client-supplied (untrusted), proxy-1-appended, proxy-2-appended]
    header = "198.51.100.1, 203.0.113.7, 192.0.2.55"

    ip = resolve_client_ip(peer_ip="10.0.0.9", forwarded_for_header=header, trusted_proxy_count=2)

    assert ip == "203.0.113.7"


@pytest.mark.unit
def test_trusted_proxy_configured_but_header_missing_falls_back_to_peer_ip():
    """A trusted-proxy count > 0 with no X-Forwarded-For header present
    (e.g. a health check hitting the backend directly, bypassing the
    ingress) falls back to the transport peer IP rather than crashing or
    treating the request as anonymous.
    """
    ip = resolve_client_ip(peer_ip="10.0.0.5", forwarded_for_header=None, trusted_proxy_count=1)

    assert ip == "10.0.0.5"


@pytest.mark.unit
def test_trusted_proxy_configured_but_header_has_fewer_hops_than_expected():
    """If X-Forwarded-For has fewer entries than trusted_proxy_count implies
    (a misconfiguration, or a proxy that didn't append its hop), fall back
    to the transport peer IP rather than indexing past the list or trusting
    an attacker-controlled leftmost entry.
    """
    ip = resolve_client_ip(
        peer_ip="10.0.0.5",
        forwarded_for_header="203.0.113.7",  # only 1 entry, but 2 hops expected
        trusted_proxy_count=2,
    )

    assert ip == "10.0.0.5"


@pytest.mark.unit
def test_forwarded_for_entries_are_trimmed_of_whitespace():
    """X-Forwarded-For is comma-separated with optional spaces per RFC 7239
    convention (proxies vary in whether they add a space after the comma).
    """
    ip = resolve_client_ip(
        peer_ip="10.0.0.5",
        forwarded_for_header="198.51.100.1,   203.0.113.7  ,192.0.2.55",
        trusted_proxy_count=2,
    )

    assert ip == "203.0.113.7"
