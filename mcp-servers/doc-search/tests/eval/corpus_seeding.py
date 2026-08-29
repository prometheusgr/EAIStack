"""Document-prefixed embedding, for eval-harness corpus seeding only.

app/search.py deliberately has no document-prefix embedding function:
doc-search never indexes in production, only queries (see its _QUERY_PREFIX
comment), so backend/app/services/embedding_service.py's embed_document is
the only production code path that ever applies the "search_document: "
prefix. The eval harness (tests/eval/test_retrieval_quality.py) is the one
place in doc-search that legitimately needs to index a corpus, so this
document-prefix path lives here in test code, not in app/search.py, rather
than adding index-time surface area to a service that must never index.

Mirrors backend/app/services/embedding_service.py's _DOCUMENT_PREFIX and
app/search.py's generate_query_embedding provider switch exactly, since it
must produce vectors from the same embedding space doc-search's own queries
use - a mismatched provider switch here would reintroduce the same
query-vs-query measurement bug this module exists to fix, just via a
different mechanism.
"""

import random

import httpx
from sqlalchemy.orm import Session

from app.search import EMBEDDING_DIMENSION, resolve_embedding_config
from app.tls import get_ssl_context

_DOCUMENT_PREFIX = "search_document: "


def embed_document_for_eval_corpus(db: Session, text: str) -> list[float]:
    """Generate an embedding for eval-corpus content, with the
    "search_document: " prefix nomic-embed-text-v1.5 requires at index time -
    the same prefix backend/app/services/embedding_service.py's
    embed_document applies to real indexed content.
    """
    config = resolve_embedding_config(db)
    prefixed_text = _DOCUMENT_PREFIX + text

    if config.provider == "fake":
        random.seed(hash(prefixed_text) % (2**32))
        return [random.gauss(0, 0.1) for _ in range(EMBEDDING_DIMENSION)]
    elif config.provider == "llama-cpp":
        with httpx.Client(timeout=config.timeout, verify=get_ssl_context()) as client:
            response = client.post(
                f"{config.url}/embeddings",
                json={"input": prefixed_text, "model": config.model},
            )
            response.raise_for_status()
            embedding: list[float] = response.json()["data"][0]["embedding"]
            return embedding
    else:
        raise ValueError(f"Unknown embedding_provider: {config.provider}")
