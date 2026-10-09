"""Unit tests for the versioned, append-only workflow store (issue #83) - TDD.

A workflow version is the record that answers "which prompt produced this
answer on the 14th?" after later edits, so it must be immutable once
written. Like AuditLogRepository, that guarantee is structural: the
repository has no method that could update or delete a version, and each
version carries a hash chain so out-of-band tampering with the table is
detectable (app.workflows.version_chain.verify_chain).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import WorkflowVersion
from app.repositories import WorkflowVersionRepository
from app.workflows.version_chain import compute_content_hash, verify_chain

NOW = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)

CHAT_V1 = (
    "name: chat\nversion: 1\nentry: respond\nsteps:\n  respond:\n    type: agent\n    prompt: one\n"
)
CHAT_V2 = CHAT_V1.replace("prompt: one", "prompt: two")


def _add(repo, yaml_text=CHAT_V1, *, name="chat", source="admin", now=NOW, parent=None):
    return repo.add(
        workflow_name=name,
        yaml_text=yaml_text,
        source=source,
        author_user_id="admin-1",
        change_note="tighten the prompt",
        parent_version_id=parent,
        now=now,
    )


@pytest.mark.unit
def test_repository_exposes_no_way_to_mutate_or_delete_a_version():
    """The public surface is the enforcement mechanism: an accidental
    update/delete method fails this test before any review has to notice."""
    public_methods = {name for name in dir(WorkflowVersionRepository) if not name.startswith("_")}

    assert public_methods == {
        "add",
        "get",
        "latest_for_workflow",
        "latest_builtin_for_workflow",
        "list_for_workflow",
        "list_workflow_names",
    }


@pytest.mark.unit
def test_add_records_author_note_source_and_content_hash(db_session):
    repo = WorkflowVersionRepository(db_session)

    version = _add(repo)
    db_session.commit()

    stored = db_session.query(WorkflowVersion).one()
    assert stored.id == version.id
    assert stored.workflow_name == "chat"
    assert stored.yaml_text == CHAT_V1
    assert stored.author_user_id == "admin-1"
    assert stored.change_note == "tighten the prompt"
    assert stored.source == "admin"
    assert stored.content_hash == compute_content_hash(CHAT_V1)
    assert stored.created_at == NOW.replace(tzinfo=None)


@pytest.mark.unit
def test_sequence_numbers_count_up_per_workflow_independently(db_session):
    repo = WorkflowVersionRepository(db_session)

    first_chat = _add(repo)
    second_chat = _add(repo, CHAT_V2, now=NOW + timedelta(minutes=1))
    first_triage = _add(repo, name="triage")

    assert (first_chat.sequence, second_chat.sequence, first_triage.sequence) == (1, 2, 1)


@pytest.mark.unit
def test_each_version_chains_to_the_previous_version_of_the_same_workflow(db_session):
    repo = WorkflowVersionRepository(db_session)

    first = _add(repo)
    second = _add(repo, CHAT_V2, now=NOW + timedelta(minutes=1))

    assert first.prev_chain_hash is None
    assert second.prev_chain_hash == first.chain_hash
    assert verify_chain(repo.list_for_workflow("chat")) is None


@pytest.mark.unit
def test_verify_chain_names_the_first_version_whose_content_was_tampered_with(db_session):
    """A direct UPDATE against the table (bypassing the repository) must be
    detectable after the fact."""
    repo = WorkflowVersionRepository(db_session)
    first = _add(repo)
    _add(repo, CHAT_V2, now=NOW + timedelta(minutes=1))
    db_session.commit()

    db_session.query(WorkflowVersion).filter(WorkflowVersion.id == first.id).update(
        {"yaml_text": CHAT_V1.replace("one", "something an attacker preferred")}
    )
    db_session.commit()

    broken = verify_chain(repo.list_for_workflow("chat"))
    assert broken is not None
    assert broken.id == first.id


@pytest.mark.unit
def test_two_versions_cannot_share_a_sequence_number(db_session):
    """The (workflow_name, sequence) uniqueness constraint is what stops two
    concurrent saves from forking the hash chain."""
    repo = WorkflowVersionRepository(db_session)
    first = _add(repo)
    db_session.commit()

    db_session.add(
        WorkflowVersion(
            workflow_name="chat",
            sequence=first.sequence,
            yaml_text=CHAT_V2,
            content_hash=compute_content_hash(CHAT_V2),
            chain_hash="x" * 64,
            prev_chain_hash=None,
            source="admin",
            author_user_id="admin-2",
            change_note="racing save",
            created_at=NOW.replace(tzinfo=None),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.unit
def test_list_for_workflow_returns_newest_first(db_session):
    repo = WorkflowVersionRepository(db_session)
    first = _add(repo)
    second = _add(repo, CHAT_V2, now=NOW + timedelta(minutes=1))

    assert [v.id for v in repo.list_for_workflow("chat")] == [second.id, first.id]


@pytest.mark.unit
def test_latest_builtin_ignores_admin_versions(db_session):
    repo = WorkflowVersionRepository(db_session)
    builtin = _add(repo, source="builtin")
    _add(repo, CHAT_V2, now=NOW + timedelta(minutes=1), parent=builtin.id)

    assert repo.latest_builtin_for_workflow("chat").id == builtin.id


@pytest.mark.unit
def test_list_workflow_names_is_sorted_and_distinct(db_session):
    repo = WorkflowVersionRepository(db_session)
    _add(repo, name="triage")
    _add(repo)
    _add(repo, CHAT_V2, now=NOW + timedelta(minutes=1))

    assert repo.list_workflow_names() == ["chat", "triage"]
