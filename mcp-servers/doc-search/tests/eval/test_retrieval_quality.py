"""Retrieval quality measurement harness.

Not a pass/fail gate: this reports Recall@k and MRR against a corpus of
query/expected-document pairs so a retrieval change (chunking, hybrid
search, reranking) can be justified with a number instead of an opinion,
per the "Evaluation" section of docs/RETRIEVAL_IMPROVEMENT_PROMPTS.md.

## Using this on a fork's own content

EAIStack is a forkable template (see CLAUDE.md), so this harness is
deliberately generic rather than tuned to any one deployment:

- **Corpus**: tests/eval/fixtures/corpus.json ships a small, generic
  technical-content example (error codes, version strings, CLI flags,
  paraphrases). Replace it with your own fork's real documents and queries
  — same {"documents": [...], "queries": [...]} shape (see that file) —
  once you have representative content and a set of questions with known
  correct answers. Recall@k/MRR are only meaningful against content that
  looks like what your users will actually search.
- **Retrieval strategy**: parametrized below (RETRIEVAL_STRATEGIES) so a
  fork can compare whichever strategies it has implemented — vector-only
  and hybrid ship here; a future strategy (e.g. reranking, if added per
  Prompt 4) is a matter of adding one more entry, not rewriting the harness.
- **Embedding provider**: this harness runs against whatever
  EMBEDDING_PROVIDER is configured (see docs/LLM_SETUP.md) - "fake" (the
  default) produces hash-based vectors with no real semantic content, so
  its numbers only prove the harness and ranking plumbing work end to end,
  not real retrieval quality. To get numbers worth acting on, run against
  a real embedding server (EMBEDDING_PROVIDER=llama-cpp), same as any
  other integration test in this suite that needs real semantics
  (see backend/tests/integration/test_embedding_client.py's equivalent
  requires_real_embedding_server pattern).

## When this justifies Prompt 4 (cross-encoder reranking)

Prompt 4 is explicitly gated on Prompts 1-3 (asymmetric prefixes, chunking,
hybrid search) being insufficient — reranking adds latency and another
vendored model, so it needs to earn its place with evidence, not be
built speculatively. Concretely, that means:

1. Run this harness against a real embedding provider (not "fake") and
   your fork's own representative corpus.
2. Compare RETRIEVAL_STRATEGIES's "hybrid" numbers (Prompts 1-3's
   end state) against your fork's actual quality bar — whatever
   Recall@k/MRR your use case needs to be useful.
3. Look at *why* hybrid still misses, not just that it does: cases where
   the correct document ranks just outside top_k, or where several
   documents are near-tied, are exactly what a cross-encoder resolves
   (it reads query and passage together, unlike bi-encoder embeddings).
   If misses are instead concentrated in one query category (e.g. your
   fork has almost no exact-token content), the fix is more likely a
   corpus/chunking issue than a reranking one.
4. Only once hybrid's numbers are measured as insufficient, on your own
   content, with a real embedding provider, does Prompt 4 have the
   evidence it asks for.

Run on demand:
    pytest tests/eval/ -v -s

Deliberately excluded from tests/unit/ and tests/integration/ (see
pyproject.toml's testpaths, which only collects under tests/) and marked
`eval` rather than `unit`/`integration`, so neither the CI-gating unit run
nor the manual "run the integration suite" habit picks it up by accident.
Requires real Postgres (testcontainers, same as tests/integration/).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from app.eval.metrics import mean_reciprocal_rank, recall_at_k
from app.models import Embedding, KnowledgeBase
from app.repositories import EmbeddingRepository
from app.search import embed_query
from tests.eval.corpus_seeding import embed_document_for_eval_corpus

CORPUS_PATH = Path(__file__).parent / "fixtures" / "corpus.json"
EVAL_USER_ID = "eval-user"
TOP_K = 5


@dataclass(frozen=True)
class RetrievalStrategy:
    """One retrieval path this harness can measure, by name.

    run(repo, query_embedding, query_text, top_k) must return the same
    list[tuple[Embedding, KnowledgeBase, float]] shape both
    EmbeddingRepository methods already return, so the harness's
    ranked_doc_ids extraction and metrics stay identical across strategies.
    """

    name: str
    run: Callable[[EmbeddingRepository, list[float], str, int], list]


# Add an entry here to make a new retrieval path (e.g. a future reranking
# stage) comparable through this same harness, without changing anything
# else below.
RETRIEVAL_STRATEGIES = [
    RetrievalStrategy(
        name="vector-only",
        run=lambda repo, query_embedding, query_text, top_k: repo.search_similar(
            EVAL_USER_ID, query_embedding, top_k
        ),
    ),
    RetrievalStrategy(
        name="hybrid",
        run=lambda repo, query_embedding, query_text, top_k: repo.search_hybrid(
            EVAL_USER_ID, query_embedding, query_text=query_text, top_k=top_k
        ),
    ),
]


def _load_corpus() -> dict:
    with CORPUS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _seed_corpus(db_session, documents: list[dict]) -> None:
    for doc in documents:
        kb = KnowledgeBase(
            id=doc["id"],
            user_id=EVAL_USER_ID,
            title=doc["title"],
            content=doc["content"],
        )
        db_session.add(kb)
        db_session.commit()

        embedding = Embedding(
            id=f"emb-{doc['id']}",
            doc_id=kb.id,
            embedding=embed_document_for_eval_corpus(db_session, doc["content"]),
            chunk_text=doc["content"],
        )
        db_session.add(embedding)
        db_session.commit()


def _report(strategy_name: str, ranked_queries: list[dict], per_category: dict[str, list[dict]]):
    overall_recall = sum(
        recall_at_k(
            ranked_doc_ids=q["ranked_doc_ids"], expected_doc_id=q["expected_doc_id"], k=TOP_K
        )
        for q in ranked_queries
    ) / len(ranked_queries)
    overall_mrr = mean_reciprocal_rank(ranked_queries)

    print(
        f"\n--- Retrieval quality: {strategy_name} (n={len(ranked_queries)} queries, k={TOP_K}) ---"
    )
    print(f"Overall Recall@{TOP_K}: {overall_recall:.2f}")
    print(f"Overall MRR:      {overall_mrr:.2f}")
    for category, queries in sorted(per_category.items()):
        category_recall = sum(
            recall_at_k(
                ranked_doc_ids=q["ranked_doc_ids"], expected_doc_id=q["expected_doc_id"], k=TOP_K
            )
            for q in queries
        ) / len(queries)
        category_mrr = mean_reciprocal_rank(queries)
        print(
            f"  {category:14s} (n={len(queries):2d})  "
            f"Recall@{TOP_K}={category_recall:.2f}  MRR={category_mrr:.2f}"
        )


@pytest.mark.eval
@pytest.mark.parametrize("strategy", RETRIEVAL_STRATEGIES, ids=lambda s: s.name)
def test_retrieval_quality_against_fixture_corpus(db_session, strategy, capsys):
    """Seed the corpus, run every query through one retrieval strategy, and
    report Recall@k and MRR overall and per query category.

    Parametrized over RETRIEVAL_STRATEGIES so vector-only and hybrid are
    measured (and, printed together in one pytest run, directly comparable)
    without duplicating this test for each - see the module docstring for
    how to add a future strategy or point this at a fork's own corpus.
    """
    corpus = _load_corpus()
    _seed_corpus(db_session, corpus["documents"])

    repo = EmbeddingRepository(db_session)
    ranked_queries = []
    per_category: dict[str, list[dict]] = {}

    for case in corpus["queries"]:
        query_embedding = embed_query(db_session, case["query"])
        matches = strategy.run(repo, query_embedding, case["query"], TOP_K)
        ranked_doc_ids = [kb.id for _, kb, _ in matches]

        ranked_queries.append(
            {"ranked_doc_ids": ranked_doc_ids, "expected_doc_id": case["expected_doc_id"]}
        )
        per_category.setdefault(case["category"], []).append(
            {"ranked_doc_ids": ranked_doc_ids, "expected_doc_id": case["expected_doc_id"]}
        )

    with capsys.disabled():
        _report(strategy.name, ranked_queries, per_category)

    # A measurement tool, not a quality gate — the numbers are the point,
    # not a threshold. The only hard assertion is that the harness produced
    # a well-formed result for every query, so a wiring bug (not a
    # retrieval-quality regression) still fails loudly.
    assert len(ranked_queries) == len(corpus["queries"])
