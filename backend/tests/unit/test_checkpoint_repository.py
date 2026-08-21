"""Unit tests for CheckpointRepository - TDD discipline."""

import pytest

from app.repositories import CheckpointRepository, ThreadRepository


@pytest.mark.unit
def test_get_returns_none_for_unknown_thread(db_session):
    """Test: get returns None when no checkpoint exists for the thread."""
    repo = CheckpointRepository(db_session)

    result = repo.get("does-not-exist")

    assert result is None


@pytest.mark.unit
def test_upsert_creates_row_on_first_write(db_session):
    """Test: upsert persists a new checkpoint row for a thread with none yet."""
    thread = ThreadRepository(db_session).get_or_create_owned(None, "user-a")
    db_session.commit()
    repo = CheckpointRepository(db_session)

    result = repo.upsert(thread.id, checkpoint=b"checkpoint-bytes-1", metadata=b"metadata-bytes-1")

    assert result.thread_id == thread.id
    assert result.checkpoint == b"checkpoint-bytes-1"
    assert result.checkpoint_metadata == b"metadata-bytes-1"


@pytest.mark.unit
def test_upsert_updates_existing_row_on_second_write(db_session):
    """Test: upsert overwrites the existing row rather than creating a second one."""
    thread = ThreadRepository(db_session).get_or_create_owned(None, "user-a")
    db_session.commit()
    repo = CheckpointRepository(db_session)
    repo.upsert(thread.id, checkpoint=b"checkpoint-1", metadata=b"metadata-1")
    db_session.commit()

    repo.upsert(thread.id, checkpoint=b"checkpoint-2", metadata=b"metadata-1")
    db_session.commit()

    result = repo.get(thread.id)
    assert result.checkpoint == b"checkpoint-2"


@pytest.mark.unit
def test_get_returns_the_upserted_checkpoint(db_session):
    """Test: get round-trips exactly what upsert stored."""
    thread = ThreadRepository(db_session).get_or_create_owned(None, "user-a")
    db_session.commit()
    repo = CheckpointRepository(db_session)
    repo.upsert(thread.id, checkpoint=b"checkpoint-payload", metadata=b"metadata-payload")
    db_session.commit()

    result = repo.get(thread.id)

    assert result is not None
    assert result.checkpoint == b"checkpoint-payload"
    assert result.checkpoint_metadata == b"metadata-payload"
