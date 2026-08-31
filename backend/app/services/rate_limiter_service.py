"""Rate limiting enforcement: resolve config, check/consume a bucket per identity.

Wraps app.ratelimit.token_bucket -- itself deterministic, pure logic with
no I/O -- with per-identity state storage and config resolution, the same
shape app.services.chat_guardrail_service wraps
app.guardrails.input_guardrail/output_guardrail with.

State is an in-process dict, not a shared store (Redis, etc.). This is a
deliberate v1 decision, not an oversight -- see docs/SECURITY.md's
rate-limiting section for the full rationale. Short version: every
deployment path this repo ships today (docker-compose, and the Helm
chart's `replicas: 1` in infra/helm/charts/backend/values.yaml, asserted by
infra/tests/test_helm_charts.py) runs the backend as a single process, so
there is exactly one dict to disagree with itself. Unlike the retention
CronJob (docs/SECURITY.md's "Enforcement: K8s CronJob" section), where
in-process state would cause a destructive double-execution across
replicas, an under-throttled limiter on a future multi-replica deployment
degrades gracefully (weaker protection, not data loss) -- tracked as
issue #38 for when that becomes a real deployment shape, not implemented
speculatively now.

A module-level lock guards the dict's read-modify-write: even a single
uvicorn worker interleaves concurrent requests on its event loop, so two
requests from the same identity arriving close together could otherwise
race on the same bucket entry.
"""

import threading
from datetime import datetime

from sqlalchemy.orm import Session

from app.ratelimit.token_bucket import TokenBucketState, check_and_consume
from app.services.rate_limit_config_service import RateLimitConfig, resolve_rate_limit_config

_buckets: dict[tuple[str, str], TokenBucketState] = {}
_buckets_lock = threading.Lock()


class RateLimitCheckResult:
    """Outcome of one rate-limit check for a single identity/route class.

    Mirrors app.ratelimit.token_bucket.TokenBucketResult's allowed/
    retry_after_seconds shape, but deliberately does not expose the
    underlying TokenBucketState -- callers (the two endpoints) only ever
    need to know whether to proceed or return 429, never the raw bucket
    internals.
    """

    def __init__(self, *, allowed: bool, retry_after_seconds: int | None):
        self.allowed = allowed
        self.retry_after_seconds = retry_after_seconds


def reset_rate_limit_state() -> None:
    """Clear all in-process bucket state.

    Test-only entry point (see tests/unit/test_rate_limiter_service.py's
    autouse fixture) -- production code never calls this, since the whole
    point of the in-process dict is that it persists for the life of the
    process.
    """
    with _buckets_lock:
        _buckets.clear()


def _check_and_consume_bucket(
    key: tuple[str, str], *, capacity: int, refill_per_minute: int, now: datetime
) -> RateLimitCheckResult:
    """Shared consume-and-store step for both chat and auth checks.

    refill_per_minute is converted to a per-second rate here, once, so
    app.ratelimit.token_bucket's math stays in per-second units regardless
    of how callers prefer to configure it (admins think in "requests per
    minute"; the algorithm just needs a steady rate).
    """
    refill_per_second = refill_per_minute / 60.0

    with _buckets_lock:
        current_state = _buckets.get(key)
        result = check_and_consume(
            current_state,
            capacity=capacity,
            refill_per_second=refill_per_second,
            now=now,
        )
        _buckets[key] = result.state

    return RateLimitCheckResult(
        allowed=result.allowed, retry_after_seconds=result.retry_after_seconds
    )


def check_chat_rate_limit(
    db: Session, *, user_id: str, now: datetime, config: RateLimitConfig | None = None
) -> RateLimitCheckResult:
    """Check and consume one token from the caller's chat bucket.

    Keyed by user_id from the validated JWT (see app.api.agents.chat),
    never request input -- the same identity source ThreadRepository uses
    for conversation ownership, so a client cannot spoof another user's
    budget or dodge their own by supplying a different identifier.

    config: the caller's already-resolved RateLimitConfig, if it has one.
    Omitted by callers (e.g. unit tests) that don't have one handy, in
    which case this function resolves its own.
    """
    if config is None:
        config = resolve_rate_limit_config(db)
    if not config.enabled:
        return RateLimitCheckResult(allowed=True, retry_after_seconds=None)

    return _check_and_consume_bucket(
        (user_id, "chat"),
        capacity=config.chat_capacity,
        refill_per_minute=config.chat_refill_per_minute,
        now=now,
    )


def check_auth_rate_limit(
    db: Session, *, client_ip: str, now: datetime, config: RateLimitConfig | None = None
) -> RateLimitCheckResult:
    """Check and consume one token from the caller's auth-endpoint bucket.

    Keyed by client IP (see app.api.auth.exchange_token) -- there is no
    authenticated identity yet at this endpoint, since it's the token
    exchange itself; IP is the only identity available before a JWT exists.

    config: same optional-already-resolved-config shape as
    check_chat_rate_limit.
    """
    if config is None:
        config = resolve_rate_limit_config(db)
    if not config.enabled:
        return RateLimitCheckResult(allowed=True, retry_after_seconds=None)

    return _check_and_consume_bucket(
        (client_ip, "auth"),
        capacity=config.auth_capacity,
        refill_per_minute=config.auth_refill_per_minute,
        now=now,
    )
