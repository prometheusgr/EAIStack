# Architecture Improvement Opportunities

**Generated:** August 18, 2026  
**Based on:** Architecture Review (see `docs/archive/ARCHITECTURE_REVIEW.md` or current review in `ARCHITECTURE_REVIEW_2026-08-19.md`)

---

## Overview

This document summarizes the key opportunities to improve EAIStack's architecture. These are **straightforward refactorings** that reduce coupling, improve testability, and prepare the system for Phase 3+ development.

**Priority Levels:**
- 🔴 **HIGH** — Complete before Phase 3 real LLM integration
- 🟡 **MEDIUM** — Complete before Phase 4+ production scaling
- 🟢 **LOW** — Quality-of-life improvements, can wait

---

## 1. 🔴 Backend: Extract Service Layer

**Current Issue:**
```python
# backend/app/api/embeddings.py (line 39)
from app.api.knowledge_base import _generate_mock_embedding
query_embedding = _generate_mock_embedding(payload.query_text)
```

This creates an inter-API dependency that violates single responsibility.

**Solution:**
Create `backend/app/services/embedding_service.py`:
```python
def generate_embedding(text: str) -> list[float]:
    """Generate mock embedding for text (Phase 3: real embedding model)."""
    # Move logic from knowledge_base._generate_mock_embedding()
```

**Benefits:**
- ✅ Eliminates cross-API coupling
- ✅ Makes it easy to swap embedding generators (Phase 3+)
- ✅ Service is mockable in tests

**Files to Create:**
- `backend/app/services/__init__.py`
- `backend/app/services/embedding_service.py`

**Files to Update:**
- `backend/app/api/embeddings.py` — import from service
- `backend/app/api/knowledge_base.py` — import from service if needed

**Estimated Effort:** 1-2 hours

**Related Issue:** See `/docs/IMPROVEMENT_OPPORTUNITIES.md#5-green-module-level-global-state`

---

## 2. 🔴 Backend: Implement Repository Pattern

**Current Issue:**
Database queries are embedded in API route handlers:
```python
# backend/app/api/embeddings.py (lines 45-51)
embeddings = db.query(Embedding).join(
    KnowledgeBase,
    Embedding.doc_id == KnowledgeBase.id
).filter(
    KnowledgeBase.user_id == user["user_id"],
    Embedding.deleted_at.is_(None),
).all()
```

This couples the HTTP layer to the data access layer.

**Solution:**
Create repository classes to abstract queries:

```python
# backend/app/repositories/embedding_repository.py
class EmbeddingRepository:
    def __init__(self, db: Session):
        self.db = db

    def search_by_user(self, user_id: str) -> list[Embedding]:
        return self.db.query(Embedding).join(...).filter(...)

    def search_similar(self, user_id: str, query_embedding: list[float]) 
        -> list[tuple[Embedding, float]]:
        # Similarity search logic
```

Then in the API:
```python
# backend/app/api/embeddings.py
repo = EmbeddingRepository(db)
embeddings = repo.search_by_user(user["user_id"])
```

**Benefits:**
- ✅ Separates HTTP concerns from data access
- ✅ Easy to test repositories with mock DB
- ✅ Reuses query logic across endpoints
- ✅ Follows SOLID principles

**Files to Create:**
- `backend/app/repositories/__init__.py`
- `backend/app/repositories/embedding_repository.py`
- `backend/app/repositories/api_key_repository.py`

**Files to Update:**
- `backend/app/api/embeddings.py`
- `backend/app/api/apikeys.py`
- `backend/app/api/knowledge_base.py`

**Estimated Effort:** 2-3 hours

---

## 3. 🔴 Frontend: Build Service Layer & API Clients

**Current Issue:**
API calls and business logic are scattered in components:
```typescript
// frontend/src/components/ChatWindow.tsx
const response = await sendChatMessage(message, currentThreadId, token, refreshAccessToken);
```

This makes code hard to reuse and test.

**Solution:**
Create a layered structure:

```
frontend/src/
  api/              ← HTTP clients (low-level)
    agentsClient.ts      — POST /api/agents/chat
    embeddingsClient.ts  — embeddings endpoints
    apiKeysClient.ts     — API key endpoints
  services/         ← Business logic (high-level, uses API clients)
    chatService.ts       — chat operations
    embeddingsService.ts — embedding operations
    apiKeyService.ts     — API key operations
  hooks/            ← React hooks (state + services)
    useChatService.ts
    useEmbeddingsService.ts
```

**Example API Client:**
```typescript
// frontend/src/api/agentsClient.ts
export async function sendChatMessage(
  request: ChatRequest,
  token: string
): Promise<ChatResponse> {
  const response = await fetch('http://localhost:8001/api/agents/chat', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
```

**Example Service:**
```typescript
// frontend/src/services/chatService.ts
export class ChatService {
  constructor(private token: string) {}
  
  async sendMessage(message: string, threadId?: string): Promise<ChatResponse> {
    return sendChatMessage({ message, thread_id: threadId }, this.token);
  }
}
```

**Example Hook:**
```typescript
// frontend/src/hooks/useChatService.ts
export function useChatService() {
  const { token } = useAuth();
  return useApiMutation(
    (args: { message: string; threadId?: string }) =>
      new ChatService(token).sendMessage(args.message, args.threadId)
  );
}
```

**Benefits:**
- ✅ Eliminates scattered fetch calls
- ✅ Easy to mock services in tests
- ✅ Reusable across components
- ✅ Centralized auth header injection

**Files to Create:**
- `frontend/src/api/client.ts` — Base HTTP client
- `frontend/src/api/agentsClient.ts`
- `frontend/src/api/embeddingsClient.ts`
- `frontend/src/api/apiKeysClient.ts`
- `frontend/src/services/chatService.ts`
- `frontend/src/services/embeddingsService.ts`
- `frontend/src/services/apiKeyService.ts`

**Files to Update:**
- `frontend/src/components/ChatWindow.tsx`
- `frontend/src/components/embeddings/EmbeddingsSearch.tsx`
- `frontend/src/components/embeddings/EmbeddingsList.tsx`
- `frontend/src/components/APIKeys.tsx`

**Estimated Effort:** 3-4 hours

---

## 4. 🔴 Frontend: Add Custom Hooks for Reuse

**Current Issue:**
Components repeat similar patterns:
- Loading state management
- Error state management
- API call execution

```typescript
// frontend/src/components/ChatWindow.tsx
const [isLoading, setIsLoading] = useState(false);
const [error, setError] = useState<string | null>(null);

const handleSend = async () => {
  setIsLoading(true);
  try {
    const response = await sendChatMessage(...);
    // ...
  } catch (err) {
    setError(err.message);
  } finally {
    setIsLoading(false);
  }
};

// Similar pattern in EmbeddingsSearch, APIKeys, etc.
```

**Solution:**
Extract patterns into reusable hooks:

```typescript
// frontend/src/hooks/useApiCall.ts
export function useApiCall<T>(
  apiFn: () => Promise<T>,
  options?: { onError?: (error: Error) => void }
): { data: T | null; error: Error | null; isLoading: boolean; execute: () => Promise<T | null> } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const execute = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await apiFn();
      setData(result);
      return result;
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      options?.onError?.(error);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [apiFn, options]);

  return { data, error, isLoading, execute };
}
```

```typescript
// frontend/src/hooks/useApiMutation.ts
export function useApiMutation<T, R>(
  mutateFn: (args: T) => Promise<R>,
  options?: { onSuccess?: (data: R) => void; onError?: (error: Error) => void }
): {
  mutate: (args: T) => Promise<void>;
  isPending: boolean;
  error: Error | null;
  data: R | null;
} {
  // Implementation...
}
```

Then use in components:
```typescript
// frontend/src/components/ChatWindow.tsx (simplified)
const { mutate: sendMessage, isPending, error, data } = useChatService();

const handleSend = async (message: string) => {
  const response = await sendMessage({ message });
  if (response) {
    setMessages(prev => [...prev, { role: 'agent', text: response.response }]);
  }
};
```

**Benefits:**
- ✅ 30-50% reduction in component size
- ✅ Consistent error/loading handling
- ✅ Easy to test hooks in isolation
- ✅ Reusable across all components

**Files to Create:**
- `frontend/src/hooks/useApiCall.ts`
- `frontend/src/hooks/useApiMutation.ts`
- `frontend/src/hooks/useChatService.ts`
- `frontend/src/hooks/useEmbeddingsService.ts`
- `frontend/src/hooks/useAPIKeyService.ts`
- `frontend/src/hooks/index.ts` (exports)

**Files to Update:**
- All component files that make API calls

**Estimated Effort:** 2-3 hours

---

## 5. 🟡 Backend: Add Alembic Database Migrations

**Current Issue:**
Schema is created at runtime:
```python
# backend/app/main.py (lines 27-30)
with engine.begin() as conn:
    conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
Base.metadata.create_all(bind=engine)
```

This is not production-ready.

**Solution:**
Implement Alembic for schema versioning:

1. Install Alembic:
   ```bash
   cd backend
   pip install alembic
   alembic init alembic
   ```

2. Configure `backend/alembic/env.py` to use EAIStack database settings

3. Create initial migration:
   ```bash
   alembic revision --autogenerate -m "Initial schema with embeddings"
   ```

4. Apply migrations in production:
   ```bash
   alembic upgrade head
   ```

5. Update `backend/app/main.py`:
   ```python
   # Schema is managed by Alembic migrations
   # Run: alembic upgrade head
   ```

**Benefits:**
- ✅ Schema history is tracked in git
- ✅ Rollback capability
- ✅ Production-ready deployments
- ✅ Enables schema evolution without downtime

**Files to Create:**
- `backend/alembic/` directory (auto-generated)
- `backend/alembic/versions/xxx_initial_schema.py` (auto-generated)

**Files to Update:**
- `backend/alembic/env.py` — configure for EAIStack
- `backend/alembic.ini` — database URL
- `backend/app/main.py` — remove runtime schema creation
- `CLAUDE.md` — document migration workflow

**Estimated Effort:** 1-2 hours

---

## 6. 🟢 Backend: Wrap Module-Level Global State

**Current Issue:**
Auth caching uses module-level globals (hard to track scope):
```python
# backend/app/core/auth.py (lines 15-17)
_jwks_cache: dict | None = None
_jwks_cache_expiry: float = 0.0
_JWKS_CACHE_TTL: int = 600
```

**Solution:**
Wrap in a class for clarity:
```python
class JWKSCache:
    def __init__(self, ttl: int = 600):
        self.cache = None
        self.expiry = 0.0
        self.ttl = ttl

    def get(self) -> dict | None:
        current_time = time.monotonic()
        if self.cache is not None and current_time < self.expiry:
            return self.cache
        return None

    def set(self, jwks: dict) -> None:
        self.cache = jwks
        self.expiry = time.monotonic() + self.ttl

    def invalidate(self) -> None:
        self.cache = None
        self.expiry = 0.0

_jwks_cache = JWKSCache()
```

**Benefits:**
- ✅ Clearer scope and intent
- ✅ Easier to test
- ✅ No hidden state in module
- ✅ Easier to extend (add metrics, logging, etc.)

**Estimated Effort:** 30-45 minutes

---

## Summary: Recommended Implementation Order

### Phase 2 Completion (Before Phase 3)

1. **Backend Service Layer** (1-2 hrs) — Quick win, foundation for Phase 3
2. **Backend Repository Pattern** (2-3 hrs) — Builds on service layer
3. **Frontend Service Layer** (3-4 hrs) — Parallelize with repos after core stabilizes
4. **Frontend Custom Hooks** (2-3 hrs) — Parallelize with services

### Phase 3 Preparation

5. **Alembic Migrations** (1-2 hrs) — Before real LLM integration

### Phase 4+

6. **Global State Wrapping** (30-45 mins) — Nice-to-have quality improvement

**Total Estimated Effort:** 10-15 hours

---

## Implementation Checklist

Each improvement opportunity has an associated agent prompt (see `docs/AGENT_PROMPTS.md`). 

Use this checklist to track progress:

- [ ] Prompt 1: Extract Backend Service Layer
- [ ] Prompt 2: Implement Backend Repository Pattern
- [ ] Prompt 3: Build Frontend Service Layer & API Clients
- [ ] Prompt 4: Add Frontend Custom Hooks
- [ ] Prompt 5: Implement Alembic Migrations
- [ ] Prompt 6 (Optional): Wrap Module-Level Global State

---

## Benefits After Completion

✅ **Reduced Coupling:** Cross-API dependencies eliminated
✅ **Improved Testability:** Services and repositories are mockable
✅ **Better Code Reuse:** Shared logic in services and hooks
✅ **Production Ready:** Alembic migrations for safe deployments
✅ **Smaller Components:** Frontend components 30-50% smaller
✅ **Clearer Intent:** Explicit layer separation

---

## Related Documents

- `ARCHITECTURE_REVIEW_2026-08-19.md` — Full architecture assessment (current)
- `docs/archive/ARCHITECTURE_REVIEW.md` — Previous review (superseded, archived)
- `AGENT_PROMPTS.md` — Copy/paste prompts for individual agents

