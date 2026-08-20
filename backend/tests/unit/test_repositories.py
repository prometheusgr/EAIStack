"""Unit tests for Repository Pattern - TDD discipline."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.models import APIKey, Embedding, KnowledgeBase, ProviderEnum
from app.repositories import APIKeyRepository, EmbeddingRepository, KnowledgeBaseRepository

# === EMBEDDING REPOSITORY TESTS ===


@pytest.mark.unit
def test_embedding_repository_get_by_id(db_session):
    """Test: EmbeddingRepository.get_by_id returns embedding with ownership check."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 768,
    )
    db_session.add(emb)
    db_session.commit()

    # Execute
    repo = EmbeddingRepository(db_session)
    result = repo.get_by_id(emb.id, "user-a")

    # Verify
    assert result is not None
    assert result.id == emb.id


@pytest.mark.unit
def test_embedding_repository_get_by_id_wrong_user_returns_none(db_session):
    """Test: EmbeddingRepository.get_by_id returns None for wrong user."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 768,
    )
    db_session.add(emb)
    db_session.commit()

    # Execute
    repo = EmbeddingRepository(db_session)
    result = repo.get_by_id(emb.id, "user-b")

    # Verify
    assert result is None


@pytest.mark.unit
def test_embedding_repository_get_knowledge_base(db_session):
    """Test: EmbeddingRepository.get_knowledge_base_for_embedding returns KB."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 768,
    )
    db_session.add(emb)
    db_session.commit()

    # Execute
    repo = EmbeddingRepository(db_session)
    result = repo.get_knowledge_base_for_embedding(emb.id)

    # Verify
    assert result is not None
    assert result.id == kb.id
    assert result.title == "Test Doc"


@pytest.mark.unit
def test_embedding_repository_update_metadata(db_session):
    """Test: EmbeddingRepository.update_metadata updates and commits."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 768,
        embed_metadata={"old": "value"},
    )
    db_session.add(emb)
    db_session.commit()

    # Execute
    repo = EmbeddingRepository(db_session)
    repo.update_metadata(emb.id, {"new": "value"})

    # Verify
    db_session.refresh(emb)
    assert emb.embed_metadata == {"new": "value"}


@pytest.mark.unit
def test_embedding_repository_soft_delete(db_session):
    """Test: EmbeddingRepository.soft_delete sets deleted_at."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 768,
    )
    db_session.add(emb)
    db_session.commit()

    # Execute
    repo = EmbeddingRepository(db_session)
    repo.soft_delete(emb.id)

    # Verify
    db_session.refresh(emb)
    assert emb.deleted_at is not None


@pytest.mark.unit
def test_embedding_repository_list_for_user(db_session):
    """Test: EmbeddingRepository.list_for_user returns embedding-KB pairs."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    emb1 = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 768,
    )
    emb2 = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.2] * 768,
    )
    db_session.add_all([emb1, emb2])
    db_session.commit()

    # Execute
    repo = EmbeddingRepository(db_session)
    results = repo.list_for_user("user-a")

    # Verify
    assert len(results) == 2
    assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in results)
    for emb, kb_result in results:
        assert kb_result.id == kb.id
        assert kb_result.title == "Test Doc"


@pytest.mark.unit
def test_embedding_repository_list_for_user_filters_deleted(db_session):
    """Test: EmbeddingRepository.list_for_user excludes soft-deleted embeddings."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    active_emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 768,
    )
    deleted_emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.2] * 768,
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add_all([active_emb, deleted_emb])
    db_session.commit()

    # Execute
    repo = EmbeddingRepository(db_session)
    results = repo.list_for_user("user-a")

    # Verify
    assert len(results) == 1
    emb, kb_result = results[0]
    assert emb.id == active_emb.id
    assert emb.deleted_at is None
    assert kb_result.id == kb.id


# === API KEY REPOSITORY TESTS ===


@pytest.mark.unit
def test_apikey_repository_get_by_user(db_session):
    """Test: APIKeyRepository.get_by_user returns active keys for user."""
    key1 = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Key 1",
        provider=ProviderEnum.openai,
        secret_value="secret-1",
    )
    key2 = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Key 2",
        provider=ProviderEnum.anthropic,
        secret_value="secret-2",
    )
    db_session.add_all([key1, key2])
    db_session.commit()

    # Execute
    repo = APIKeyRepository(db_session)
    results = repo.get_by_user("user-a")

    # Verify
    assert len(results) == 2
    names = {k.name for k in results}
    assert names == {"Key 1", "Key 2"}


@pytest.mark.unit
def test_apikey_repository_get_by_user_filters_revoked(db_session):
    """Test: APIKeyRepository.get_by_user excludes revoked keys."""
    active_key = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Active",
        provider=ProviderEnum.openai,
        secret_value="secret-1",
    )
    revoked_key = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Revoked",
        provider=ProviderEnum.openai,
        secret_value="secret-2",
        revoked_at=datetime.now(timezone.utc),
    )
    db_session.add_all([active_key, revoked_key])
    db_session.commit()

    # Execute
    repo = APIKeyRepository(db_session)
    results = repo.get_by_user("user-a")

    # Verify
    assert len(results) == 1
    assert results[0].name == "Active"


@pytest.mark.unit
def test_apikey_repository_get_by_id(db_session):
    """Test: APIKeyRepository.get_by_id returns key with ownership check."""
    key = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Test Key",
        provider=ProviderEnum.openai,
        secret_value="secret",
    )
    db_session.add(key)
    db_session.commit()

    # Execute
    repo = APIKeyRepository(db_session)
    result = repo.get_by_id(key.id, "user-a")

    # Verify
    assert result is not None
    assert result.id == key.id
    assert result.name == "Test Key"


@pytest.mark.unit
def test_apikey_repository_get_by_id_wrong_user_returns_none(db_session):
    """Test: APIKeyRepository.get_by_id returns None for wrong user."""
    key = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Test Key",
        provider=ProviderEnum.openai,
        secret_value="secret",
    )
    db_session.add(key)
    db_session.commit()

    # Execute
    repo = APIKeyRepository(db_session)
    result = repo.get_by_id(key.id, "user-b")

    # Verify
    assert result is None


@pytest.mark.unit
def test_apikey_repository_create(db_session):
    """Test: APIKeyRepository.create creates and commits key."""
    # Execute
    repo = APIKeyRepository(db_session)
    key = repo.create(
        user_id="user-a",
        name="New Key",
        provider="openai",
        secret_value="secret-value",
    )

    # Verify
    assert key.id is not None
    assert key.user_id == "user-a"
    assert key.name == "New Key"
    assert key.provider == "openai"
    assert key.secret_value == "secret-value"
    # Verify it was committed
    db_session.refresh(key)
    assert key.created_at is not None


@pytest.mark.unit
def test_apikey_repository_update(db_session):
    """Test: APIKeyRepository.update updates name and provider."""
    key = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Old Name",
        provider=ProviderEnum.openai,
        secret_value="secret",
    )
    db_session.add(key)
    db_session.commit()

    # Execute
    repo = APIKeyRepository(db_session)
    repo.update(key.id, "New Name", "anthropic")

    # Verify
    db_session.refresh(key)
    assert key.name == "New Name"
    assert key.provider == "anthropic"


@pytest.mark.unit
def test_apikey_repository_update_skips_revoked(db_session):
    """Test: APIKeyRepository.update skips revoked keys."""
    key = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Old Name",
        provider=ProviderEnum.openai,
        secret_value="secret",
        revoked_at=datetime.now(timezone.utc),
    )
    db_session.add(key)
    db_session.commit()

    # Execute
    repo = APIKeyRepository(db_session)
    repo.update(key.id, "New Name", "anthropic")

    # Verify (no change)
    db_session.refresh(key)
    assert key.name == "Old Name"
    assert key.provider == ProviderEnum.openai


@pytest.mark.unit
def test_apikey_repository_revoke(db_session):
    """Test: APIKeyRepository.revoke sets revoked_at."""
    key = APIKey(
        id=str(uuid4()),
        user_id="user-a",
        name="Test Key",
        provider=ProviderEnum.openai,
        secret_value="secret",
    )
    db_session.add(key)
    db_session.commit()

    # Execute
    repo = APIKeyRepository(db_session)
    repo.revoke(key.id)

    # Verify
    db_session.refresh(key)
    assert key.revoked_at is not None


# === KNOWLEDGE BASE REPOSITORY TESTS ===


@pytest.mark.unit
def test_knowledge_base_repository_get_by_user(db_session):
    """Test: KnowledgeBaseRepository.get_by_user returns active entries for user."""
    kb1 = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Doc 1",
        content="Content 1",
    )
    kb2 = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Doc 2",
        content="Content 2",
    )
    db_session.add_all([kb1, kb2])
    db_session.commit()

    # Execute
    repo = KnowledgeBaseRepository(db_session)
    results = repo.get_by_user("user-a")

    # Verify
    assert len(results) == 2
    assert all(kb.user_id == "user-a" for kb in results)


@pytest.mark.unit
def test_knowledge_base_repository_get_by_user_filters_deleted(db_session):
    """Test: KnowledgeBaseRepository.get_by_user excludes soft-deleted entries."""
    active_kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Active",
        content="Active content",
    )
    deleted_kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Deleted",
        content="Deleted content",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add_all([active_kb, deleted_kb])
    db_session.commit()

    # Execute
    repo = KnowledgeBaseRepository(db_session)
    results = repo.get_by_user("user-a")

    # Verify
    assert len(results) == 1
    assert results[0].id == active_kb.id


@pytest.mark.unit
def test_knowledge_base_repository_get_by_id(db_session):
    """Test: KnowledgeBaseRepository.get_by_id returns entry with ownership check."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    # Execute
    repo = KnowledgeBaseRepository(db_session)
    result = repo.get_by_id(kb.id, "user-a")

    # Verify
    assert result is not None
    assert result.id == kb.id


@pytest.mark.unit
def test_knowledge_base_repository_get_by_id_wrong_user_returns_none(db_session):
    """Test: KnowledgeBaseRepository.get_by_id returns None for wrong user."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    # Execute
    repo = KnowledgeBaseRepository(db_session)
    result = repo.get_by_id(kb.id, "user-b")

    # Verify
    assert result is None


@pytest.mark.unit
def test_knowledge_base_repository_get_by_id_soft_deleted_returns_none(db_session):
    """Test: KnowledgeBaseRepository.get_by_id returns None for a soft-deleted entry."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(kb)
    db_session.commit()

    # Execute
    repo = KnowledgeBaseRepository(db_session)
    result = repo.get_by_id(kb.id, "user-a")

    # Verify
    assert result is None


@pytest.mark.unit
def test_knowledge_base_repository_create(db_session):
    """Test: KnowledgeBaseRepository.create persists and returns the entry."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="New Doc",
        content="New content",
    )

    # Execute
    repo = KnowledgeBaseRepository(db_session)
    result = repo.create(kb)

    # Verify
    assert result.id == kb.id
    retrieved = db_session.query(KnowledgeBase).filter_by(id=kb.id).first()
    assert retrieved is not None
    assert retrieved.title == "New Doc"


@pytest.mark.unit
def test_knowledge_base_repository_update(db_session):
    """Test: KnowledgeBaseRepository.update modifies fields and commits."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Old Title",
        content="Old content",
    )
    db_session.add(kb)
    db_session.commit()

    # Execute
    repo = KnowledgeBaseRepository(db_session)
    repo.update(kb, "New Title", "New content", {"key": "value"})

    # Verify
    db_session.refresh(kb)
    assert kb.title == "New Title"
    assert kb.content == "New content"
    assert kb.doc_metadata == {"key": "value"}


@pytest.mark.unit
def test_knowledge_base_repository_soft_delete_with_embeddings(db_session):
    """Test: KnowledgeBaseRepository.soft_delete_with_embeddings deletes KB and its embeddings."""
    kb = KnowledgeBase(
        id=str(uuid4()),
        user_id="user-a",
        title="Test Doc",
        content="Test content",
    )
    db_session.add(kb)
    db_session.commit()

    emb = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=[0.1] * 768,
    )
    db_session.add(emb)
    db_session.commit()

    # Execute
    repo = KnowledgeBaseRepository(db_session)
    repo.soft_delete_with_embeddings(kb)

    # Verify
    db_session.refresh(kb)
    db_session.refresh(emb)
    assert kb.deleted_at is not None
    assert emb.deleted_at is not None
