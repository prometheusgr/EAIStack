# Clean Architecture Review — 19 August 2026

**Scope:** Layer boundaries, dependency direction, and duplication across backend and frontend.
**Baseline at review time:** 99 backend unit tests passing, 77 frontend tests passing (2 skipped). Every task below must preserve that.

This review supersedes the layering sections of `ARCHITECTURE_REVIEW.md` (18 Aug 2026), whose headline recommendation — extract `generate_embedding` into a service — has since been implemented.

---

## Summary of findings

| # | Finding | Layer | Severity |
|---|---------|-------|----------|
| 1 | Two parallel implementations of each API client, with different auth mechanisms | Frontend | **High** |
| 2 | `EmbeddingDetail` reads auth from `localStorage`, bypassing `AuthContext` | Frontend | **High** |
| 3 | `knowledge_base.py` holds raw ORM queries while sibling routers use repositories | Backend | **High** |
| 4 | Similarity scoring — the core domain logic — lives in an HTTP handler | Backend | **Medium** |
| 5 | Four fully-written but unreferenced modules | Frontend | **Medium** |
| 6 | Components reach past the hook layer at three different depths | Frontend | **Medium** |
| 7 | `search_similar` issues N+1 queries and returns data the caller re-derives | Backend | **Medium** |
| 8 | Module-level agent singleton in the router | Backend | **Low** |
| 9 | Repository write methods commit their own transactions | Backend | **Low** |
| 10 | 24 markdown files at repo root and in test directories | Docs | **Low** |

Findings 1, 2, 5, and 6 are one connected problem: the frontend has two half-finished migrations layered on top of each other. Tasks A–C below should go to a single agent, in order. The rest are independent.

---

## Finding 1 — Duplicate API clients with divergent auth (High)

`src/api/embeddingsClient.ts` and `src/services/embeddingsClient.ts` both export a const named `embeddingsClient` implementing an interface named `EmbeddingsClient`. Same for `knowledgeBaseClient` in both directories. They are not thin variants of each other — they differ in how they authenticate:

- **`src/api/*`** — takes `token` as an explicit parameter, defines a private local `authorizedFetch` with no 401-refresh handling.
- **`src/services/*`** — reads the token from `localStorage` directly, and uses the shared `@/api/authorizedFetch`, which *does* retry on 401.

So the same feature has two auth paths with different session-expiry behavior, selected by which file a component happened to import. `useEmbeddingsService` imports the `api/` copy; `EmbeddingDetail` imports the `services/` copy.

Note that AGENTS.md's own convention places API clients in `src/api/` and *services* (classes wrapping clients) in `src/services/`. The `services/*Client.ts` files violate that naming on top of duplicating the logic.

## Finding 2 — `localStorage` auth bypass (High)

`src/services/embeddingsClient.ts:12-18` and `src/services/knowledgeBaseClient.ts:13-19` read `localStorage.getItem('access_token')` at call time. `src/api/apiKeysClient.ts:29-35` does the same. This bypasses `AuthContext`, which is the single owner of token lifecycle.

Consequences: the component cannot react to token state, tests must stub `localStorage` rather than the auth provider, and the `getRefreshFn()` in these files dispatches a `CustomEvent('auth-refresh-needed')` and then unconditionally returns `true` — claiming a refresh succeeded without waiting for one. `authorizedFetch` then re-reads `localStorage` hoping a listener updated it in the interim. That is a race, not a refresh.

## Finding 3 — Repository pattern applied to two of three routers (High)

`apikeys.py` and `embeddings.py` route all data access through repositories. `knowledge_base.py` does not — it builds `db.query(KnowledgeBase).filter(...)` inline in all five handlers ([knowledge_base.py:73-81](backend/app/api/knowledge_base.py#L73-L81), [:92-99](backend/app/api/knowledge_base.py#L92-L99), [:115-122](backend/app/api/knowledge_base.py#L115-L122), [:134-141](backend/app/api/knowledge_base.py#L134-L141), [:159-166](backend/app/api/knowledge_base.py#L159-L166)).

The ownership filter `KnowledgeBase.user_id == user["user_id"]` is hand-repeated four times; the soft-delete filter `deleted_at.is_(None)` is applied in `list` but **not** in `get`, `update`, or `delete`. A soft-deleted entry is therefore still fetchable and editable by ID — a real inconsistency that a repository would have made structural rather than a per-handler decision.

## Finding 4 — Domain logic in the HTTP layer (Medium)

[embeddings.py:48-76](backend/app/api/embeddings.py#L48-L76) computes dot-product similarity, clamps negatives, builds content previews, sorts, and truncates to `top_k` — inside the route handler. This is the substance of semantic search, and it is the one piece of backend logic most likely to change in Phase 3 when real embeddings and pgvector operators replace the mock. It is currently untestable without going through FastAPI.

Note also that `similarity_score` is a raw dot product of two unnormalized Gaussian vectors, so it is not bounded to `[0,1]`; `max(0, similarity)` clamps only the low end. Worth confirming the frontend `SimilarityScore` component's assumptions when this moves.

## Finding 5 — Dead modules (Medium)

Written, exported, never imported anywhere in `src/` or `tests/`:

- `src/services/apiKeyService.ts` — `APIKeyService`, 98 lines
- `src/services/embeddingsService.ts` — `EmbeddingsService`, 26 lines
- `src/services/chatService.ts` — `ChatService`, 42 lines (duplicates `sendChatMessage` in `api/agentsClient.ts`)
- `src/api/client.ts` — `apiCall<T>` + `ApiErrorImpl`, 66 lines
- `src/api/apiKeysClient.ts:154` — `getAPIKeyDetail`, unused export

`api/client.ts` is the most interesting loss: it is the only place with structured error handling that parses `detail` out of a JSON error body into a typed `ApiError`. Every live client throws bare `new Error(response.statusText)`, discarding the backend's error detail. The good pattern is the one that got abandoned.

## Finding 6 — Inconsistent component access depth (Medium)

Three different depths in one feature folder:

- `EmbeddingsList` / `EmbeddingsSearch` → `useEmbeddingsService()` hook ✅ matches AGENTS.md
- `KnowledgeBaseUpload` → instantiates `new KnowledgeBaseService(token)` directly, managing its own `loading`/`error` state
- `EmbeddingDetail` → imports a client module directly, managing its own `loading`/`error`/`deleteError` state
- `APIKeys` → imports React Query hooks from `api/apiKeysClient.ts`, a fourth pattern (React Query is used *only* here)

## Finding 7 — N+1 in `search_similar` (Medium)

[embedding_repository.py:38-54](backend/app/repositories/embedding_repository.py#L38-L54) joins `KnowledgeBase` to filter, discards the joined row, then issues one additional `SELECT` per embedding to fetch the same `KnowledgeBase` it already had. The join should select both entities.

The same shape appears in [embeddings.py:88-91](backend/app/api/embeddings.py#L88-L91): `list_embeddings` calls `get_knowledge_base_for_embedding` per row, and that method itself performs two queries — so listing N embeddings costs 2N+1 round trips.

## Finding 8 — Agent singleton at import time (Low)

[agents.py:13](backend/app/api/agents.py#L13) — `_agent = create_chat_agent()` runs at module import. Importing the router compiles a graph, which will bind a real LLM client once `llm_provider` is not `fake`. Prefer a `Depends`-provided factory with `lru_cache`, consistent with `get_db` / `get_current_user`.

## Finding 9 — Repositories own transaction boundaries (Low)

`APIKeyRepository.create/update/revoke` and `EmbeddingRepository.update_metadata/soft_delete` each call `self.db.commit()`. The caller cannot compose two repository operations into one transaction — relevant for Finding 3, where deleting a knowledge base must also soft-delete its embeddings atomically. Also, both `EmbeddingRepository` write methods import `datetime` inside the function body (lines 82, 93) rather than at module scope.

## Finding 10 — Documentation sprawl (Low)

24 markdown files, ~180KB. Seven at repo root, four inside `frontend/tests/unit/`. Several are point-in-time debugging narratives (`AUTHENTICATION_FIX_COMPLETE.md`, `LOGOUT_INVESTIGATION.md`, `FRESH_INSTANCE_FIX.md`, `LOGOUT_SESSION_DIAGNOSTICS.md`) whose content is now history, not guidance. `AGENTS.md` alone is 49KB — larger than the backend application code it governs.

---

## What is working well

Worth stating so it isn't refactored away:

- **The LLM boundary is clean.** `get_llm_client()` is the single seam, and tests mock exactly there. `FakeChatModel` is a real `LLM` subclass, not a stub object.
- **API schemas are properly separated from ORM models.** No SQLAlchemy model leaks into a response.
- **Dependency injection is used consistently** for `db` and `user` — no global session or request-context smuggling.
- **JWKS caching with kid-miss invalidation** ([auth.py:71-93](backend/app/core/auth.py#L71-L93)) correctly handles Keycloak key rotation, which is easy to get wrong.
- **`useApiCall` / `useApiMutation`** are a sound generic foundation. The problem is inconsistent adoption, not the abstraction.
