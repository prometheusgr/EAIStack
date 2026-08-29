"""Retrieval quality measurement harness.

Not a pass/fail gate: this reports Recall@k and MRR against a small,
committed, realistic technical-content corpus (tests/eval/fixtures/corpus.json)
so a later retrieval change (chunking, hybrid search, reranking) can be
justified with a number instead of an opinion, per the "Evaluation" section
of docs/RETRIEVAL_IMPROVEMENT_PROMPTS.md.

Run on demand:
    pytest tests/eval/ -v -s

Deliberately excluded from tests/unit/ and tests/integration/ (see
pyproject.toml's testpaths, which only collects under tests/) and marked
`eval` rather than `unit`/`integration`, so neither the CI-gating unit run
nor the manual "run the integration suite" habit picks it up by accident.
Requires real Postgres (testcontainers, same as tests/integration/).
"""

import json
from pathlib import Path

import pytest

from app.eval.metrics import mean_reciprocal_rank, recall_at_k
from app.models import Embedding, KnowledgeBase
from app.repositories import EmbeddingRepository
from app.search import embed_query

CORPUS_PATH = Path(__file__).parent / "fixtures" / "corpus.json"
EVAL_USER_ID = "eval-user"
TOP_K = 5


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
            embedding=embed_query(db_session, doc["content"]),
        )
        db_session.add(embedding)
        db_session.commit()


@pytest.mark.eval
def test_retrieval_quality_against_fixture_corpus(db_session, capsys):
    """Seed the fixture corpus, run every fixture query through the actual
    query-embedding + pgvector-similarity path, and report Recall@k and MRR
    overall and per query category.

    Uses embed_query for seeding (not embed_document) because the "fake"
    embedding provider (the default, and all this harness needs to exercise
    the ranking logic) produces a hash-based vector with no real semantic
    content — the asymmetric prefix only matters for a real embedding
    model, exercised instead by mcp-servers/doc-search/tests/integration/.
    A run against the real llama-cpp provider would want embed_document for
    the corpus side; see docs/RETRIEVAL_IMPROVEMENT_PROMPTS.md.
    """
    corpus = _load_corpus()
    _seed_corpus(db_session, corpus["documents"])

    repo = EmbeddingRepository(db_session)
    ranked_queries = []
    per_category: dict[str, list[dict]] = {}

    for case in corpus["queries"]:
        query_embedding = embed_query(db_session, case["query"])
        matches = repo.search_similar(EVAL_USER_ID, query_embedding, TOP_K)
        ranked_doc_ids = [kb.id for _, kb, _ in matches]

        ranked_queries.append(
            {"ranked_doc_ids": ranked_doc_ids, "expected_doc_id": case["expected_doc_id"]}
        )
        per_category.setdefault(case["category"], []).append(
            {"ranked_doc_ids": ranked_doc_ids, "expected_doc_id": case["expected_doc_id"]}
        )

    overall_recall = sum(
        recall_at_k(
            ranked_doc_ids=q["ranked_doc_ids"], expected_doc_id=q["expected_doc_id"], k=TOP_K
        )
        for q in ranked_queries
    ) / len(ranked_queries)
    overall_mrr = mean_reciprocal_rank(ranked_queries)

    with capsys.disabled():
        print(f"\n--- Retrieval quality (n={len(ranked_queries)} queries, k={TOP_K}) ---")
        print(f"Overall Recall@{TOP_K}: {overall_recall:.2f}")
        print(f"Overall MRR:      {overall_mrr:.2f}")
        for category, queries in sorted(per_category.items()):
            category_recall = sum(
                recall_at_k(
                    ranked_doc_ids=q["ranked_doc_ids"],
                    expected_doc_id=q["expected_doc_id"],
                    k=TOP_K,
                )
                for q in queries
            ) / len(queries)
            category_mrr = mean_reciprocal_rank(queries)
            print(
                f"  {category:12s} (n={len(queries):2d})  "
                f"Recall@{TOP_K}={category_recall:.2f}  MRR={category_mrr:.2f}"
            )

    # A measurement tool, not a quality gate — the numbers are the point,
    # not a threshold. The only hard assertion is that the harness produced
    # a well-formed result for every query, so a wiring bug (not a
    # retrieval-quality regression) still fails loudly.
    assert len(ranked_queries) == len(corpus["queries"])
