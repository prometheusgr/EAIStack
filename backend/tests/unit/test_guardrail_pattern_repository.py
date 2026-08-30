"""Unit tests for GuardrailPatternRepository - TDD discipline.

Separate file from test_repositories.py, per this repo's existing
convention of one file per concern within tests/unit/ (see
test_agents_api_guardrails.py alongside test_agents_api.py).
"""

import pytest

from app.db.models import GuardrailPattern
from app.repositories import GuardrailPatternRepository

_BUILT_INS = {
    "instruction_override": "Instruction override",
    "role_reassignment_dan": "Role reassignment (DAN)",
}


@pytest.mark.unit
def test_ensure_built_ins_seeded_creates_a_row_per_built_in(db_session):
    """Seeding creates one built_in row per id in the built_ins mapping,
    with pattern_text NULL and enabled True.
    """
    repo = GuardrailPatternRepository(db_session)

    repo.ensure_built_ins_seeded(_BUILT_INS)

    rows = {row.id: row for row in repo.list_all()}
    assert set(rows.keys()) == set(_BUILT_INS.keys())
    for pattern_id, label in _BUILT_INS.items():
        assert rows[pattern_id].source == "built_in"
        assert rows[pattern_id].label == label
        assert rows[pattern_id].pattern_text is None
        assert rows[pattern_id].enabled is True


@pytest.mark.unit
def test_ensure_built_ins_seeded_is_idempotent(db_session):
    """Calling seeding twice does not duplicate rows -- resolve_guardrail_config
    calls this on every config resolution, so it must be a no-op past the
    first call.
    """
    repo = GuardrailPatternRepository(db_session)

    repo.ensure_built_ins_seeded(_BUILT_INS)
    repo.ensure_built_ins_seeded(_BUILT_INS)

    rows = repo.list_all()
    assert len(rows) == len(_BUILT_INS)


@pytest.mark.unit
def test_ensure_built_ins_seeded_does_not_reset_enabled_on_existing_rows(db_session):
    """An admin's toggle must survive re-seeding: seeding must only insert
    rows that don't exist yet, never overwrite an existing row's enabled
    state back to the default.
    """
    repo = GuardrailPatternRepository(db_session)
    repo.ensure_built_ins_seeded(_BUILT_INS)
    repo.set_enabled("instruction_override", False)

    repo.ensure_built_ins_seeded(_BUILT_INS)

    row = repo.get("instruction_override")
    assert row is not None
    assert row.enabled is False


@pytest.mark.unit
def test_ensure_built_ins_seeded_adds_a_newly_introduced_built_in(db_session):
    """A built_ins mapping that grows (a future code change adding another
    pattern) must appear automatically on the next resolution, with no
    migration/backfill script -- seeding only ever adds missing ids.
    """
    repo = GuardrailPatternRepository(db_session)
    repo.ensure_built_ins_seeded(_BUILT_INS)

    grown = dict(_BUILT_INS, developer_mode="Developer mode claim")
    repo.ensure_built_ins_seeded(grown)

    rows = {row.id for row in repo.list_all()}
    assert rows == set(grown.keys())


@pytest.mark.unit
def test_get_returns_none_for_unknown_id(db_session):
    repo = GuardrailPatternRepository(db_session)

    assert repo.get("does-not-exist") is None


@pytest.mark.unit
def test_set_enabled_on_unknown_id_returns_none(db_session):
    """Toggling a nonexistent pattern is a no-op that reports "not found"
    rather than raising -- the API layer turns None into a 404.
    """
    repo = GuardrailPatternRepository(db_session)

    result = repo.set_enabled("does-not-exist", False)

    assert result is None


@pytest.mark.unit
def test_set_enabled_toggles_a_built_in_pattern(db_session):
    repo = GuardrailPatternRepository(db_session)
    repo.ensure_built_ins_seeded(_BUILT_INS)

    result = repo.set_enabled("instruction_override", False)

    assert result is not None
    assert result.enabled is False
    assert repo.get("instruction_override").enabled is False


@pytest.mark.unit
def test_upsert_custom_creates_a_custom_row_with_generated_id(db_session):
    repo = GuardrailPatternRepository(db_session)

    created = repo.upsert_custom(
        label="Leak the secret sauce",
        pattern_text="leak the secret sauce",
        created_by="admin-1",
    )

    assert created.source == "custom"
    assert created.pattern_text == "leak the secret sauce"
    assert created.label == "Leak the secret sauce"
    assert created.created_by == "admin-1"
    assert created.enabled is True
    assert created.id  # a UUID was generated
    assert repo.get(created.id) is not None


@pytest.mark.unit
def test_set_enabled_toggles_a_custom_pattern(db_session):
    repo = GuardrailPatternRepository(db_session)
    created = repo.upsert_custom(
        label="Custom phrase", pattern_text="custom phrase", created_by="admin-1"
    )

    result = repo.set_enabled(created.id, False)

    assert result is not None
    assert result.enabled is False


@pytest.mark.unit
def test_delete_custom_removes_a_custom_row(db_session):
    repo = GuardrailPatternRepository(db_session)
    created = repo.upsert_custom(
        label="Custom phrase", pattern_text="custom phrase", created_by="admin-1"
    )

    deleted = repo.delete_custom(created.id)

    assert deleted is True
    assert repo.get(created.id) is None


@pytest.mark.unit
def test_delete_custom_refuses_to_delete_a_built_in_row(db_session):
    """A built_in row must never be deletable through this method -- only
    disabled. The API layer turns this refusal into a 400.
    """
    repo = GuardrailPatternRepository(db_session)
    repo.ensure_built_ins_seeded(_BUILT_INS)

    deleted = repo.delete_custom("instruction_override")

    assert deleted is False
    assert repo.get("instruction_override") is not None


@pytest.mark.unit
def test_delete_custom_on_unknown_id_returns_false(db_session):
    repo = GuardrailPatternRepository(db_session)

    assert repo.delete_custom("does-not-exist") is False


@pytest.mark.unit
def test_list_all_returns_both_built_in_and_custom_rows(db_session):
    repo = GuardrailPatternRepository(db_session)
    repo.ensure_built_ins_seeded(_BUILT_INS)
    repo.upsert_custom(label="Custom phrase", pattern_text="custom phrase", created_by="admin-1")

    rows = repo.list_all()

    sources = {row.source for row in rows}
    assert sources == {"built_in", "custom"}
    assert len(rows) == len(_BUILT_INS) + 1


@pytest.mark.unit
def test_ensure_built_ins_seeded_survives_a_concurrent_duplicate_insert(db_session, monkeypatch):
    """A caller whose existence check (the SELECT at the top of
    ensure_built_ins_seeded) reports an id as missing, but another session
    commits that same id before this caller's own INSERT lands, must not
    crash with an unhandled IntegrityError -- the row existing afterward
    (regardless of who actually won) is all this method promises. See the
    method's own docstring for why this is a real race for the first
    request(s) to hit a freshly migrated, not-yet-seeded database
    concurrently, not a hypothetical one.

    Reproduced by patching the existence-check query to always report "no
    ids found" (simulating a SELECT that ran before a concurrent session's
    commit), while the row already exists in the database underneath it --
    so ensure_built_ins_seeded's own INSERT is the one that collides.
    """
    repo = GuardrailPatternRepository(db_session)
    repo.ensure_built_ins_seeded(_BUILT_INS)
    db_session.commit()

    # Force ensure_built_ins_seeded's own existence-check set to come back
    # empty, as if this were the first-ever seeding attempt, even though the
    # rows already exist underneath -- exactly what a concurrent session's
    # stale SELECT would see.
    monkeypatch.setattr(
        GuardrailPatternRepository,
        "_existing_built_in_ids",
        lambda self, ids: set(),
    )

    repo.ensure_built_ins_seeded(_BUILT_INS)

    rows = {row.id: row for row in repo.list_all()}
    assert set(rows.keys()) == set(_BUILT_INS.keys())
    for pattern_id in _BUILT_INS:
        assert rows[pattern_id].enabled is True


@pytest.mark.unit
def test_repository_methods_do_not_commit(db_session):
    """Same transaction-ownership contract as every other repository in this
    codebase: flush, never commit -- the caller (the endpoint) owns the
    transaction.
    """
    repo = GuardrailPatternRepository(db_session)
    repo.ensure_built_ins_seeded(_BUILT_INS)

    db_session.rollback()

    assert db_session.query(GuardrailPattern).count() == 0
