# Archived: Delegation Prompts for the 2026-08-19 Architecture Review

**Archived, historical document — not a live prompt library.** These are copy/paste prompts written to delegate five specific refactors identified by `ARCHITECTURE_REVIEW_2026-08-19.md` (service layer extraction, repository pattern, frontend service/hooks layers, Alembic migrations) to separate coding-agent sessions. All five tasks are complete and are now documented as standing project conventions in [docs/BACKEND_SERVICES.md](../BACKEND_SERVICES.md), [docs/REPOSITORY_PATTERN.md](../REPOSITORY_PATTERN.md), and [docs/FRONTEND_ARCHITECTURE.md](../FRONTEND_ARCHITECTURE.md) — read those instead for the current pattern.

This file is kept only for historical record of how that one review's backlog was delegated. It has no relationship to the LLM's own system/agent prompts — for that, see `backend/app/prompts/` (the prompt library) and [docs/AGENT_LIBRARY.md](../AGENT_LIBRARY.md) (the agent-scaffolding pattern), introduced in Phase 4.

These prompts were designed to be copy/pasted directly into separate agent invocations. Each prompt is self-contained and includes all necessary context.

---

## Prompt 1: Extract Backend Service Layer

**Copy/paste this entire prompt to an Agent:**

```
You are working on the EAIStack enterprise AI application (FastAPI backend + React frontend). 
Your task is to extract the backend service layer to reduce coupling between API endpoints.

CONTEXT:
- The codebase is in `backend/` and `frontend/` directories
- Currently, `backend/app/api/embeddings.py` imports directly from `backend/app/api/knowledge_base.py`:
  ```python
  from app.api.knowledge_base import _generate_mock_embedding
  query_embedding = _generate_mock_embedding(payload.query_text)
  ```
- This creates an inter-API dependency that violates single responsibility

TASK:
1. Create `backend/app/services/embedding_service.py` with a clean public API:
   - Function: `generate_embedding(text: str) -> list[float]`
   - Move the mock embedding generation logic from `knowledge_base.py` into this service
   - Import only what you need (no circular dependencies)

2. Update `backend/app/api/embeddings.py`:
   - Remove the import from `knowledge_base.py`
   - Import from the new service: `from app.services.embedding_service import generate_embedding`
   - Replace the call to `_generate_mock_embedding()` with `generate_embedding()`

3. Update `backend/app/api/knowledge_base.py`:
   - If it also uses embedding generation, import from the service instead
   - Keep only knowledge base-specific logic

4. Create or update `backend/app/services/__init__.py` to export the service

5. Run tests to verify nothing broke:
   ```bash
   pytest backend/tests/unit/ -v
   ```

CONSTRAINTS:
- No changes to test files or test infrastructure
- Service should have a docstring explaining its purpose
- Use the same type hints as the rest of the codebase (Python 3.9+ style hints)
- The service should have no FastAPI dependencies (it's business logic, not HTTP)

DONE CRITERIA:
- `embedding_service.py` exists and exports `generate_embedding()`
- Both `embeddings.py` and `knowledge_base.py` use the service (no circular imports)
- All unit tests still pass
- No imports from one API module to another (cross-API coupling eliminated)
```

---

## Prompt 2: Implement Backend Repository Pattern

**Copy/paste this entire prompt to an Agent:**

```
You are working on the EAIStack enterprise AI application. Your task is to implement the Repository Pattern 
to isolate database queries from API endpoints.

CONTEXT:
- EAIStack uses SQLAlchemy ORM with PostgreSQL
- Currently, database queries are embedded in API route handlers (e.g., `backend/app/api/embeddings.py`, `backend/app/api/apikeys.py`)
- Example of what we're fixing:
  ```python
  # backend/app/api/embeddings.py
  embeddings = db.query(Embedding).join(KnowledgeBase, ...).filter(...).all()
  ```
- We want to abstract these into repository classes for testability and reuse

TASK:
1. Create `backend/app/repositories/` directory with `__init__.py`

2. Create `backend/app/repositories/embedding_repository.py`:
   - Class: `EmbeddingRepository`
   - Constructor takes `db: Session`
   - Methods (based on queries in `app/api/embeddings.py`):
     - `search_by_user(user_id: str) -> list[Embedding]` — fetch all user embeddings
     - `search_similar(user_id: str, query_embedding: list[float]) -> list[tuple[Embedding, float]]` — search with similarity scores
     - Each method should contain the SQLAlchemy query logic currently in the API
   - Add docstrings to each method

3. Create `backend/app/repositories/api_key_repository.py`:
   - Class: `APIKeyRepository`
   - Constructor takes `db: Session`
   - Methods (based on queries in `app/api/apikeys.py`):
     - `get_by_user(user_id: str) -> list[APIKey]`
     - `get_by_id(api_key_id: str, user_id: str) -> APIKey | None`
     - `create(user_id: str, name: str, provider: str, secret: str) -> APIKey`
     - `revoke(api_key_id: str) -> None`
     - Any other queries currently in the API
   - Add docstrings to each method

4. Update `backend/app/repositories/__init__.py` to export both repositories

5. Update `backend/app/api/embeddings.py`:
   - Instantiate `EmbeddingRepository(db)` at the start of each endpoint
   - Replace inline queries with repository method calls
   - Keep only API logic (request validation, response formatting, auth)

6. Update `backend/app/api/apikeys.py`:
   - Same pattern: instantiate `APIKeyRepository(db)`, replace queries with method calls

7. Ensure no regressions:
   ```bash
   pytest backend/tests/unit/ -v
   pytest backend/tests/integration/ -v
   ```

CONSTRAINTS:
- Repository methods should NOT import FastAPI or have HTTP knowledge
- Repository methods take primitives (str, int, list) and return ORM models
- No breaking changes to API contracts (responses stay the same)
- Type hints must be clear (e.g., `-> list[APIKey]` not `-> list`)

DONE CRITERIA:
- `backend/app/repositories/embedding_repository.py` exists and works
- `backend/app/repositories/api_key_repository.py` exists and works
- API endpoints use repositories instead of direct queries
- All tests pass (unit and integration)
- Query logic is centralized in repositories (no duplicated queries)
```

---

## Prompt 3: Build Frontend Service Layer & API Clients

**Copy/paste this entire prompt to an Agent:**

```
You are working on the EAIStack React frontend. Your task is to extract API client logic and create a service layer 
to improve code reuse and testability.

CONTEXT:
- Frontend is in `frontend/` directory
- Currently, API calls are scattered in component files (e.g., fetch calls in ChatWindow.tsx)
- We need to centralize API clients and business logic
- Example of what we're fixing:
  ```typescript
  // frontend/src/components/ChatWindow.tsx
  const response = await fetch('http://localhost:8001/api/agents/chat', { ... })
  ```

GOAL:
Create a structured service/API layer:
```
frontend/src/
  api/              ← API clients (low-level HTTP)
    agentsClient.ts
    embeddingsClient.ts
    apiKeysClient.ts
  services/         ← Business logic (high-level, uses API clients)
    chatService.ts
    embeddingsService.ts
    apiKeyService.ts
```

TASK:

1. Create `frontend/src/api/` directory with:

   a. `frontend/src/api/client.ts` — Base API client:
      ```typescript
      export interface ApiError extends Error {
        status: number;
        detail: string;
      }

      export async function apiCall<T>(
        endpoint: string,
        options: RequestInit & { token?: string }
      ): Promise<T> {
        // Implement fetch wrapper that:
        // - Adds Authorization header if token provided
        // - Parses JSON response
        // - Throws ApiError on non-2xx status
        // - Handles auth token refresh on 401
      }
      ```

   b. `frontend/src/api/agentsClient.ts`:
      ```typescript
      export interface ChatRequest {
        message: string;
        thread_id?: string;
      }

      export interface ChatResponse {
        response: string;
        thread_id: string;
      }

      export async function sendChatMessage(
        request: ChatRequest,
        token: string
      ): Promise<ChatResponse> {
        // Extract logic from ChatWindow.tsx
      }
      ```

   c. `frontend/src/api/embeddingsClient.ts`:
      ```typescript
      export async function searchEmbeddings(query: string, token: string) { ... }
      export async function listEmbeddings(token: string) { ... }
      export async function uploadDocument(file: File, token: string) { ... }
      ```

   d. `frontend/src/api/apiKeysClient.ts`:
      ```typescript
      export async function listAPIKeys(token: string) { ... }
      export async function createAPIKey(name: string, provider: string, secret: string, token: string) { ... }
      export async function deleteAPIKey(id: string, token: string) { ... }
      ```

2. Create `frontend/src/services/` directory with:

   a. `frontend/src/services/chatService.ts`:
      ```typescript
      export class ChatService {
        constructor(private token: string) {}
        
        async sendMessage(message: string, threadId?: string): Promise<ChatResponse> {
          // Delegates to agentsClient.sendChatMessage()
        }
      }
      ```

   b. `frontend/src/services/embeddingsService.ts`:
      ```typescript
      export class EmbeddingsService {
        constructor(private token: string) {}
        
        async search(query: string) { ... }
        async list() { ... }
        async upload(file: File) { ... }
      }
      ```

   c. `frontend/src/services/apiKeyService.ts`:
      ```typescript
      export class APIKeyService {
        constructor(private token: string) {}
        
        async list() { ... }
        async create(name: string, provider: string, secret: string) { ... }
        async delete(id: string) { ... }
      }
      ```

3. Update components to use services:

   a. `frontend/src/components/ChatWindow.tsx`:
      - Get token from `useAuth()` hook
      - Create service: `const chatService = new ChatService(token)`
      - Replace fetch calls with: `await chatService.sendMessage(message, threadId)`

   b. `frontend/src/components/APIKeys.tsx`:
      - Same pattern: use `APIKeyService`

   c. `frontend/src/components/embeddings/EmbeddingsSearch.tsx`:
      - Same pattern: use `EmbeddingsService`

4. Type safety:
   - Use TypeScript types from `frontend/src/types/` (existing or create new)
   - Export all request/response types from API clients
   - Components import types from services, not API clients

5. Testing:
   - Services should be easy to mock: `new ChatService(mockToken)`
   - API clients use the base `apiCall()` which can be mocked in tests

CONSTRAINTS:
- API clients are HTTP-only (no business logic)
- Services contain retry logic, error handling, and business rules
- Services take the token in constructor (no importing from context inside service)
- Components remain simple: call service, update state, render
- Use existing auth helper from `frontend/src/auth/authHelpers.ts` where needed

DONE CRITERIA:
- `frontend/src/api/` directory exists with all client files
- `frontend/src/services/` directory exists with all service classes
- Components use services instead of direct fetch calls
- No `fetch()` calls in component files
- All components still work (no functionality changed, just refactored)
- TypeScript compiles without errors
```

---

## Prompt 4: Add Frontend Custom Hooks for Reuse

**Copy/paste this entire prompt to an Agent:**

```
You are working on the EAIStack React frontend. Your task is to extract common patterns into custom hooks 
to reduce code duplication and improve component clarity.

CONTEXT:
- Components like ChatWindow, EmbeddingsList, EmbeddingsSearch share similar patterns:
  - Loading state management
  - Error state management
  - API call execution
- These patterns are repeated across multiple components
- We want to extract them into reusable hooks

TASK:

1. Create `frontend/src/hooks/` directory with:

   a. `frontend/src/hooks/useApiCall.ts`:
      ```typescript
      export interface UseApiCallState<T> {
        data: T | null;
        error: Error | null;
        isLoading: boolean;
      }

      export function useApiCall<T>(
        apiFn: () => Promise<T>,
        options?: { onError?: (error: Error) => void }
      ): UseApiCallState<T> & { execute: () => Promise<T | null> } {
        // Implement hook that:
        // - Manages loading state while apiFn runs
        // - Catches errors and stores in state
        // - Returns { data, error, isLoading, execute }
        // - execute() can be called to retry
      }
      ```

   b. `frontend/src/hooks/useApiMutation.ts`:
      ```typescript
      export function useApiMutation<T, R>(
        mutateFn: (args: T) => Promise<R>,
        options?: { onSuccess?: (data: R) => void; onError?: (error: Error) => void }
      ): {
        mutate: (args: T) => Promise<void>;
        isPending: boolean;
        error: Error | null;
        data: R | null;
      } {
        // Implement hook for POST/PUT/DELETE operations
        // - Takes arguments, executes mutation
        // - Manages loading state
        // - Calls onSuccess/onError callbacks
      }
      ```

   c. `frontend/src/hooks/useChatService.ts`:
      ```typescript
      export function useChatService() {
        const { token } = useAuth();
        
        return useApiMutation(
          async (message: string, threadId?: string) => {
            const service = new ChatService(token);
            return service.sendMessage(message, threadId);
          }
        );
      }
      ```

   d. `frontend/src/hooks/useEmbeddingsService.ts`:
      ```typescript
      export function useEmbeddingsService() {
        const { token } = useAuth();
        
        return {
          search: useApiMutation(
            async (query: string) => {
              const service = new EmbeddingsService(token);
              return service.search(query);
            }
          ),
          list: useApiCall(
            async () => {
              const service = new EmbeddingsService(token);
              return service.list();
            }
          ),
          upload: useApiMutation(
            async (file: File) => {
              const service = new EmbeddingsService(token);
              return service.upload(file);
            }
          ),
        };
      }
      ```

   e. `frontend/src/hooks/useAPIKeyService.ts`:
      ```typescript
      export function useAPIKeyService() {
        const { token } = useAuth();
        
        return {
          list: useApiCall(...),
          create: useApiMutation(...),
          delete: useApiMutation(...),
        };
      }
      ```

2. Update components to use hooks:

   a. `frontend/src/components/ChatWindow.tsx`:
      ```typescript
      export function ChatWindow() {
        const { mutate: sendMessage, isPending, error, data } = useChatService();
        const [messages, setMessages] = useState<ChatMessage[]>([]);
        const [threadId, setThreadId] = useState<string>('');

        const handleSend = async (message: string) => {
          const response = await sendMessage(message, threadId);
          if (response) {
            setThreadId(response.thread_id);
            setMessages(prev => [...prev, { role: 'agent', text: response.response }]);
          }
        };

        return (
          // Render messages, input, loading state, error
          // Much simpler than before!
        );
      }
      ```

   b. `frontend/src/components/embeddings/EmbeddingsList.tsx`:
      ```typescript
      export function EmbeddingsList() {
        const { list: { data: embeddings, isLoading, error } } = useEmbeddingsService();

        // Use embeddings directly, hook handles fetching
      }
      ```

   c. `frontend/src/components/embeddings/EmbeddingsSearch.tsx`:
      ```typescript
      export function EmbeddingsSearch() {
        const { search: { mutate: searchEmbeddings, isPending } } = useEmbeddingsService();

        const handleSearch = async (query: string) => {
          const results = await searchEmbeddings(query);
          // Handle results
        };

        return (
          // Render search form, results, loading state
        );
      }
      ```

   d. `frontend/src/components/APIKeys.tsx`:
      ```typescript
      export function APIKeys() {
        const { list, create, delete: deleteKey } = useAPIKeyService();

        // Use hook methods instead of managing state manually
      }
      ```

3. Create `frontend/src/hooks/index.ts` to export all hooks:
   ```typescript
   export { useApiCall } from './useApiCall';
   export { useApiMutation } from './useApiMutation';
   export { useChatService } from './useChatService';
   export { useEmbeddingsService } from './useEmbeddingsService';
   export { useAPIKeyService } from './useAPIKeyService';
   ```

CONSTRAINTS:
- Hooks should NOT import from API clients directly (use services instead)
- Hooks should be "pure"—they manage state, not render anything
- All hooks must have TypeScript type safety
- Hooks should integrate with existing `useAuth()` from AuthContext
- No breaking changes to component functionality

BENEFITS:
- Components become 30-50% smaller
- Logic is reusable (same hook in multiple components)
- Easy to test (mock the hook)
- Error handling is centralized

DONE CRITERIA:
- `frontend/src/hooks/` directory exists with all hook files
- Components use custom hooks instead of managing state/API calls manually
- All components still work correctly
- TypeScript compiles without errors
- Components are simpler (fewer lines of code per component)
```

---

## Prompt 5: Implement Alembic Database Migrations

**Copy/paste this entire prompt to an Agent:**

```
You are working on the EAIStack backend. Your task is to set up Alembic for database migrations 
to replace runtime schema creation.

CONTEXT:
- Currently, `backend/app/main.py` creates tables at startup:
  ```python
  Base.metadata.create_all(bind=engine)
  ```
- This is fine for development but not production-ready
- We need Alembic to manage schema evolution

CURRENT STATE:
- Database models are in `backend/app/db/models.py`
- Tables include: APIKey, KnowledgeBase, Embedding
- PostgreSQL extensions like `pgvector` are required

TASK:

1. Install Alembic in the backend environment:
   ```bash
   cd backend
   pip install alembic
   ```

2. Initialize Alembic:
   ```bash
   alembic init alembic
   ```
   This creates `backend/alembic/` directory with:
   - `env.py` — Alembic configuration
   - `script.py.mako` — Template for migrations
   - `versions/` — Directory for migration files

3. Configure `backend/alembic/env.py`:
   - Import SQLAlchemy engine from `app.db.database`
   - Configure `sqlalchemy.url` to use `app.core.config.settings.database_url`
   - Set `target_metadata = Base.metadata` (import from `app.db.models`)
   - Enable auto-detection: `compare_type=True, compare_server_default=True`

4. Configure `backend/alembic.ini`:
   - Set `sqlalchemy.url` to use environment variable or config
   - Ensure `version_locations` points to `backend/alembic/versions/`

5. Create initial migration (captures current schema):
   ```bash
   cd backend
   alembic revision --autogenerate -m "Initial schema with embeddings"
   ```
   This creates a migration file in `backend/alembic/versions/`

6. Verify the migration:
   - Read `backend/alembic/versions/xxx_initial_schema.py`
   - Should include:
     - `CREATE EXTENSION vector` (for pgvector)
     - `CREATE TABLE api_keys`
     - `CREATE TABLE knowledge_base`
     - `CREATE TABLE embeddings`
     - Foreign key relationships

7. Update `backend/app/main.py`:
   - Remove the runtime schema creation:
     ```python
     # DELETE THIS:
     with engine.begin() as conn:
         conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
         conn.commit()
     Base.metadata.create_all(bind=engine)
     ```
   - Replace with a comment:
     ```python
     # Schema is managed by Alembic migrations
     # Run: alembic upgrade head
     ```

8. Create a migration runner script for deployment:
   ```bash
   # backend/scripts/migrate.sh
   #!/bin/bash
   cd backend
   alembic upgrade head
   ```
   Make it executable: `chmod +x backend/scripts/migrate.sh`

9. Update documentation:
   - Add to `CLAUDE.md`:
     ```markdown
     ### Database Migrations

     Create a new migration:
     ```bash
     cd backend
     alembic revision --autogenerate -m "Description of change"
     ```

     Apply migrations:
     ```bash
     alembic upgrade head
     ```

     Rollback one migration:
     ```bash
     alembic downgrade -1
     ```
     ```

10. Test the migration workflow:
    ```bash
    cd backend
    
    # Start with a clean database (optional)
    # dropdb eaistack && createdb eaistack
    
    # Run the migration
    alembic upgrade head
    
    # Verify tables exist
    psql -d eaistack -c "\\dt"
    
    # Run tests to ensure nothing broke
    pytest tests/unit/ -v
    ```

MIGRATION FILE CHECKLIST:

The generated migration should:
- [ ] Include `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`
- [ ] Include all table creation operations (api_keys, knowledge_base, embeddings)
- [ ] Include indexes on frequently queried columns (user_id, doc_id)
- [ ] Include foreign key constraints (embeddings → knowledge_base)
- [ ] Include default values and NOT NULL constraints

CONSTRAINTS:
- Don't manually edit the auto-generated migration (let Alembic generate them)
- All future schema changes must go through migrations
- Migrations must be backwards compatible or have a clear rollback path
- Test migrations in a dev database before applying to production

FUTURE WORKFLOW:
Once Alembic is set up, follow this for schema changes:

1. Modify `backend/app/db/models.py` to add/change a field
2. Generate migration: `alembic revision --autogenerate -m "Add user_preference column"`
3. Review the generated migration file
4. Test locally: `alembic upgrade head`
5. Commit both the model change AND the migration file
6. In production deployment, run migrations as part of CI/CD

DONE CRITERIA:
- `backend/alembic/` directory exists with proper configuration
- Initial migration file created and captures current schema
- `backend/app/main.py` no longer creates schema at runtime
- `alembic upgrade head` successfully creates all tables
- `pytest tests/unit/ -v` still passes
- Migration rollback works: `alembic downgrade -1` then `alembic upgrade head`
```

---

## Summary Table

| Prompt # | Task | Scope | Complexity | Est. Time |
|----------|------|-------|-----------|-----------|
| 1 | Extract Backend Service Layer | `app/services/` | Medium | 1-2 hours |
| 2 | Implement Repository Pattern | `app/repositories/` | Medium | 2-3 hours |
| 3 | Build Frontend Service Layer | `frontend/src/{api,services}/` | High | 3-4 hours |
| 4 | Add Frontend Custom Hooks | `frontend/src/hooks/` | High | 2-3 hours |
| 5 | Implement Alembic Migrations | `backend/alembic/` | Medium | 1-2 hours |

**Total estimated effort:** 10-15 hours

**Recommended order:**
1. Start with Prompt 1 (service layer) — quick win, unblocks Prompt 2
2. Then Prompt 2 (repository pattern) — builds on Prompt 1
3. Then Prompt 5 (migrations) — independent, can run in parallel
4. Then Prompts 3 & 4 (frontend) — can run in parallel once backend stabilizes

