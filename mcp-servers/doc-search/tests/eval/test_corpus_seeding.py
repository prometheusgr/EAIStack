"""TDD test for the eval harness's corpus-seeding embedding helper.

nomic-embed-text-v1.5 is an asymmetric embedding model: "search_document: "
and "search_query: " prefixes are expected to produce different vectors for
identical text (see backend/app/services/embedding_service.py and
app/search.py's _QUERY_PREFIX comment). Production always indexes with the
document prefix and queries with the query prefix - this eval harness must
mirror that asymmetry when seeding its fixture corpus, or its Recall@k/MRR
numbers measure query-vs-query similarity instead of the query-vs-document
scenario production actually runs.

doc-search has no document-prefix embedding function in app/search.py by
design: doc-search "never indexes, only queries" in production (see
_QUERY_PREFIX's comment there). embed_document_for_eval_corpus exists only
for this harness, which is the one place in doc-search that legitimately
needs to index.
"""

import pytest

from app.search import embed_query
from tests.eval.corpus_seeding import embed_document_for_eval_corpus


@pytest.mark.eval
def test_embed_document_for_eval_corpus_differs_from_embed_query_for_same_text(db_session):
    """The document-prefixed and query-prefixed embeddings of identical text
    must differ - if they matched, the corpus-seeding helper would still be
    silently measuring query-vs-query similarity, the exact bug this
    function exists to fix.
    """
    text = "The API returns error code E4042 when the request times out."

    document_vector = embed_document_for_eval_corpus(db_session, text)
    query_vector = embed_query(db_session, text)

    assert document_vector != query_vector


@pytest.mark.eval
def test_embed_document_for_eval_corpus_is_deterministic(db_session):
    """Same text must always produce the same document-prefixed vector, so a
    harness run is reproducible."""
    text = "Rotate certificates every 90 days."

    first = embed_document_for_eval_corpus(db_session, text)
    second = embed_document_for_eval_corpus(db_session, text)

    assert first == second
