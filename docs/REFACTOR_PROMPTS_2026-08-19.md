# Refactor Prompts — Architecture Review, 19 August 2026

Each task below is self-contained and copy-pasteable to a separate agent. Findings referenced are in `ARCHITECTURE_REVIEW_2026-08-19.md`.

**Baseline every task must preserve:** `cd backend && pytest tests/unit/` → 99 passed. `cd frontend && npx vitest run` → 77 passed, 2 skipped.

## Dispatch order

**Tasks A, B, C are sequential and must go to one agent** (or run in strict order) — they touch the same frontend files. A is a prerequisite for B and C.

Everything else is independent and parallelizable:

| Track | Tasks | Can run concurrently? |
|-------|-------|----------------------|
| Frontend consolidation | A → B → C | No — strictly sequential, one agent |
| Backend data access | D → E | Sequential pair, one agent |
| Backend search logic | F | Yes, independent |
| Backend small fixes | G | Yes, independent |
| Docs | H | Yes, independent |

D and F both touch `backend/app/api/embeddings.py`. If you run them in parallel, expect a small merge conflict in the import block — or give both to one agent.

---

## TASK A — Delete duplicate and dead frontend modules

**Prerequisite for B and C. Frontend only.**

```
The frontend has two parallel implementations of each API client plus several
fully-written modules that nothing imports. Consolidate to one implementation
per resource.

Delete these files (verified: zero importers across src/ and tests/):
  frontend/src/services/apiKeyService.ts        (APIKeyService class)
  frontend/src/services/embeddingsService.ts    (EmbeddingsService class)
  frontend/src/services/chatService.ts          (ChatService class - duplicates
                                                 sendChatMessage in api/agentsClient.ts)

Delete this duplicate client, but FIRST see the migration note below:
  frontend/src/services/embeddingsClient.ts     (duplicate of api/embeddingsClient.ts)
  frontend/src/services/knowledgeBaseClient.ts  (duplicate of api/knowledgeBaseClient.ts)

MIGRATION NOTE: frontend/src/components/embeddings/EmbeddingDetail.tsx line 2
imports { embeddingsClient } from '@/services/embeddingsClient'. That is the
ONLY importer of either services/*Client.ts file. Task B rewrites that component.
So: do Task B's component rewrite in the same pass, or leave EmbeddingDetail.tsx
temporarily importing from '@/api/embeddingsClient' and adjust the call sites to
pass a token (the api/ variant takes token as an explicit last parameter, the
services/ variant reads localStorage). Do not leave the build broken.

Also delete the unused export getAPIKeyDetail (frontend/src/api/apiKeysClient.ts
line 154) - nothing calls it.

DO NOT delete frontend/src/api/client.ts yet. It is currently unused, but it is
the only module with structured error handling (parses `detail` from a JSON error
body into a typed ApiError). Task C decides its fate. Leave it in place.

Keep: frontend/src/services/knowledgeBaseService.ts - it IS used, by
KnowledgeBaseUpload.tsx. Task B deals with it.

After deleting, confirm nothing dangles:
  cd frontend && npx tsc --noEmit && npx vitest run

Expected: 77 passed, 2 skipped. No TypeScript errors.
```

---

## TASK B — Route every component through the hook layer

**Depends on Task A. Frontend only.**

```
Components in frontend/src/ access the API at four different depths. AGENTS.md
specifies exactly one: Components -> Hooks -> API Clients. Bring all of them to
that pattern.

Current state:
  EmbeddingsList.tsx    -> useEmbeddingsService()          CORRECT, leave alone
  EmbeddingsSearch.tsx  -> useEmbeddingsService()          CORRECT, leave alone
  KnowledgeBaseUpload.tsx -> new KnowledgeBaseService(token) directly
  EmbeddingDetail.tsx   -> imports a client module directly
  APIKeys.tsx           -> React Query hooks from api/apiKeysClient.ts

Work required:

1. EmbeddingDetail.tsx
   Add getEmbedding to the useEmbeddingsService() hook (hooks/useEmbeddingsService.ts)
   using useApiCall, following the existing `list` entry as the model. The hook
   already has a `delete` mutation - reuse it rather than adding a second one.
   Rewrite the component to use the hook and drop its hand-rolled loading/error/
   deleteError useState triple. Preserve the existing rendered output exactly:
   the loading skeletons, the role="alert" error div, and the "Embedding not
   found" branch are all asserted against or user-visible.

2. KnowledgeBaseUpload.tsx
   It calls `new KnowledgeBaseService(token)` inside a submit handler. The
   useEmbeddingsService() hook already exposes an `upload` mutation that does the
   same thing via knowledgeBaseClient.create. Switch the component to
   `const { upload } = useEmbeddingsService()` and use upload.isPending in place
   of its local `loading` state. Then delete frontend/src/services/knowledgeBaseService.ts,
   which becomes unused.

3. APIKeys.tsx
   This is the only place in the codebase using @tanstack/react-query. Do NOT
   rewrite it in this task - it works, and converting it is a judgment call about
   whether React Query becomes the project standard or gets dropped. Instead,
   leave the code as-is and add a short note to docs/ARCHITECTURE.md recording
   that API keys use React Query while everything else uses useApiCall/
   useApiMutation, and that this should be unified. Flag it in your summary.

Do not change any component's rendered markup or user-visible behavior. This is
a wiring change only.

Verify: cd frontend && npx tsc --noEmit && npx vitest run
Expected: 77 passed, 2 skipped.
```

---

## TASK C — Make AuthContext the only source of tokens

**Depends on Tasks A and B. Frontend only. Security-relevant.**

```
Several API clients read the auth token straight out of localStorage instead of
going through AuthContext, and their token-refresh logic is a race condition.
Fix both.

Problem 1 - localStorage reads bypassing AuthContext:
  frontend/src/api/apiKeysClient.ts lines 29-35 (getAuthToken)
  (after Task A, the services/*Client.ts copies with the same pattern are gone)

AuthContext owns the token lifecycle. Clients reading localStorage directly
cannot react to auth state, and force tests to stub browser storage instead of
the auth provider. Convert apiKeysClient's React Query hooks to take the token
from useAuth() and pass it into the fetch calls, matching how
useEmbeddingsService does it.

Problem 2 - the refresh callback lies:
  The getRefreshFn() helper (frontend/src/api/apiKeysClient.ts lines 37-43)
  dispatches a CustomEvent('auth-refresh-needed') and then immediately returns
  true - reporting a successful refresh without waiting for one to happen.
  api/authorizedFetch.ts then re-reads localStorage hoping some listener updated
  it in the meantime. That is a race.

  AuthContext already exposes a real refreshAccessToken function that returns a
  genuine success boolean - useChatService.ts uses it correctly. Use that
  instead. Delete the CustomEvent mechanism and grep for any remaining
  'auth-refresh-needed' listeners to remove.

Problem 3 - error detail is discarded:
  Live clients throw `new Error(response.statusText)`, dropping the `detail`
  field the FastAPI backend returns in its error bodies. The unused
  frontend/src/api/client.ts already solves this with apiCall<T> and a typed
  ApiErrorImpl that parses `detail` out of the JSON body.

  Decide one of:
    (a) adopt api/client.ts as the shared fetch layer and route the existing
        clients through it, folding in authorizedFetch's 401-retry, or
    (b) delete api/client.ts and lift just its error-parsing into
        api/authorizedFetch.ts so callers get the backend's detail message.

  (b) is the smaller change and keeps one fetch helper rather than two. Prefer it
  unless you find a reason not to. Either way, the end state is ONE fetch helper
  in the frontend, and users see the backend's actual error text instead of a
  bare HTTP status.

Add a test covering the case the current code gets wrong: a 401 response
triggers a refresh, and when the refresh genuinely fails the original error
propagates rather than being retried into a second failure.

Verify: cd frontend && npx tsc --noEmit && npx vitest run
```

---

## TASK D — Add KnowledgeBaseRepository

**Backend only. Fixes a real ownership/soft-delete bug. TDD required.**

```
backend/app/api/knowledge_base.py is the only router still doing raw ORM queries
in its handlers; apikeys.py and embeddings.py both use repositories. Bring it in
line, following the pattern in backend/app/repositories/embedding_repository.py
and the "Repository Pattern for Data Access" section of AGENTS.md.

THERE IS A REAL BUG TO FIX HERE, not just a layering cleanup:

  list_knowledge_base   filters deleted_at.is_(None)   correct
  get_knowledge_base    does NOT filter deleted_at     BUG
  update_knowledge_base does NOT filter deleted_at     BUG
  delete_knowledge_base does NOT filter deleted_at     BUG

A soft-deleted knowledge base entry is still fetchable and editable by ID. Since
this is a bug fix, AGENTS.md requires the failing-test-first cycle:

  1. Write tests in backend/tests/unit/ asserting that GET, PUT, and DELETE all
     return 404 for a soft-deleted entry. Run them, confirm they FAIL.
  2. Create backend/app/repositories/knowledge_base_repository.py with
     KnowledgeBaseRepository, taking `db: Session` in __init__. Every read method
     filters BOTH user_id (ownership) and deleted_at IS NULL. Cover: get_by_user,
     get_by_id, create, update, soft_delete.
  3. Rewrite the five handlers in knowledge_base.py to call the repository. The
     handlers should retain ONLY HTTP concerns - status codes, the _to_response
     DTO conversion, and HTTPException raising.
  4. Confirm the new tests pass and all 99 existing tests still pass.
  5. Export KnowledgeBaseRepository from backend/app/repositories/__init__.py.

One transactional detail: delete_knowledge_base soft-deletes the entry AND its
embeddings. Those two writes must land in a single transaction - do not split
them across two repository methods that each commit. See Task E, which addresses
commit ownership generally; if you are doing both tasks, do E first.

Also add repository-level tests in backend/tests/unit/test_repositories.py
matching the existing style there.

Verify: cd backend && pytest tests/unit/ -v && ruff check . && black --check .
```

---

## TASK E — Move transaction control out of repositories

**Backend only. Do before Task D if both are assigned to you.**

```
Repository write methods each call self.db.commit() internally:
  backend/app/repositories/api_key_repository.py     create, update, revoke
  backend/app/repositories/embedding_repository.py   update_metadata, soft_delete

This makes it impossible for a caller to compose two repository operations into
one atomic transaction - which Task D needs, since deleting a knowledge base must
also soft-delete its embeddings.

Move commit responsibility to the caller. Repositories should add/modify/flush;
the API handler (or the get_db dependency) commits once at the end of the unit of
work.

Look at backend/app/db/database.py get_db() first - if it can own commit/rollback
per request, that is the cleanest seam and means handlers do not each need an
explicit commit. Use your judgment; if that turns out to be too broad a change,
having handlers commit explicitly is acceptable. State which you chose and why.

Watch for: APIKeyRepository.create currently does commit() then refresh() and
returns a fully-populated object with server defaults applied. Callers depend on
the returned object being usable. db.flush() will populate the primary key
without committing - confirm created_at/updated_at defaults still resolve
correctly, since those are Python-side (default=utc_now) rather than
server_default, so they should be fine.

Also, while in embedding_repository.py: it imports datetime inside two function
bodies (lines 82 and 93). Move that to a module-level import.

This is a refactor with no behavior change, so the existing tests are the
specification - all 99 must still pass, and none should need modification. If a
test needs changing to accommodate this, that is a signal the change altered
behavior; stop and reconsider.

Verify: cd backend && pytest tests/unit/ -v && ruff check . && black --check .
```

---

## TASK F — Extract similarity search into a service

**Backend only. TDD required. Touches embeddings.py — coordinate with Task D.**

```
The core logic of semantic search lives inside an HTTP handler. Move it to the
service layer so it can be unit-tested directly and swapped out in Phase 3.

Current state, backend/app/api/embeddings.py lines 48-76 (search_embeddings):
the handler computes dot-product similarity, clamps negative scores to 0, builds
a 150-char content preview, sorts descending, and truncates to top_k. All of that
is domain logic sitting in a route.

Work required, following AGENTS.md "Adding Backend Services":

  1. Write tests FIRST in backend/tests/unit/ for a new
     app/services/search_service.py. Confirm they fail. Cover at minimum:
       - results come back sorted by descending similarity
       - top_k truncates correctly, and top_k larger than the result count is safe
       - a content shorter than 150 chars gets no "..." suffix; longer content does
       - identical vectors score higher than dissimilar ones
       - an empty candidate list returns an empty result, not an error
  2. Create the service with a function like:
       rank_by_similarity(query_embedding, candidates, top_k) -> list[dict]
     No FastAPI imports. Pure, deterministic, directly testable.
  3. Reduce the handler to: generate query embedding, fetch candidates via the
     repository, call the service, wrap in SemanticSearchResponse.
  4. Export from app/services/__init__.py.

While you are in here, note for your summary (do NOT change behavior in this
task): similarity_score is a raw dot product of two unnormalized Gaussian
vectors, so it is not bounded to [0,1] despite the frontend SimilarityScore
component likely assuming a 0-1 range. max(0, similarity) clamps only the low
end. Flag whether normalizing to cosine similarity should be a follow-up - it
would change scores users see, so it is a product decision, not a refactor.

Verify: cd backend && pytest tests/unit/ -v && ruff check . && black --check .
Expected: 99 existing + your new tests, all passing.
```

---

## TASK G — Fix N+1 queries and the router-level agent singleton

**Backend only. Two small independent fixes.**

```
Fix 1 - N+1 queries in embedding lookups.

backend/app/repositories/embedding_repository.py, search_similar (lines 38-54):
joins KnowledgeBase in order to filter by user, discards the joined row, then
runs one extra SELECT per embedding to fetch the very same KnowledgeBase. Select
both entities from the join instead:

    self.db.query(Embedding, KnowledgeBase).join(...)

The same shape appears in backend/app/api/embeddings.py list_embeddings (lines
88-91), which calls repo.get_knowledge_base_for_embedding() once per row - and
that method itself runs two queries. Listing N embeddings currently costs 2N+1
round trips. Add a repository method returning (Embedding, KnowledgeBase) pairs
in one query and use it there.

get_knowledge_base_for_embedding may become unused once both call sites are
fixed - it is used in three places in embeddings.py (lines 90, 109, 131). Line
109 and 131 are single-row lookups where the N+1 does not apply, so keep the
method if they still need it; just stop calling it in a loop.

This is a performance refactor with no behavior change: all 99 tests must pass
unmodified. Do not change what the endpoints return.

Fix 2 - agent compiled at import time.

backend/app/api/agents.py line 13: `_agent = create_chat_agent()` executes on
module import, so importing the router compiles a LangGraph graph. Once
llm_provider stops being "fake", this binds a real LLM client at import.

Convert to a dependency-injected factory with @lru_cache, consistent with how
get_db and get_current_user are provided, so the graph is built on first request
rather than at import and can be overridden in tests.

Verify: cd backend && pytest tests/unit/ -v && ruff check . && black --check .
```

---

## TASK H — Consolidate documentation

**Docs only. No code changes. Safe to run fully in parallel.**

```
The repo has 24 markdown files totaling ~180KB, including 7 at the root and 4
inside frontend/tests/unit/. Several are point-in-time debugging narratives whose
content is now history rather than guidance, and they compete with the actual
reference docs for attention.

Archive (move to docs/archive/, do not delete - they contain real debugging
context worth keeping):
  AUTHENTICATION_FIX_COMPLETE.md
  LOGOUT_INVESTIGATION.md
  UI_IMPROVEMENTS.md
  frontend/LOGOUT_FIX_SUMMARY.md
  frontend/tests/unit/FRESH_INSTANCE_FIX.md
  frontend/tests/unit/LOGOUT_AND_TOKEN_FIXES.md
  frontend/tests/unit/LOGOUT_SESSION_DIAGNOSTICS.md
  docs/PHASE_2_COMPLETION.md

Before archiving each one, check whether it contains guidance that is still
current and not recorded elsewhere. If so, fold that into the appropriate live
doc (docs/AUTH_TROUBLESHOOTING.md or docs/ARCHITECTURE.md) rather than losing it.
frontend/tests/unit/AUTH_TESTS_README.md in particular may describe how the auth
tests are structured - if that is still accurate, it belongs in the test
directory; leave it.

Then: docs/ARCHITECTURE_REVIEW.md is dated 18 Aug 2026 and its headline
recommendation (extract generate_embedding into a service) has since been
implemented. Add a short header noting it is superseded by
docs/ARCHITECTURE_REVIEW_2026-08-19.md, and archive it.

Finally, AGENTS.md is 49KB - larger than the backend application code it
governs, and it is imported into context on every session via CLAUDE.md. Do NOT
restructure it in this task. Instead, read it and report: which sections are
load-bearing standards versus which are long inline code examples that could
move to docs/ and be linked. Propose a split with rough line counts; do not
execute it.

Update any internal links that break from the moves. Verify no file still links
to a moved doc:
  grep -rn "AUTHENTICATION_FIX_COMPLETE\|LOGOUT_INVESTIGATION\|UI_IMPROVEMENTS\|PHASE_2_COMPLETION\|LOGOUT_FIX_SUMMARY" --include=*.md .
```
