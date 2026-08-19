# Adding Backend Services

This is the canonical worked example for creating a backend service. Follow this pattern exactly — new services should look like this one, not invent a new shape.

Governing standards live in [AGENTS.md](../AGENTS.md); this doc is the how-to.

**Business logic should live in the service layer (`app/services/`), not in API endpoints.** Services isolate reusable logic, enable testing without HTTP/FastAPI concerns, and prevent inter-API coupling.

## When to Create a Service

Create a service when:
- Logic is used by **more than one API endpoint**
- Logic is **independent of HTTP concerns** (request/response handling)
- Logic should be **unit-testable in isolation** (no FastAPI mocking needed)
- Logic is a **distinct responsibility** that could live in another context (e.g., embedding generation, search, validation)

Do NOT create a service for:
- Simple DTO conversions (leave in the endpoint)
- Single-use endpoint logic (keep in the endpoint until it's needed elsewhere)
- HTTP concerns (auth, headers, status codes—these belong in endpoints)

## Pattern: Create a Service

**1. Write a Failing Test First (TDD)**
```python
# tests/unit/test_embedding_service.py
from app.services import generate_embedding

def test_generate_embedding_deterministic():
    """Test: Same text always produces same embedding."""
    text = "Hello world"
    emb1 = generate_embedding(text)
    emb2 = generate_embedding(text)
    assert emb1 == emb2

def test_generate_embedding_different_texts():
    """Test: Different texts produce different embeddings."""
    emb1 = generate_embedding("Text A")
    emb2 = generate_embedding("Text B")
    assert emb1 != emb2
```

**2. Create the Service Module**
```python
# app/services/embedding_service.py
"""Service for embedding generation and management."""

import random


def generate_embedding(text: str) -> list[float]:
    """Generate a deterministic mock embedding from text.

    For MVP, we use a simple hash-based approach that's deterministic
    so the same text always produces the same embedding.

    Args:
        text: The text to generate an embedding for.

    Returns:
        A list of 1536 floating point values representing the embedding.
    """
    random.seed(hash(text) % (2**32))
    return [random.gauss(0, 0.1) for _ in range(1536)]
```

**Key design principles:**
- **No FastAPI imports** — Services are business logic, not HTTP handlers
- **Pure functions where possible** — Deterministic, testable, no side effects
- **Clear type hints** — Use Python 3.9+ style (`list[float]` not `List[float]`)
- **Docstring for public API** — Explain *what* and *why*, not implementation details
- **One responsibility per function** — A service function should do one thing well

**3. Export from Services `__init__.py`**
```python
# app/services/__init__.py
"""Backend service layer for business logic."""

from app.services.embedding_service import generate_embedding

__all__ = ["generate_embedding"]
```

**4. Update API Endpoints to Use the Service**
```python
# app/api/embeddings.py
from app.services import generate_embedding

@router.post("/search")
async def search_embeddings(payload: SemanticSearchRequest, ...):
    """Perform semantic search."""
    # Use the service
    query_embedding = generate_embedding(payload.query_text)
    # ... rest of logic
```

**5. Update Any Other Endpoints Using This Logic**
```python
# app/api/knowledge_base.py
from app.services import generate_embedding

@router.post("")
async def create_knowledge_base(payload: KnowledgeBaseCreate, ...):
    """Create knowledge base with auto-generated embeddings."""
    # Use the service
    embedding_vector = generate_embedding(payload.content)
    # ... rest of logic
```

**6. Remove the Old Implementation**
- Delete the old function from the API module (e.g., `_generate_mock_embedding` from knowledge_base.py)
- Update any tests that imported the old function to use the service instead

**7. Run Tests**
```bash
pytest tests/unit/ -v
```

All tests must pass, including:
- New service tests
- Existing API endpoint tests
- Any other tests that use this logic

## Example: Refactoring Existing Code to a Service

**Before (coupled):**
```python
# app/api/embeddings.py
from app.api.knowledge_base import _generate_mock_embedding  # ❌ Inter-API import

query_embedding = _generate_mock_embedding(payload.query_text)
```

**After (decoupled):**
```python
# app/api/embeddings.py
from app.services import generate_embedding  # ✓ Service import

query_embedding = generate_embedding(payload.query_text)
```

And:
```python
# app/api/knowledge_base.py
from app.services import generate_embedding  # ✓ Service import

embedding_vector = generate_embedding(payload.content)
```

Result: No inter-API imports, reusable logic, easier to test.

## Code Review Checklist for Services

- [ ] Service has no FastAPI imports (is pure business logic)
- [ ] Service functions have clear, descriptive names and docstrings
- [ ] All functions are unit-tested independently (no mocking of HTTP/database at this level)
- [ ] Type hints are present and accurate (Python 3.9+ style)
- [ ] No mutable global state or side effects (where possible)
- [ ] Service is exported from `app/services/__init__.py`
- [ ] All API endpoints using this logic import from the service, not from each other
- [ ] No inter-API imports remain (check with: `grep -r "from app.api.X import" app/api/Y.py`)
