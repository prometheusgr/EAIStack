"""FastAPI dependency for the object-storage boundary.

Mirrors app.db.database.get_db's shape: a single dependency function that
endpoints depend on, overridable in tests (see
tests/unit/test_knowledge_base_upload.py's FakeDocumentStore) the same way
get_db is overridden with a test session.
"""

from functools import lru_cache

from app.core.config import settings
from app.storage.document_store import DocumentStore
from app.storage.minio_client import build_minio_client


@lru_cache(maxsize=1)
def _document_store() -> DocumentStore:
    """Build the process-wide DocumentStore once.

    The underlying Minio client holds a connection pool, so it is built
    once per process and reused - the same rationale as
    app.core.tls.get_ssl_context caching the parsed CA bundle.
    """
    return DocumentStore(client=build_minio_client(), bucket=settings.minio_bucket)


def get_document_store() -> DocumentStore:
    """FastAPI dependency yielding the shared DocumentStore instance."""
    return _document_store()
