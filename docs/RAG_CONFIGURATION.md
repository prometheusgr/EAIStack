# RAG Retrieval & Chunking Configuration (Issue #68)

**Status**: implemented. This document is the admin-facing reference for the
six retrieval/chunking knobs made configurable by issue #68, following the
audit in `docs/CONFIG_AUDIT_2026-09-04.md` (Part 1). See `docs/SECURITY.md`'s
"Rate Limiting" and "Guardrails & Compliance" sections for the identical
env-default + nullable-DB-override pattern these fields also follow.

## The six fields

| Setting | Env default | DB override column | Enforcement point |
|---|---|---|---|
| Similarity threshold | none (no cutoff) | `SystemSettings.rag_similarity_threshold` | `EmbeddingRepository.search_similar` (both `backend/` and `mcp-servers/doc-search/`) |
| Maximum results | 5 | `SystemSettings.rag_max_results` | doc-search's `search_knowledge_base` tool handler (`app/server.py`) — the actual enforced ceiling, not just a suggested default |
| Minimum chunk size (tokens) | 500 | `SystemSettings.rag_min_chunk_size` | `chunking_service.chunk_document` (index time only) |
| Maximum chunk size (tokens) | 1000 | `SystemSettings.rag_chunk_size` | `chunking_service.chunk_document` (index time only) |
| Chunk overlap ratio | 0.125 | `SystemSettings.rag_chunk_overlap_ratio` | `chunking_service.chunk_document` (index time only) |
| Maximum excerpt length (characters) | 2000 | `SystemSettings.rag_max_excerpt_chars` | doc-search's `search_knowledge_base_with_sources` (`app/search.py`) |

All six are resolved fresh on every call (`app.services.rag_config_service.resolve_rag_config`
on the backend; doc-search's own independent copy, `app.search.resolve_rag_config`,
for the three fields it needs) — an admin's change via the Settings screen
takes effect on the very next query or index operation, no backend restart
required, unlike `tracing_enabled`.

**Explicitly out of scope** (per the issue's Non-goals): the RRF fusion
constant (`RRF_K = 60`) and the candidate-pool multipliers
(`_CANDIDATE_MULTIPLIER` in doc-search's repository, `_CANDIDATE_POOL_MULTIPLIER`
in `backend/app/api/embeddings.py`) stay fixed, named constants — literature-
standard defaults an operator would rarely need to tune, not admin-facing
knobs. No cross-encoder reranking either; see
`docs/RETRIEVAL_IMPROVEMENT_PROMPTS.md`'s "Prompt 4" for that deferred work.

## Similarity threshold: read the direction carefully

pgvector's `cosine_distance` returns **0 for identical vectors and 2 for
opposite ones** — it is a *distance*, not a similarity score. The threshold
therefore works as a maximum-distance cutoff: a match is kept only when its
distance is **below** the configured value. A smaller number is a *stricter*
cutoff (fewer, more-relevant results), and a larger number is *looser*.

- `null`/blank (the default) preserves the pre-#68 behavior exactly: every
  search always returns up to `top_k` results, even if none of them are
  actually relevant to the query.
- `0.0` is a valid, deliberately strict override — "only an exact match
  counts" — not an unset value. `resolve_rag_config` treats it as a real
  override (`is not None`, never truthiness), the same distinction AGENTS.md's
  Retention Field Semantics documents for `conversation_retention_hours = 0`.
- A typical starting value that filters out clearly-unrelated matches without
  being overly strict is around `0.4`–`0.5`; tune per corpus.

With no threshold set, a query about a topic the knowledge base has nothing
on still returns its `top_k` least-bad guesses — there was previously no way
for the system to say "nothing relevant was found." Setting a threshold
enables exactly that: `search_knowledge_base_with_sources` returns its
"No matching documents were found" message once every candidate is filtered
out.

**Hybrid search interaction**: doc-search's `search_hybrid` fuses a vector
branch and a lexical (full-text) branch via Reciprocal Rank Fusion. The
similarity threshold is applied **only to the vector branch** — a document
with no close vector match but a strong exact-token match (an error code, a
CLI flag) can still surface via the lexical branch alone. This is intended:
the whole reason hybrid search exists (see `docs/RETRIEVAL_IMPROVEMENT_PROMPTS.md`'s
Prompt 3) is that rare technical tokens are exactly the case where pure
vector similarity is weak.

## Maximum results is now a real ceiling, not just a default

Before this change, `top_k` defaulted to 5 in three separate places
(`mcp-servers/doc-search/app/server.py`, `app/search.py`,
`backend/app/mcp_client/doc_search_client.py`) with **no server-side
ceiling** — a tool-calling LLM could request any `top_k` it wanted. Now,
doc-search's `search_knowledge_base` tool handler clamps whatever `top_k`
the caller supplied down to `rag_max_results`, so the admin-configured value
is an actual enforced bound, not a suggestion the model can override.

## Chunk sizing: two independent fields, not one derived from the other

`rag_min_chunk_size` and `rag_chunk_size` are independent, both
admin-facing fields — not one derived from the other by a fixed ratio. This
means a PUT to `/api/settings` that would make the *effective* minimum
greater than or equal to the *effective* maximum is rejected with a `400`
(`detail: "rag_chunk_size_bounds_inverted"`), whichever of the two fields the
payload actually sets — since either field can be changed independently
while the other stays at its currently-resolved value. This check lives in
`app.api.settings.update_settings` (not a stateless per-field
`Field(ge=..., le=...)` bound, which cannot see the other field's current
value), and is the one validation in this feature that requires resolving
the current `RagConfig` before writing.

The env-level defaults (`app/core/config.py`) carry the identical check via
a `model_validator`, so a misconfigured `.env` fails loudly at process
startup rather than corrupting chunking silently the first time it runs.

## Retroactivity caveat: chunk size/overlap only affect new documents

**Changing `rag_min_chunk_size`, `rag_chunk_size`, or `rag_chunk_overlap_ratio`
only affects documents indexed (or re-indexed) after the change.** Unlike
the LLM/embedding provider switch — which applies to the very next call —
existing documents already chunked and stored under a previous setting are
**not** retroactively re-chunked. The Settings UI states this explicitly in
each field's tooltip.

`rag_similarity_threshold`, `rag_max_results`, and `rag_max_excerpt_chars`
have no such caveat: they are query-time knobs, applied fresh on every
search regardless of when a document was indexed.

**Follow-up not built in this change**: a "needs re-chunking" indicator on
existing knowledge-base documents (flagging which ones were chunked under a
now-stale setting) was considered and deliberately scoped out, per the
issue's own suggestion to defer it if needed. If a fork wants this, it would
need a per-document record of the chunk-size/overlap values in effect at
index time (not currently stored) to compare against the current resolved
config.

## Excerpt length is a safety net, not the primary sizing mechanism

`rag_max_excerpt_chars` truncates (with a trailing `...`) a single matched
chunk's text before it reaches the LLM. Since chunking already keeps
passages a reasonable size, this only bites an unusually large individual
chunk (e.g. an atomic fenced code block that legitimately exceeds the
target chunk size, per `chunking_service`'s "never split a code block" rule)
— it is not the mechanism doing the primary excerpting work the old,
pre-chunking whole-document flow relied on.

## Audit logging

Every change to any of the six fields is recorded via
`action="rag_config.config_update"`, following the identical
before/after-diff pattern as `retention.update` / `guardrail.config_update` /
`rate_limit.config_update` (see `docs/SECURITY.md`'s "Audit & Compliance"
section and `docs/AUDIT_EVENTS.md`).

## Two independent resolution copies

Like `embedding_provider`/`embedding_url`/`embedding_model`, the RAG config
is resolved independently in two places reading the same `system_settings`
row:

- **Backend** (`backend/app/services/rag_config_service.py`): the full
  six-field `RagConfig`, used for chunking (index time) and the manual
  `/api/embeddings/search` endpoint.
- **doc-search** (`mcp-servers/doc-search/app/search.py`): its own
  `resolve_rag_config`, a three-field subset (`rag_similarity_threshold`,
  `rag_max_results`, `rag_max_excerpt_chars` — the query-time fields it
  needs). doc-search is a separate deployable with no import path back to
  `backend/`, so this is a deliberate duplicate, not shared code — the same
  reasoning `resolve_embedding_config` already established. doc-search's
  partial `SystemSettings` mirror (`app/models.py`) carries only these three
  columns; chunk sizing has no equivalent there since chunking never
  happens in doc-search.

`backend/tests/unit/test_doc_search_schema_parity.py` structurally
guards against the two model declarations drifting out of sync.
