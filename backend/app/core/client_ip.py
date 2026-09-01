"""Trusted-proxy-aware client IP resolution for per-IP rate limiting.

Pure logic, no Request/ASGI dependency - app.api.auth.exchange_token extracts
the two raw inputs (the transport's peer IP, the X-Forwarded-For header
value) and passes them here, the same separation
app.ratelimit.token_bucket's module docstring describes for keeping
algorithmic logic testable without framework machinery.

Trust model: X-Forwarded-For is attacker-controlled input on any endpoint
reachable with no authentication (like POST /api/auth/token) unless the
deployment topology guarantees every hop between the caller and this
process is a proxy this deployment controls. Blindly trusting the header
would let any caller set `X-Forwarded-For: <anything>` and pick their own
rate-limit bucket, defeating the limiter entirely. So the header is
consulted only when settings.rate_limit_trusted_proxy_count is explicitly
set above its default of 0 (see app.core.config) - the same "off unless a
deployment operator turns it on" posture as ca_bundle_path and
tracing_otlp_endpoint, since only the operator knows how many proxy hops
actually sit in front of this process.

When trusted_proxy_count is N, the real client is the Nth-from-the-right
entry in X-Forwarded-For: a proxy appends the address it received the
request from to the right of whatever was already there, so each trusted
hop's own append can be peeled off from the right, leaving anything further
left (attacker-controlled, prepended before the first trusted proxy ever
saw the request) untrusted and ignored.
"""


def resolve_client_ip(
    *,
    peer_ip: str | None,
    forwarded_for_header: str | None,
    trusted_proxy_count: int,
) -> str:
    """Resolve the client IP to key a per-IP rate-limit bucket on.

    peer_ip: the transport-reported peer address (e.g. Starlette's
    `Request.client.host`), or None if the ASGI transport doesn't report
    one (some test transports; see docs/SECURITY.md's rate-limiting
    section).

    forwarded_for_header: the raw `X-Forwarded-For` header value, or None
    if absent.

    trusted_proxy_count: how many proxy hops between the real client and
    this process are trusted to have appended their own observed peer
    address to X-Forwarded-For. 0 (the default) means "don't trust this
    header at all" - use peer_ip directly.

    Falls back to peer_ip (then "unknown") whenever the header is missing,
    or has fewer entries than trusted_proxy_count implies (a
    misconfiguration, or a request that reached this process by some path
    other than the expected proxy chain) - never partially-trusts a header
    that doesn't match the configured topology.
    """
    if trusted_proxy_count > 0 and forwarded_for_header:
        hops = [hop.strip() for hop in forwarded_for_header.split(",")]
        if len(hops) >= trusted_proxy_count:
            return hops[-trusted_proxy_count]

    return peer_ip if peer_ip else "unknown"
