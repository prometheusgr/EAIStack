"""Unit tests for retrieval evaluation metrics (Recall@k, MRR).

Pure, deterministic functions — ranked doc ids in, a score out, no DB or
network — so they belong in the CI-gating unit suite even though the
harness that produces the rankings (tests/eval/) is not itself gated.
"""

import pytest

from app.eval.metrics import mean_reciprocal_rank, recall_at_k


@pytest.mark.unit
def test_recall_at_k_hit_at_top_rank():
    """The expected doc as the very first result is a hit."""
    assert recall_at_k(ranked_doc_ids=["doc-1", "doc-2"], expected_doc_id="doc-1", k=5) == 1.0


@pytest.mark.unit
def test_recall_at_k_hit_within_k_but_not_first():
    """A hit anywhere within the top k still counts as a full recall of 1.0."""
    assert (
        recall_at_k(ranked_doc_ids=["doc-2", "doc-3", "doc-1"], expected_doc_id="doc-1", k=5) == 1.0
    )


@pytest.mark.unit
def test_recall_at_k_miss_outside_k():
    """A hit beyond position k does not count — this is what makes k meaningful."""
    assert (
        recall_at_k(ranked_doc_ids=["doc-2", "doc-3", "doc-1"], expected_doc_id="doc-1", k=2) == 0.0
    )


@pytest.mark.unit
def test_recall_at_k_miss_when_expected_doc_absent():
    """The expected document not appearing in the ranking at all is a miss."""
    assert recall_at_k(ranked_doc_ids=["doc-2", "doc-3"], expected_doc_id="doc-1", k=5) == 0.0


@pytest.mark.unit
def test_recall_at_k_empty_ranking_is_a_miss():
    """No results at all (e.g. an empty knowledge base) is a miss, not an error."""
    assert recall_at_k(ranked_doc_ids=[], expected_doc_id="doc-1", k=5) == 0.0


@pytest.mark.unit
def test_mean_reciprocal_rank_rewards_earlier_hits():
    """MRR is the mean of 1/rank across queries — a hit at rank 1 scores
    higher than the same query's hit at rank 3.
    """
    rank_1_hit = mean_reciprocal_rank(
        [{"ranked_doc_ids": ["doc-1", "doc-2"], "expected_doc_id": "doc-1"}]
    )
    rank_3_hit = mean_reciprocal_rank(
        [{"ranked_doc_ids": ["doc-2", "doc-3", "doc-1"], "expected_doc_id": "doc-1"}]
    )

    assert rank_1_hit == 1.0
    assert rank_3_hit == pytest.approx(1 / 3)
    assert rank_1_hit > rank_3_hit


@pytest.mark.unit
def test_mean_reciprocal_rank_averages_across_queries():
    """MRR across multiple queries is the mean of each query's own
    reciprocal rank, not (e.g.) the reciprocal of an averaged rank.
    """
    queries = [
        {"ranked_doc_ids": ["doc-1"], "expected_doc_id": "doc-1"},  # rank 1 -> 1.0
        {"ranked_doc_ids": ["doc-x", "doc-1"], "expected_doc_id": "doc-1"},  # rank 2 -> 0.5
    ]

    assert mean_reciprocal_rank(queries) == pytest.approx((1.0 + 0.5) / 2)


@pytest.mark.unit
def test_mean_reciprocal_rank_scores_a_miss_as_zero():
    """A query whose expected document never appears contributes 0, not an
    error and not a skipped/excluded query.
    """
    queries = [
        {"ranked_doc_ids": ["doc-1"], "expected_doc_id": "doc-1"},  # rank 1 -> 1.0
        {"ranked_doc_ids": ["doc-x"], "expected_doc_id": "doc-missing"},  # miss -> 0.0
    ]

    assert mean_reciprocal_rank(queries) == pytest.approx((1.0 + 0.0) / 2)


@pytest.mark.unit
def test_mean_reciprocal_rank_raises_on_empty_query_set():
    """An empty query set has no meaningful mean — fail loudly rather than
    silently returning 0.0 or NaN, which would look like a real (bad) score.
    """
    with pytest.raises(ValueError):
        mean_reciprocal_rank([])
