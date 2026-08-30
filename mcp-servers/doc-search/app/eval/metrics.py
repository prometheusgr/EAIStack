"""Standard retrieval metrics: Recall@k and Mean Reciprocal Rank (MRR).

Both operate on plain ranked-id lists, not on the retrieval path itself, so
they can be unit-tested without a database and reused by any future
retrieval harness (hybrid search, reranking) that also needs to report
these numbers.
"""

from typing import TypedDict


def recall_at_k(*, ranked_doc_ids: list[str], expected_doc_id: str, k: int) -> float:
    """Return 1.0 if expected_doc_id appears within the first k ranked
    results, else 0.0.

    A single-relevant-document recall (there is exactly one expected
    document per query in this evaluation harness), not the general
    multi-relevant-document formula.
    """
    return 1.0 if expected_doc_id in ranked_doc_ids[:k] else 0.0


class RankedQuery(TypedDict):
    """One query's ranked results, for mean_reciprocal_rank."""

    ranked_doc_ids: list[str]
    expected_doc_id: str


def mean_reciprocal_rank(queries: list[RankedQuery]) -> float:
    """Return the mean of 1/rank across queries, where rank is the 1-based
    position of expected_doc_id in ranked_doc_ids (0 if it does not appear).

    Raises ValueError on an empty query set rather than returning 0.0 or
    NaN, either of which would be indistinguishable from a real (bad) score.
    """
    if not queries:
        raise ValueError("mean_reciprocal_rank requires at least one query")

    reciprocal_ranks = [_reciprocal_rank(query) for query in queries]
    return sum(reciprocal_ranks) / len(reciprocal_ranks)


def _reciprocal_rank(query: RankedQuery) -> float:
    """1/rank of the expected document (1-based), or 0.0 if it never appears."""
    try:
        rank = query["ranked_doc_ids"].index(query["expected_doc_id"]) + 1
    except ValueError:
        return 0.0
    return 1 / rank
