"""Token-bucket rate limiting: pure, deterministic math.

Chosen over a fixed window (which allows up to 2x the intended rate at
window boundaries -- a burst at :59 and another at :00 of the next window)
and a sliding-window log (which needs an unbounded-until-pruned list of
request timestamps per identity). A token bucket needs only two numbers per
identity (tokens, last_refill_at), naturally expresses "N requests per
window with some burst allowance," and is trivial to move into a shared
store like Redis later (see docs/SECURITY.md's rate-limiting section and
issue #38) without changing this module at all -- only where its state is
persisted between requests changes.

Deterministic, pure logic -- no clock read, no I/O, no DB access -- so it
is fully unit testable per AGENTS.md's TDD standard and
docs/TIME_INJECTION.md's time-injection pattern: `now` is always a required
parameter, never read from the wall clock internally. Identity resolution,
config resolution, and state persistence between calls all live one layer
up, in app.services.rate_limiter_service -- this module never touches a
database or a dict of its own.
"""

import math
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TokenBucketState:
    """A bucket's persisted state between requests for one identity.

    tokens is a float (not int) so refill amounts that don't divide evenly
    into whole tokens (e.g. a fractional refill_per_second, or a partial
    second elapsed) accumulate precisely across many calls rather than
    losing fractions to repeated rounding.
    """

    tokens: float
    last_refill_at: datetime


@dataclass(frozen=True)
class TokenBucketResult:
    """Outcome of one check_and_consume call.

    state is the new state to persist regardless of outcome -- even a
    denied request still needs its caller to save the refilled (but not
    further consumed) token count and the current now as last_refill_at,
    so the next call's elapsed-time math stays correct.

    retry_after_seconds is set only when allowed is False, and is what the
    caller (see app.api.agents.chat / app.api.auth.exchange_token) puts
    directly in the 429 response's Retry-After header.
    """

    allowed: bool
    state: TokenBucketState
    retry_after_seconds: int | None


def check_and_consume(
    state: TokenBucketState | None,
    *,
    capacity: int,
    refill_per_second: float,
    now: datetime,
) -> TokenBucketResult:
    """Refill a bucket for elapsed time, then attempt to consume one token.

    state=None means "first request ever seen from this identity" -- the
    bucket starts full (capacity tokens), the same as if it had been idle
    forever before now. This is the initial-state case every caller hits
    the first time a new user_id/IP shows up, and needs no special casing
    beyond treating it as "0 tokens elapsed-refilled from empty, capped at
    capacity."

    Refill is `min(capacity, tokens + elapsed_seconds * refill_per_second)`,
    computed before the consume check -- a bucket that has been idle long
    enough to fully refill is allowed even if its last stored value was 0.

    A denied request (fewer than 1 token available after refill) does not
    consume anything further; only an allowed request subtracts one token.

    Raises ValueError for a non-positive capacity or refill_per_second: both
    are caller contract violations (a zero/negative capacity bucket denies
    every request forever with no way to recover; a zero/negative refill
    rate makes the retry_after_seconds division undefined or negative).
    Config resolution is expected to never produce such a value in practice
    (see app.core.config's Field(ge=1) bound on the env-sourced settings and
    UpdateSettingsRequest's identical bound on the DB-override path) -- this
    is a defense-in-depth assertion at the boundary of this module's own
    contract, not a scenario normal operation should ever reach.
    """
    if capacity < 1:
        raise ValueError(f"capacity must be >= 1, got {capacity}")
    if refill_per_second <= 0:
        raise ValueError(f"refill_per_second must be > 0, got {refill_per_second}")

    if state is None:
        tokens_before_consume = float(capacity)
        elapsed_seconds = 0.0
    else:
        elapsed_seconds = max(0.0, (now - state.last_refill_at).total_seconds())
        tokens_before_consume = min(capacity, state.tokens + elapsed_seconds * refill_per_second)

    if tokens_before_consume < 1:
        missing_tokens = 1 - tokens_before_consume
        retry_after_seconds = math.ceil(missing_tokens / refill_per_second)
        return TokenBucketResult(
            allowed=False,
            state=TokenBucketState(tokens=tokens_before_consume, last_refill_at=now),
            retry_after_seconds=retry_after_seconds,
        )

    return TokenBucketResult(
        allowed=True,
        state=TokenBucketState(tokens=tokens_before_consume - 1, last_refill_at=now),
        retry_after_seconds=None,
    )
