"""Unit tests for SqlAlchemyCheckpointSaver - TDD discipline."""

import pytest
from langgraph.checkpoint.base import empty_checkpoint

from app.agents.checkpointer import SqlAlchemyCheckpointSaver
from app.repositories import ThreadRepository


@pytest.mark.unit
def test_get_tuple_returns_none_for_fresh_thread(db_session):
    """Test: get_tuple returns None when the thread has no checkpoint yet."""
    thread = ThreadRepository(db_session).get_or_create_owned(None, "user-a")
    db_session.commit()
    saver = SqlAlchemyCheckpointSaver(db_session)
    config = {"configurable": {"thread_id": thread.id}}

    result = saver.get_tuple(config)

    assert result is None


@pytest.mark.unit
def test_put_then_get_tuple_roundtrips_checkpoint(db_session):
    """Test: a checkpoint written via put() is readable via get_tuple()."""
    thread = ThreadRepository(db_session).get_or_create_owned(None, "user-a")
    db_session.commit()
    saver = SqlAlchemyCheckpointSaver(db_session)
    config = {"configurable": {"thread_id": thread.id, "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": ["hello"]}
    checkpoint["channel_versions"] = {"messages": "1"}
    metadata = {"source": "loop", "step": 0}

    saver.put(config, checkpoint, metadata, {"messages": "1"})
    db_session.commit()

    result = saver.get_tuple(config)
    assert result is not None
    assert result.checkpoint["id"] == checkpoint["id"]
    assert result.checkpoint["channel_values"] == {"messages": ["hello"]}
    assert result.metadata == metadata


@pytest.mark.unit
def test_put_overwrites_previous_checkpoint_for_same_thread(db_session):
    """Test: a second put() for the same thread replaces the first (latest-only storage)."""
    thread = ThreadRepository(db_session).get_or_create_owned(None, "user-a")
    db_session.commit()
    saver = SqlAlchemyCheckpointSaver(db_session)
    config = {"configurable": {"thread_id": thread.id, "checkpoint_ns": ""}}

    first = empty_checkpoint()
    first["channel_values"] = {"messages": ["first"]}
    saver.put(config, first, {"step": 0}, {})
    db_session.commit()

    second = empty_checkpoint()
    second["channel_values"] = {"messages": ["first", "second"]}
    saver.put(config, second, {"step": 1}, {})
    db_session.commit()

    result = saver.get_tuple(config)
    assert result.checkpoint["channel_values"] == {"messages": ["first", "second"]}


@pytest.mark.unit
def test_list_yields_the_latest_checkpoint(db_session):
    """Test: list() yields the single stored checkpoint tuple for the thread."""
    thread = ThreadRepository(db_session).get_or_create_owned(None, "user-a")
    db_session.commit()
    saver = SqlAlchemyCheckpointSaver(db_session)
    config = {"configurable": {"thread_id": thread.id, "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    saver.put(config, checkpoint, {"step": 0}, {})
    db_session.commit()

    results = list(saver.list(config))

    assert len(results) == 1
    assert results[0].checkpoint["id"] == checkpoint["id"]


@pytest.mark.unit
def test_list_yields_nothing_for_thread_with_no_checkpoint(db_session):
    """Test: list() yields no items when the thread has never been checkpointed."""
    thread = ThreadRepository(db_session).get_or_create_owned(None, "user-a")
    db_session.commit()
    saver = SqlAlchemyCheckpointSaver(db_session)
    config = {"configurable": {"thread_id": thread.id, "checkpoint_ns": ""}}

    results = list(saver.list(config))

    assert results == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"filter": {"source": "loop"}}, id="filter"),
        pytest.param({"before": {"configurable": {"thread_id": "t"}}}, id="before"),
        pytest.param({"limit": 5}, id="limit"),
    ],
)
def test_list_raises_for_unsupported_filtering_arguments(db_session, kwargs):
    """Test: list() raises NotImplementedError rather than silently ignoring
    filter/before/limit.

    This saver stores only the latest checkpoint per thread (see the module
    docstring), so it structurally cannot honor any of these - there is at
    most one checkpoint to return, and neither "filter it out" nor "list
    checkpoints before X" nor "cap at N" is a meaningful operation on a
    single-item result. Silently ignoring the argument and returning the
    one checkpoint anyway would be wrong in a way a caller could not detect;
    raising surfaces the mismatch immediately, matching
    BaseCheckpointSaver.list's own documented default of NotImplementedError
    for anything a subclass can't actually support.
    """
    thread = ThreadRepository(db_session).get_or_create_owned(None, "user-a")
    db_session.commit()
    saver = SqlAlchemyCheckpointSaver(db_session)
    config = {"configurable": {"thread_id": thread.id, "checkpoint_ns": ""}}

    with pytest.raises(NotImplementedError):
        list(saver.list(config, **kwargs))
