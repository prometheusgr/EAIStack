# Hidden Configuration Audit — September 2026

**Generated:** 2026-09-04
**Trigger:** A question about whether the RAG/embedding pipeline's tuning knobs are admin-configurable surfaced a broader pattern — several operationally-relevant values across the system are hardcoded Python/Pydantic constants instead of following the repo's own established `SystemSettings` pattern (env-default + nullable-DB-override, resolved per-call via a `resolve_*_config` function, exposed on the Settings UI with a tooltip, audit-logged on change — see retention, guardrails, tracing, and rate-limiting for worked examples).

**Purpose of this document:** a single, dated inventory of every such gap found in one sweep, so each item can be triaged into a tracked issue (or explicitly accepted as a deliberate constant) rather than rediscovered piecemeal. This document is a findings snapshot, not living documentation — once an item is actioned (made configurable, or deliberately left a named constant with rationale), its entry here is historical, not authoritative; check the code.

**Process fix landed alongside this audit:** [AGENTS.md](../AGENTS.md)'s TDD Discipline step 0 now requires a "configuration call-out" for every new numeric/boolean/threshold/limit a feature introduces — decide explicitly whether it's a SystemSettings-backed admin knob or a deliberate fixed constant with a rationale comment, before implementation starts. This is what should prevent a third round of this audit.

---

## Part 1 — RAG / Embedding Pipeline

### Confirmed already configurable (no gap)
`embedding_provider` / `embedding_url` / `embedding_model` and `llm_provider` / `llm_url` / `llm_model` are fully `SystemSettings`-backed today (`backend/app/services/system_settings_service.py`, mirrored in `mcp-servers/doc-search/app/search.py`'s own resolver).

### Gaps found

| # | Knob | Location | Current value | Kind | Judgment |
|---|---|---|---|---|---|
| 1 | **Similarity/relevance threshold** | *absent entirely* | — | — | **Highest priority.** `EmbeddingRepository.search_similar` (`backend/app/repositories/embedding_repository.py:17-40`, doc-search's copy `mcp-servers/doc-search/app/repositories/embedding_repository.py:53-80`) does `ORDER BY distance LIMIT top_k` with no `WHERE distance < X` cutoff. A query with zero relevant documents in the corpus still returns the *k* least-bad chunks. This is a missing capability, not a hardcoded value to unhide. |
| 2 | **Max results (top_k)** | `mcp-servers/doc-search/app/server.py:147`, `mcp-servers/doc-search/app/search.py:169`, `backend/app/mcp_client/doc_search_client.py:76` | `5`, duplicated 3× | Python/Pydantic field default | No server-side ceiling exists — the LLM can request any `top_k` it wants. Good SystemSettings candidate; should also become doc-search's actual enforced ceiling, not just a suggested default. |
| 3 | **Chunk size (min/max)** | `backend/app/services/chunking_service.py:23-24` | `MIN_CHUNK_TOKENS=500`, `MAX_CHUNK_TOKENS=1000` | Python module constants | Good candidate. Caveat: only affects newly-(re)indexed documents, not retroactive like the provider switch — document this if implemented. |
| 4 | **Chunk overlap ratio** | `backend/app/services/chunking_service.py:30` | `CHUNK_OVERLAP_RATIO = 0.125` | Python module constant | Good candidate, same retroactivity caveat as #3. |
| 5 | **Excerpt truncation cap** | `mcp-servers/doc-search/app/search.py:24` | `MAX_EXCERPT_CHARS = 2000` | Python module constant | Reasonable candidate; bundle with #2/#3/#4 rather than treat separately — it governs how much of a retrieved chunk reaches the LLM per source. |
| 6 | **RRF fusion constant** | `mcp-servers/doc-search/app/repositories/embedding_repository.py:17` | `RRF_K = 60` (literature-standard default) | Python module constant | Low priority — obscure, rarely needs tuning. |
| 7 | **Hybrid-search candidate multiplier** | `mcp-servers/doc-search/app/repositories/embedding_repository.py:23` | `_CANDIDATE_MULTIPLIER = 4` | Python module constant | Not a good candidate — internal implementation headroom, not an admin-facing concept. |
| 8 | **Same candidate multiplier, duplicated inline** | `backend/app/api/embeddings.py:72` | `payload.top_k * 4` | Inline literal (not even a named constant) | Same judgment as #7, but worse — should at minimum become a named constant even if not made configurable. |

### Not a gap (correctly fixed)
- **Embedding dimension** (`EMBEDDING_DIMENSION = 768`, `backend/app/services/embedding_service.py:16` and duplicated in `mcp-servers/doc-search/app/search.py:56`) is schema-tied to the pgvector column width — changing it requires a migration and full re-embedding, not a per-call override. Correctly hardcoded.
  - **Adjacent landmine, not a config gap**: nothing validates that a `embedding_model` switch (already configurable) produces vectors of the expected dimension. Worth a follow-up as a validation/guard issue, separate from this configurability audit.

### Prompt text (real gap, different shape)
- `search_knowledge_base` tool description (`backend/app/mcp_client/doc_search_client.py:186-193`, duplicated at `mcp-servers/doc-search/app/server.py:138-145`) directly controls whether/how eagerly the model grounds answers in the KB, and is a hardcoded string in two places. Same for the chat agent's system prompt (`backend/app/prompts/chat_prompts.py:16-24`). These don't fit a scalar `SystemSettings` column as cleanly as the numeric knobs above — `PromptTemplate` (`backend/app/prompts/prompt_template.py`) is deliberately static-text-only today, by its own documented design. Flag as a known gap requiring its own design (a text-field DB column or prompt-versioning mechanism), not a quick add.

### Reranking (absent, already scoped)
No cross-encoder or second-stage reranking exists anywhere. This is **already documented** in `docs/RETRIEVAL_IMPROVEMENT_PROMPTS.md` ("Prompt 4") as deliberately deferred future work, and that doc *already specifies* the SystemSettings pattern should be used if it's ever built. No numbered GitHub issue tracks it yet.

---

## Part 2 — Solution-Wide Sweep (everything else)

Excludes anything already covered above or already `SystemSettings`-backed (LLM/embedding config, retention, guardrails, tracing, rate-limiting, audit-log-UI, nav-config).

### Auth (JWT / Keycloak)

| Knob | Location | Value | Judgment |
|---|---|---|---|
| JWKS cache TTL (backend) | `backend/app/core/auth.py:20` | `_JWKS_CACHE_TTL = 600` | Good candidate — pure cache-TTL, resolved per-call already. |
| JWKS cache TTL (doc-search) | `mcp-servers/doc-search/app/auth.py:26` | `_JWKS_CACHE_TTL = 600` | Same knob, duplicated in the second deployable — should move together if actioned. |
| JWKS forced-refetch cooldown | `mcp-servers/doc-search/app/auth.py:40` | `_JWKS_REFETCH_COOLDOWN_SECONDS = 30` | Good candidate — protects against hammering Keycloak on an unknown `kid`. |
| Keycloak token-exchange timeout | `backend/app/api/auth.py:141` | `timeout=10.0` | Good candidate — same tier as `llm_timeout`/`embedding_timeout`. |
| Doc-search JWKS fetch timeout | `mcp-servers/doc-search/app/auth.py:79` | `timeout=10.0` | Good candidate, same shape. |
| Keycloak client secret | `backend/app/core/config.py:114` | dev placeholder, env-only | **Not** a candidate — it's a credential; DB-storing via the Settings pattern would be a security regression. |
| Trusted proxy count | `backend/app/core/config.py:214` | `rate_limit_trusted_proxy_count`, env-only | **Not** a candidate — fixed deployment topology, security-sensitive if wrong; deliberately env/redeploy-only. |

### MCP / doc-search client

| Knob | Location | Value | Judgment |
|---|---|---|---|
| MCP tool-call timeout | `backend/app/mcp_client/doc_search_client.py:30` | `MCP_CALL_TIMEOUT = 30s` | Good candidate — directly affects chat latency/failure behavior. |
| MCP connect timeout | `backend/app/mcp_client/doc_search_client.py:63` | `_CONNECT_TIMEOUT_SECONDS = 30.0` | Good candidate. |
| MCP SSE read timeout | `backend/app/mcp_client/doc_search_client.py:64` | `_SSE_READ_TIMEOUT_SECONDS = 300.0` | Good candidate. |
| Max tool-call rounds per chat turn | `backend/app/agents/chat_agent.py:16` | `MAX_TOOL_CALL_ROUNDS = 5` | Good candidate — cost/latency vs. thoroughness ceiling, same spirit as rate-limit capacity. |

### Storage (MinIO / uploads)

| Knob | Location | Value | Judgment |
|---|---|---|---|
| Upload size ceiling | `backend/app/core/config.py:221` | `knowledge_base_upload_max_bytes = 25 MiB`, env-only | Good candidate — comparable to existing DB-backed guardrail/rate-limit ceilings. |
| Allowed content-type list | `backend/app/core/config.py:222-226` | env-only list | **Not** a good raw-DB-editable candidate — each type maps to specific extraction code in `text_extraction.py`; a free-text DB list could enable a type with no matching extractor. If ever exposed, only as on/off toggles over the existing fixed set (like guardrail pattern toggles), not a freeform list. |
| MinIO client pool/retry tuning | `backend/app/storage/minio_client.py` | none configured at all | Not yet even an env-only constant — noted as an absence, not a promotion candidate. |

### Database

| Knob | Location | Value | Judgment |
|---|---|---|---|
| Connection pool size / overflow / recycle / pre-ping | `backend/app/db/database.py:12`, `mcp-servers/doc-search/app/db.py:15` | SQLAlchemy defaults, not set anywhere | Gap one level below the others — not yet promoted even to an env var. `pool_size`/`max_overflow`/`pool_recycle` are tied to `create_engine()` at import time, so a DB-stored override would need a restart anyway (same category as `tracing_enabled`) — if added, should be env-var `Settings` fields, not `SystemSettings`-backed. `pool_pre_ping` (bool) is the one sub-item that's cheap to add and has clear value (avoids stale-connection errors after DB restart/failover). |

### Session / Thread handling
No new gaps found beyond what `retention_service` already covers (TTLs are DB-backed).

| Knob | Location | Value | Judgment |
|---|---|---|---|
| Rate-limit bucket idle-eviction window | `backend/app/services/rate_limiter_service.py:58` | `_STALE_AFTER_SECONDS = 3600` | Good candidate — numeric, resolved per-request, no restart implication. |

### Networking / CORS

| Knob | Location | Value | Judgment |
|---|---|---|---|
| CORS allowed origins | `backend/app/core/config.py:15` | env-only list | **Not** a good candidate as currently structured — `CORSMiddleware` is installed once at `app.add_middleware()` time (`backend/app/main.py:48-54`), before any DB read is possible; a DB override would need a restart anyway, and (unlike `tracing_enabled`) there's no existing precedent here for a middleware-construction-time-only override. Env-var remains the right mechanism unless CORS handling is refactored to a dynamic per-request check. |

### Other

| Knob | Location | Value | Judgment |
|---|---|---|---|
| LLM sampling temperature | `backend/app/core/llm_client.py:94` | `temperature=0.7`, hardcoded, no env var or DB override at all | Good candidate — conspicuously the one LLM parameter left out of the otherwise-complete `resolve_llm_config` resolver. |
| Output guardrail verbatim-leak threshold | `backend/app/guardrails/output_guardrail.py:85` | `_VERBATIM_LEAK_MIN_WORDS = 6` | Good candidate — directly analogous to the already-DB-backed guardrail thresholds; a false-positive/false-negative tuning knob. |
| Retention purge batch size | `backend/app/services/retention_service.py:48` | `DEFAULT_BATCH_SIZE = 500` | Good candidate — distinct from the (already DB-backed) retention *windows*; resolved fresh per CronJob run, no restart implication. |
| Dashboard "recent" lookback window | `backend/app/services/dashboard_service.py:51` | `RECENT_WINDOW = 24h` | **Not** a candidate — the module's own docstring explicitly argues for keeping this fixed ("a glance-level operational signal, not a reporting feature"). Deliberate, not an oversight. |
| Retry/backoff logic | *absent everywhere* | — | No retry/backoff exists for any outbound call (Keycloak, LLM, embedding server, MinIO, doc-search MCP) — single attempt + timeout only. Not a constant to promote; flagged as a standalone resilience gap. |

---

## Triage outcome — issues filed 2026-09-04

**[#68](../../../issues/68) — RAG tuning bundle** (Part 1, items 1–5): similarity threshold, top_k ceiling, chunk size, chunk overlap, excerpt cap. Bundled into one issue since these are reviewed and tuned together (one design conversation: schema fields, retroactivity caveats, Settings UI section).

**[#69](../../../issues/69) — timeout/cache tuning bundle** (Auth + MCP client sections): JWKS cache TTL ×2, JWKS refetch cooldown, Keycloak/doc-search auth timeouts ×2, MCP call/connect/SSE timeouts ×3. Same shape, same resolver pattern, same UI section.

**Standalone issues:**
- [#70](../../../issues/70) — LLM `temperature`.
- [#71](../../../issues/71) — Output guardrail `_VERBATIM_LEAK_MIN_WORDS`.
- [#72](../../../issues/72) — Upload size ceiling (`knowledge_base_upload_max_bytes`).
- [#73](../../../issues/73) — Rate-limit bucket idle-eviction window.
- [#74](../../../issues/74) — Retention purge batch size.
- [#75](../../../issues/75) — `MAX_TOOL_CALL_ROUNDS`.

**Separate follow-ups (not pure configurability gaps — each needed its own design-pass framing):**
- [#76](../../../issues/76) — Retry/backoff strategy for outbound service calls. No retry/backoff exists anywhere in the system today; scoped as a design-then-implement issue rather than a straightforward `SystemSettings` add, since it requires deciding which calls should retry and what policy before any code is written.
- [#77](../../../issues/77) — Embedding dimension mismatch guard + re-embedding trigger on model change. Covers both preventing a silent dimension mismatch when `embedding_model` is switched at runtime, and triggering re-embedding of existing documents so they don't stay silently stale/mixed against the newly configured model.

**Not filed as issues — deliberate constants, to be named explicitly in code per the new AGENTS.md configuration call-out rather than left silent:**
- `EMBEDDING_DIMENSION` (schema-tied) — its risk is now covered by #77's validation scope, but the constant itself stays fixed by design.
- `keycloak_client_secret`, `rate_limit_trusted_proxy_count` (security-sensitive / topology-fixed).
- `cors_origins` mechanism (restart-only; env-var is correct as-is).
- DB connection pool settings (restart-only if ever added).
- `knowledge_base_upload_allowed_content_types` (extraction-code-tied).
- `dashboard_service.RECENT_WINDOW` (already has a documented rationale).
