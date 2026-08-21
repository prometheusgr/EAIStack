"""Unit tests for ThreadRepository - TDD discipline."""

from datetime import datetime

import pytest

from app.db.models import ConversationThread
from app.repositories import ThreadRepository


@pytest.mark.unit
def test_get_or_create_owned_creates_new_thread_when_thread_id_is_none(db_session):
    """Test: get_or_create_owned mints a new thread when no thread_id is supplied."""
    repo = ThreadRepository(db_session)

    thread = repo.get_or_create_owned(None, "user-a")

    assert thread.id is not None
    assert thread.user_id == "user-a"


@pytest.mark.unit
def test_get_or_create_owned_returns_existing_thread_when_owned(db_session):
    """Test: get_or_create_owned returns the same thread on repeat calls by its owner."""
    repo = ThreadRepository(db_session)
    first = repo.get_or_create_owned(None, "user-a")
    db_session.commit()

    second = repo.get_or_create_owned(first.id, "user-a")

    assert second.id == first.id


@pytest.mark.unit
def test_get_or_create_owned_mints_new_thread_when_thread_id_not_owned_by_caller(db_session):
    """Test: get_or_create_owned silently mints a fresh thread when the supplied
    thread_id belongs to a different user, rather than granting access to it.
    """
    repo = ThreadRepository(db_session)
    user_a_thread = repo.get_or_create_owned(None, "user-a")
    db_session.commit()

    result = repo.get_or_create_owned(user_a_thread.id, "user-b")

    assert result.id != user_a_thread.id
    assert result.user_id == "user-b"


@pytest.mark.unit
def test_get_or_create_owned_mints_new_thread_when_thread_id_unknown(db_session):
    """Test: get_or_create_owned mints a fresh thread for a thread_id that doesn't exist."""
    repo = ThreadRepository(db_session)

    result = repo.get_or_create_owned("does-not-exist", "user-a")

    assert result.id != "does-not-exist"
    assert result.user_id == "user-a"


@pytest.mark.unit
def test_get_by_id_for_user_returns_thread_when_owned(db_session):
    """Test: get_by_id_for_user returns the thread when owned by the caller."""
    repo = ThreadRepository(db_session)
    thread = repo.get_or_create_owned(None, "user-a")
    db_session.commit()

    result = repo.get_by_id_for_user(thread.id, "user-a")

    assert result is not None
    assert result.id == thread.id


@pytest.mark.unit
def test_get_by_id_for_user_returns_none_when_not_owned(db_session):
    """Test: get_by_id_for_user returns None when the thread belongs to another user."""
    repo = ThreadRepository(db_session)
    thread = repo.get_or_create_owned(None, "user-a")
    db_session.commit()

    result = repo.get_by_id_for_user(thread.id, "user-b")

    assert result is None


@pytest.mark.unit
def test_get_by_id_for_user_returns_none_when_thread_does_not_exist(db_session):
    """Test: get_by_id_for_user returns None for an unknown thread_id."""
    repo = ThreadRepository(db_session)

    result = repo.get_by_id_for_user("does-not-exist", "user-a")

    assert result is None


@pytest.mark.unit
def test_list_for_user_excludes_other_users_threads(db_session):
    """Test: list_for_user only returns threads owned by the given user."""
    repo = ThreadRepository(db_session)
    own_thread = repo.get_or_create_owned(None, "user-a")
    repo.get_or_create_owned(None, "user-b")
    db_session.commit()

    result = repo.list_for_user("user-a")

    assert [t.id for t in result] == [own_thread.id]


@pytest.mark.unit
def test_list_for_user_orders_by_most_recently_updated_first(db_session):
    """Test: list_for_user returns threads ordered by updated_at descending."""
    repo = ThreadRepository(db_session)
    # updated_at is set explicitly rather than relying on the gap between two
    # inserts: the system clock's resolution is coarser (~15ms on Windows) than
    # the time it takes to create two rows, so both would otherwise share a
    # timestamp and the ordering under test would be an arbitrary tie-break.
    older = ConversationThread(user_id="user-a", updated_at=datetime(2026, 1, 1, 12, 0, 0))
    newer = ConversationThread(user_id="user-a", updated_at=datetime(2026, 1, 1, 13, 0, 0))
    db_session.add_all([older, newer])
    db_session.commit()

    result = repo.list_for_user("user-a")

    assert [t.id for t in result] == [newer.id, older.id]
