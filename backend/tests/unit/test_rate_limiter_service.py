"""Unit tests for the rate limiter service - TDD discipline.

Covers the in-process bucket store wired to resolved config: separate
buckets per identity, exhaustion denies further requests, and the
enabled=False kill switch bypasses checking entirely. See
app.ratelimit.token_bucket's own tests for the underlying algorithm's
math - these tests exercise the service layer that resolves config and
persists TokenBucketState between calls.
"""

from datetime import timedelta

import pytest

from app.db.models import SystemSettings
from app.services.rate_limiter_service import check_auth_rate_limit, check_chat_rate_limit

# Bucket state is reset automatically before/after every test by the
# autouse _reset_rate_limit_state fixture in tests/conftest.py.


@pytest.mark.unit
def test_check_chat_rate_limit_allows_first_request_for_new_user(db_session, now_fixed):
    result = check_chat_rate_limit(db_session, user_id="user-1", now=now_fixed)

    assert result.allowed is True
    assert result.retry_after_seconds is None


@pytest.mark.unit
def test_check_chat_rate_limit_denies_after_capacity_exhausted(db_session, now_fixed):
    db_session.add(
        SystemSettings(
            id="default",
            rate_limit_chat_capacity=2,
            rate_limit_chat_refill_per_minute=1,
            updated_by="admin-1",
        )
    )
    db_session.commit()

    check_chat_rate_limit(db_session, user_id="user-1", now=now_fixed)
    check_chat_rate_limit(db_session, user_id="user-1", now=now_fixed)
    result = check_chat_rate_limit(db_session, user_id="user-1", now=now_fixed)

    assert result.allowed is False
    assert result.retry_after_seconds is not None
    assert result.retry_after_seconds > 0


@pytest.mark.unit
def test_check_chat_rate_limit_tracks_separate_buckets_per_user(db_session, now_fixed):
    """One user exhausting their bucket must not affect another user's."""
    db_session.add(
        SystemSettings(
            id="default",
            rate_limit_chat_capacity=1,
            rate_limit_chat_refill_per_minute=1,
            updated_by="admin-1",
        )
    )
    db_session.commit()

    exhausted = check_chat_rate_limit(db_session, user_id="user-1", now=now_fixed)
    still_fresh = check_chat_rate_limit(db_session, user_id="user-2", now=now_fixed)

    assert exhausted.allowed is True  # user-1's first (and only) allowed request
    assert still_fresh.allowed is True  # user-2's own bucket is untouched


@pytest.mark.unit
def test_check_auth_rate_limit_tracks_separate_buckets_per_ip(db_session, now_fixed):
    db_session.add(
        SystemSettings(
            id="default",
            rate_limit_auth_capacity=1,
            rate_limit_auth_refill_per_minute=1,
            updated_by="admin-1",
        )
    )
    db_session.commit()

    check_auth_rate_limit(db_session, client_ip="10.0.0.1", now=now_fixed)
    exhausted = check_auth_rate_limit(db_session, client_ip="10.0.0.1", now=now_fixed)
    other_ip = check_auth_rate_limit(db_session, client_ip="10.0.0.2", now=now_fixed)

    assert exhausted.allowed is False
    assert other_ip.allowed is True


@pytest.mark.unit
def test_rate_limit_disabled_always_allows(db_session, now_fixed):
    """With rate_limit_enabled=False, every request is allowed and no bucket
    state is even consulted - mirrors how the guardrails' off switch skips
    check_input entirely rather than running it and ignoring the result.
    """
    db_session.add(
        SystemSettings(
            id="default",
            rate_limit_enabled=False,
            rate_limit_chat_capacity=1,
            rate_limit_chat_refill_per_minute=1,
            updated_by="admin-1",
        )
    )
    db_session.commit()

    for _ in range(5):
        result = check_chat_rate_limit(db_session, user_id="user-1", now=now_fixed)
        assert result.allowed is True
        assert result.retry_after_seconds is None


@pytest.mark.unit
def test_check_chat_rate_limit_refills_over_time(db_session, now_fixed):
    """A user who exhausts their bucket regains capacity as time passes,
    exercised through the service layer (not just the pure module) to
    confirm state is actually persisted and re-read between calls.
    """
    db_session.add(
        SystemSettings(
            id="default",
            rate_limit_chat_capacity=1,
            rate_limit_chat_refill_per_minute=60,  # 1 token/sec
            updated_by="admin-1",
        )
    )
    db_session.commit()

    check_chat_rate_limit(db_session, user_id="user-1", now=now_fixed)
    denied = check_chat_rate_limit(db_session, user_id="user-1", now=now_fixed)
    later = now_fixed + timedelta(seconds=2)
    allowed_again = check_chat_rate_limit(db_session, user_id="user-1", now=later)

    assert denied.allowed is False
    assert allowed_again.allowed is True
