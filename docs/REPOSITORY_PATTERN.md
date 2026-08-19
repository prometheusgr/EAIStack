# Repository Pattern for Data Access

This is the canonical worked example for creating a repository. Follow this pattern exactly — new repositories should look like this one, not invent a new shape.

Governing standards live in [AGENTS.md](../AGENTS.md); this doc is the how-to.

**All database queries must live in repository classes, not in API endpoints.** Repositories centralize query logic, enable testability, and prevent query duplication.

## When to Create a Repository

Create a repository for each data model (or group of related models) that is queried by API endpoints:
- One repository per ORM model class (e.g., `EmbeddingRepository` for `Embedding` model)
- Repository groups related query methods for a single entity
- Repositories enable unit testing of query logic without HTTP concerns

**Examples:**
- `EmbeddingRepository` — manages all `Embedding` queries (search, get, update, delete)
- `APIKeyRepository` — manages all `APIKey` queries (create, list, revoke)
- Future: `KnowledgeBaseRepository`, `AgentRepository`, `SessionRepository`, etc.

## Pattern: Create a Repository

**1. Write Tests First (TDD)**
```python
# tests/unit/test_repositories.py
@pytest.mark.unit
def test_embedding_repository_search_by_user(db_session):
    """Test: EmbeddingRepository.search_by_user returns active embeddings."""
    kb = KnowledgeBase(id=str(uuid4()), user_id="user-a", title="Test", content="Content")
    db_session.add(kb)
    db_session.commit()

    emb = Embedding(id=str(uuid4()), doc_id=kb.id, embedding=[0.1] * 1536)
    db_session.add(emb)
    db_session.commit()

    repo = EmbeddingRepository(db_session)
    results = repo.search_by_user("user-a")

    assert len(results) == 1
    assert results[0].id == emb.id
```

**2. Create the Repository Class**
```python
# app/repositories/embedding_repository.py
"""Repository for Embedding data access."""

from sqlalchemy.orm import Session
from app.db.models import Embedding, KnowledgeBase


class EmbeddingRepository:
    """Repository for querying and managing embeddings."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def search_by_user(self, user_id: str) -> list[Embedding]:
        """Fetch all active embeddings for a user.

        Returns embeddings that are not soft-deleted and belong to user's knowledge bases.
        """
        return self.db.query(Embedding).join(
            KnowledgeBase,
            Embedding.doc_id == KnowledgeBase.id
        ).filter(
            KnowledgeBase.user_id == user_id,
            Embedding.deleted_at.is_(None),
        ).all()

    def get_by_id(self, embedding_id: str, user_id: str) -> Embedding | None:
        """Fetch a single embedding by ID, verifying user ownership."""
        return self.db.query(Embedding).join(
            KnowledgeBase,
            Embedding.doc_id == KnowledgeBase.id
        ).filter(
            Embedding.id == embedding_id,
            KnowledgeBase.user_id == user_id,
        ).first()

    def soft_delete(self, embedding_id: str) -> None:
        """Soft-delete an embedding by setting deleted_at timestamp."""
        from datetime import datetime, timezone

        embedding = self.db.query(Embedding).filter(
            Embedding.id == embedding_id
        ).first()

        if embedding:
            embedding.deleted_at = datetime.now(timezone.utc)
            self.db.commit()
```

**Key design principles:**
- **No FastAPI imports** — Repositories are pure data access, not HTTP handlers
- **Take `db: Session` in constructor** — Dependency injection enables testing with mock/test DBs
- **One model/entity per repository** — Don't mix `Embedding` and `APIKey` queries in one class
- **Methods return ORM models or None** — Not DTOs or JSON; let endpoints handle response formatting
- **User isolation built-in** — All queries filter by `user_id` to prevent cross-tenant data leaks
- **Soft-delete awareness** — Query methods exclude soft-deleted records by default
- **Clear docstrings** — Explain *what* each method does and any important filtering/ownership checks

**3. Export from Repositories `__init__.py`**
```python
# app/repositories/__init__.py
"""Repository module for data access abstraction."""

from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.api_key_repository import APIKeyRepository

__all__ = [
    "EmbeddingRepository",
    "APIKeyRepository",
]
```

**4. Replace Direct Queries in API Endpoints**

**Before (❌ query logic in endpoint):**
```python
# app/api/embeddings.py
@router.get("/{embedding_id}")
async def get_embedding(embedding_id: str, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    # Direct query logic in endpoint
    embedding = db.query(Embedding).join(
        KnowledgeBase,
        Embedding.doc_id == KnowledgeBase.id
    ).filter(
        Embedding.id == embedding_id,
        KnowledgeBase.user_id == user["user_id"],
    ).first()

    if not embedding:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_response(embedding)
```

**After (✓ using repository):**
```python
# app/api/embeddings.py
from app.repositories import EmbeddingRepository

@router.get("/{embedding_id}")
async def get_embedding(embedding_id: str, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = EmbeddingRepository(db)
    embedding = repo.get_by_id(embedding_id, user["user_id"])

    if not embedding:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_response(embedding)
```

**Key points:**
- Instantiate the repository at the start of each endpoint: `repo = EmbeddingRepository(db)`
- Call repository methods to fetch data, not direct `db.query()` calls
- Endpoints handle **only** HTTP concerns: status codes, response formatting, auth
- All query logic (joins, filters, soft-deletes) lives in the repository

**5. Run Tests**
```bash
pytest tests/unit/test_repositories.py -v  # Repository tests
pytest tests/unit/test_embeddings.py -v     # API endpoint tests
pytest tests/unit/ --cov                    # Full coverage report
```

## Query Logic Patterns

**User Isolation (Required)**
```python
# Always filter by user_id to prevent cross-tenant data leaks
def get_by_id(self, embedding_id: str, user_id: str) -> Embedding | None:
    return self.db.query(Embedding).join(
        KnowledgeBase,
        Embedding.doc_id == KnowledgeBase.id
    ).filter(
        Embedding.id == embedding_id,
        KnowledgeBase.user_id == user_id,  # ✓ Ownership check
    ).first()
```

**Soft-Delete Filtering (Default)**
```python
# Exclude soft-deleted records by default
def search_by_user(self, user_id: str) -> list[Embedding]:
    return self.db.query(Embedding).join(
        KnowledgeBase,
        Embedding.doc_id == KnowledgeBase.id
    ).filter(
        KnowledgeBase.user_id == user_id,
        Embedding.deleted_at.is_(None),  # ✓ Exclude soft-deleted
    ).all()
```

**Ownership Check Then Soft-Delete (For Modifications)**
```python
# Check ownership first, then check if already soft-deleted
def update(self, embedding_id: str, user_id: str, metadata: dict) -> None:
    embedding = self.get_by_id(embedding_id, user_id)  # ✓ Ownership check
    if embedding and embedding.deleted_at is None:      # ✓ Not soft-deleted
        embedding.embed_metadata = metadata
        self.db.commit()
```

## Code Review Checklist for Repositories

- [ ] Repository has no FastAPI imports (is pure data access)
- [ ] Repository methods take `db: Session` in constructor via `__init__`
- [ ] All methods return ORM models or None (never DTOs or JSON)
- [ ] All queries filter by `user_id` to ensure user isolation
- [ ] Soft-deleted records are excluded by default (unless method explicitly includes them)
- [ ] Method docstrings explain *what* is returned and any ownership/filtering behavior
- [ ] Repository is unit-tested in `tests/unit/test_repositories.py`
- [ ] API endpoints import from the repository, not direct `db.query()` calls
- [ ] No duplicate query logic across endpoints (all consolidated in repository)
- [ ] Endpoints handle only HTTP concerns (auth, status codes, response formatting)
