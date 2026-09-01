"""Tests for the token-bucket rate-limiting algorithm.

Pure logic, no DB/IO, no reliance on the wall clock -- these are exactly the
deterministic, time-injected checks AGENTS.md's TDD standard and
docs/TIME_INJECTION.md expect thorough coverage for.
"""

from datetime import timedelta

import pytest

from app.ratelimit.token_bucket import TokenBucketState, check_and_consume


@pytest.mark.unit
def test_first_request_is_allowed_and_consumes_one_token(now_fixed):
    """A brand-new identity (state=None) starts with a full bucket."""
    result = check_and_consume(None, capacity=10, refill_per_second=1.0, now=now_fixed)

    assert result.allowed is True
    assert result.retry_after_seconds is None
    assert result.state.tokens == 9
    assert result.state.last_refill_at == now_fixed


@pytest.mark.unit
def test_request_denied_when_bucket_empty(now_fixed):
    """A bucket with fewer than one token available is denied, not consumed further."""
    empty_state = TokenBucketState(tokens=0, last_refill_at=now_fixed)

    result = check_and_consume(empty_state, capacity=10, refill_per_second=1.0, now=now_fixed)

    assert result.allowed is False
    assert result.state.tokens == 0
    assert result.retry_after_seconds is not None
    assert result.retry_after_seconds > 0


@pytest.mark.unit
def test_tokens_refill_over_elapsed_time(now_fixed):
    """Tokens accrue at refill_per_second between the stored state and now."""
    empty_state = TokenBucketState(tokens=0, last_refill_at=now_fixed)
    later = now_fixed + timedelta(seconds=5)

    result = check_and_consume(empty_state, capacity=10, refill_per_second=1.0, now=later)

    # 5 seconds * 1 token/sec = 5 tokens refilled, then 1 consumed for this request.
    assert result.allowed is True
    assert result.state.tokens == 4
    assert result.state.last_refill_at == later


@pytest.mark.unit
def test_bucket_never_refills_past_capacity(now_fixed):
    """A long idle period caps the bucket at capacity, not an unbounded surplus."""
    state = TokenBucketState(tokens=2, last_refill_at=now_fixed)
    much_later = now_fixed + timedelta(hours=1)

    result = check_and_consume(state, capacity=10, refill_per_second=1.0, now=much_later)

    # Capped at 10, then 1 consumed for this request -> 9, not 3602 - 1.
    assert result.allowed is True
    assert result.state.tokens == 9


@pytest.mark.unit
def test_retry_after_seconds_matches_refill_rate(now_fixed):
    """retry_after_seconds reflects how long until one token becomes available."""
    empty_state = TokenBucketState(tokens=0, last_refill_at=now_fixed)

    result = check_and_consume(empty_state, capacity=10, refill_per_second=0.5, now=now_fixed)

    # Needs 1 token at 0.5 tokens/sec -> 2 seconds, ceil'd.
    assert result.allowed is False
    assert result.retry_after_seconds == 2


@pytest.mark.unit
def test_elapsed_time_since_last_refill_still_consumes_one_token_when_allowed(now_fixed):
    """A request that succeeds always nets exactly one fewer token than the
    refilled-but-uncapped amount, whether or not any time has passed.
    """
    state = TokenBucketState(tokens=3, last_refill_at=now_fixed)

    result = check_and_consume(state, capacity=10, refill_per_second=1.0, now=now_fixed)

    assert result.allowed is True
    assert result.state.tokens == 2


@pytest.mark.unit
@pytest.mark.parametrize("refill_per_second", [0.0, -1.0])
def test_check_and_consume_rejects_non_positive_refill_rate(now_fixed, refill_per_second):
    """A refill rate of zero or less can never produce a valid
    retry_after_seconds (division by zero, or a negative wait). This is a
    contract violation by the caller (config resolution should never reach
    here with such a value - see app.core.config's Field(ge=1) bound on the
    env-sourced settings), not a state this pure module should silently
    accept and either crash on or return nonsense from.
    """
    empty_state = TokenBucketState(tokens=0, last_refill_at=now_fixed)

    with pytest.raises(ValueError, match="refill_per_second"):
        check_and_consume(
            empty_state, capacity=10, refill_per_second=refill_per_second, now=now_fixed
        )


@pytest.mark.unit
@pytest.mark.parametrize("capacity", [0, -1])
def test_check_and_consume_rejects_non_positive_capacity(now_fixed, capacity):
    """A zero or negative capacity bucket would deny every request forever
    with no way to recover - the same kind of caller contract violation as
    a non-positive refill rate, and equally worth failing loudly on rather
    than silently locking every identity out.
    """
    with pytest.raises(ValueError, match="capacity"):
        check_and_consume(None, capacity=capacity, refill_per_second=1.0, now=now_fixed)
