# Retrieval Improvement Prompts (technical content)

Four sequenced pieces of work to make knowledge-base search work well on
highly technical documents. Each prompt is self-contained: paste one into a
fresh Claude Code session in this repo.

**Do them in order.** Prompt 1 is a prerequisite for meaningfully evaluating
2–4, and each later prompt assumes the earlier schema exists.

**Before starting any of them**, the Phase 3 review work currently sitting
uncommitted in the working tree should be committed or stashed — these are
separate concerns and should not be tangled into the same diff.

**Every prompt assumes the standards in `AGENTS.md`**: TDD (test fails first),
`docs/DATABASE_MODELS.md` for any schema change, `docs/REPOSITORY_PATTERN.md`
for any new query, no premature abstraction, comments explain *why*.

A note on effort: prompts 2 and 3 are substantial (schema migration + backfill,
touching two deployables). Expect to review them carefully rather than
accepting wholesale.

---

## Prompt 1 — Asymmetric embedding prefixes (do this first)

> `nomic-embed-text-v1.5` is an asymmetric embedding model: it expects
> `search_document: ` prefixed to text at index time and `search_query: `
> prefixed at query time. Our application code does neither — grep for
> `search_document` across `backend/app` and `mcp-servers/doc-search/app`
> returns nothing. Only test fixtures use the prefixes, so our tests look
> correct while production is silently losing retrieval quality.
>
> Fix this so the prefix is applied structurally, not by remembering to pass
> it at each call site.
>
> Index-time call sites (all currently unprefixed):
> - `backend/app/api/knowledge_base.py:56` (create)
> - `backend/app/api/knowledge_base.py:126` (update)
>
> Query-time call sites:
> - `backend/app/api/embeddings.py:45` (semantic search endpoint)
> - `mcp-servers/doc-search/app/search.py` — `generate_query_embedding`
>
> Requirements:
> - The prefix must be tied to the *purpose* of the call (indexing vs
>   querying) so a new call site cannot forget it. Consider distinct
>   functions (e.g. `embed_document` / `embed_query`) rather than a boolean
>   flag — a boolean at a call site is exactly the thing that gets passed
>   wrong.
> - The prefix is a property of the **model**, not of all embedding
>   providers. The `fake` provider must not be affected in a way that breaks
>   existing deterministic-vector tests. Decide whether prefixing belongs
>   inside or outside the provider switch and explain the choice.
> - `mcp-servers/doc-search` is a separate deployable and cannot import from
>   `backend/`. It has its own copy of this logic; keep the two consistent
>   and note in each why the duplication exists (same reasoning as its
>   `auth.py`).
> - TDD: write failing tests first asserting that the text actually handed to
>   the embedding provider carries the right prefix, for both index and query
>   paths, in both services.
>
> **Migration impact — call this out explicitly in your summary:** existing
> stored vectors were produced without the prefix, so they are no longer
> comparable to newly-prefixed query vectors. Tell me whether existing
> documents need re-embedding and, if so, propose (but do not build) the
> smallest safe way to do it. Do not silently leave a mixed corpus.
>
> Verify: `pytest tests/unit/` in `backend/`, and `pytest tests/unit/` plus
> `pytest tests/integration/` in `mcp-servers/doc-search/` (Docker is
> available, so integration tests should genuinely run). Report actual output.

---

## Prompt 2 — Chunking with structure-aware splitting

> Today `backend/app/api/knowledge_base.py` embeds `payload.content` as a
> single vector per document, however long it is. For technical documents
> this is the dominant retrieval failure:
>
> 1. A long spec collapses into one averaged vector, so specific facts inside
>    it match poorly.
> 2. Our embedding server runs `--ctx-size 8192` (see `docker-compose.yml`),
>    so content beyond that is **silently truncated server-side** — long
>    documents are only partially embedded, with no error.
> 3. `mcp-servers/doc-search/app/search.py` returns `content[:300]`
>    (`MAX_EXCERPT_CHARS`), so even a correct hit usually hands the LLM the
>    document's opening lines rather than the passage that matched.
>
> Implement chunking so we store and retrieve passages, not whole documents.
>
> Design requirements:
> - **Structure-aware splitting**, not fixed-size windows: split on markdown
>   headings/section boundaries. **Never split a fenced code block**, even if
>   that makes a chunk oversized — a bisected code block is worse than a long
>   one. Target roughly 500–1000 tokens with ~10–15% overlap.
> - **Prepend context to each chunk before embedding**: document title plus
>   the heading path (e.g. `"Deployment Guide > TLS > Certificate rotation"`).
>   A chunk extracted from its section loses the context that makes it
>   meaningful; this restores it cheaply and matters a lot for technical docs.
>   Note this is separate from, and composes with, the `search_document:`
>   prefix from Prompt 1.
> - Chunking logic must be **pure and deterministic** — plain text in, chunks
>   out, no DB or network — so it can be TDD'd directly. Test the cases that
>   actually break: a document with no headings, a code block larger than the
>   target size, a heading with no body, content shorter than one chunk.
>
> Schema:
> - `embeddings` currently assumes one row per document. It needs to carry
>   chunk identity and the chunk's own text (so retrieval can return the
>   matching passage without re-splitting at query time).
> - Follow `docs/DATABASE_MODELS.md` for the model + Alembic migration. The
>   latest migration is `005_retention_and_audit_log.py`.
> - `mcp-servers/doc-search/app/models.py` mirrors these tables column-for-
>   column and **must be updated in the same change**. There is a parity test
>   at `backend/tests/unit/test_doc_search_schema_parity.py` that will fail if
>   you update only one side — that failure is the guard working, not a
>   problem to route around.
> - Existing rows need a backfill path. Propose it, flag the re-embedding
>   cost, and get my confirmation before writing a destructive migration.
>
> Retrieval changes:
> - Return the **matching chunk** with its heading path, not
>   `content[:MAX_EXCERPT_CHARS]`. Raise the excerpt cap substantially — 300
>   characters is about one sentence and is not enough to ground an answer.
> - Consider deduplicating multiple chunks from the same document in results,
>   and say what you chose.
>
> Both `backend/app/api/knowledge_base.py` (create and update paths) and
> `mcp-servers/doc-search/app/search.py` are affected.
>
> This is a large change. Start by proposing the schema and chunking approach
> and **stop for my review before implementing**.

---

## Prompt 3 — Hybrid search (vector + BM25)

> Our knowledge base holds highly technical content: error codes
> (`ORA-01555`), version strings (`v2.14.3`), CLI flags (`--ctx-size`), API
> names, part numbers. Pure vector search is weak precisely here — these are
> rare tokens, and embeddings smear them toward semantic neighbors, so
> searching for a specific error code returns documents about *other* errors.
>
> Add hybrid retrieval combining pgvector similarity with Postgres full-text
> search, fused into one ranking. We already run Postgres, so this needs no
> new infrastructure.
>
> Requirements:
> - Use Postgres `tsvector`/`ts_rank` for the lexical side, with a GIN index.
>   Prefer a generated/maintained `tsvector` column over computing it per
>   query.
> - Combine the two rankings with **Reciprocal Rank Fusion** (or justify a
>   different fusion choice). RRF needs no score normalization between two
>   incomparable scales, which is why it is usually the right default —
>   cosine distance and `ts_rank` are not on a common scale.
> - Make the fusion weighting a **named constant with a comment explaining
>   the tradeoff**, not a bare magic number.
> - The query lives in doc-search's `EmbeddingRepository`
>   (`mcp-servers/doc-search/app/repositories/embedding_repository.py`).
>   That repository is **read-only by design** and has a structural test
>   asserting its public surface
>   (`mcp-servers/doc-search/tests/unit/test_repository_surface.py`) — adding
>   a read method is fine, but update that test deliberately and keep the
>   no-write-methods guarantee intact.
> - User isolation (`KnowledgeBase.user_id`) and the soft-delete filter
>   (`Embedding.deleted_at`) must hold on **both** sides of the hybrid query.
>   This is the most likely place to introduce a data-leak bug: a lexical
>   branch that forgets the ownership filter would return other users'
>   documents. Test it explicitly.
> - Schema changes must be mirrored in `backend/app/db/models.py` and
>   doc-search's `models.py` (parity test will enforce this).
>
> TDD with real Postgres (doc-search integration tests use testcontainers;
> Docker is available). Include a test that is the actual motivating case: an
> exact-token query like an error code where vector search alone ranks the
> right document poorly and hybrid ranks it first. If that test does not fail
> before your change, the change is not justified — tell me so.

---

## Prompt 4 — Cross-encoder reranking (only if 1–3 are not enough)

> **Only do this if retrieval quality is still insufficient after prompts
> 1–3.** It adds latency and another vendored model, so it needs to earn its
> place. If asked to do this without evidence that 1–3 fell short, push back
> and say what evidence would justify it.
>
> Add a reranking stage: retrieve a wider candidate set (top ~20) via hybrid
> search, then rerank with a local cross-encoder and return the top ~5. A
> cross-encoder reads query and passage together, so it resolves near-miss
> cases bi-encoder embeddings cannot.
>
> Requirements:
> - The model must run **fully locally and air-gapped** (e.g.
>   `bge-reranker-base`). It must be vendored like every other model — see
>   `docs/AIRGAP_SETUP.md` and how the existing embedding model is handled.
>   No runtime downloads.
> - Reranking is a **separate concern from retrieval**: the repository
>   returns candidates, the reranker reorders them. Do not entangle the
>   cross-encoder call into the SQL query path.
> - It must be **optional and configurable**, defaulting to off, following the
>   existing provider-config pattern (env default + DB override via
>   `system_settings`, resolved per call — see
>   `backend/app/services/system_settings_service.py`). Read
>   `docs/BACKEND_SERVICES.md` first.
> - Respect the settings precedence rule already established: a DB override
>   wins over the env default, and the resolution uses `is not None` checks,
>   not truthiness.
> - Candidate count and final count must be named constants with rationale.
> - Report the **latency cost** with real measurements, not estimates. If it
>   is significant, say so plainly rather than burying it.
>
> TDD: the reranker boundary is an external model call — mock it at that
> boundary only (same discipline as the LLM boundary per `AGENTS.md`), and
> test the ordering logic deterministically.

---

## Evaluation (worth doing alongside prompt 1)

> Everything above is unmeasurable without a way to tell whether retrieval
> improved. Before or alongside Prompt 1, build a small evaluation harness.
>
> - Assemble ~20–30 realistic query/expected-document pairs from our actual
>   technical content, including the hard cases: exact error codes, version
>   strings, CLI flags, and paraphrased conceptual questions.
> - Report standard retrieval metrics — Recall@k and MRR at minimum.
> - It must run against a real Postgres (testcontainers) and be **runnable on
>   demand, not part of the CI-gating unit suite** — it is a measurement tool,
>   not a pass/fail gate, and its numbers will move as content changes.
> - Keep the fixture corpus small and committed so runs are reproducible.
>
> This is what lets each later change be justified with a number instead of
> an opinion. Without it, prompt 4 in particular is unjustifiable.
