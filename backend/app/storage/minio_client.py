"""MinIO client construction.

Phase 5 stood MinIO up with TLS deliberately ahead of any client that talks
to it, so that the default, easiest-to-write client is also the compliant
one (see docs/SECURITY.md and issue #13). build_minio_client() is the one
place that constructs the SDK client - every caller in this codebase must
go through it rather than instantiating `minio.Minio` directly, so this
guarantee can't be quietly bypassed at a second call site.
"""

from urllib.parse import urlsplit

import urllib3
from minio import Minio

from app.core.config import settings


def build_minio_client() -> Minio:
    """Build the MinIO client used for all object storage.

    secure is derived from settings.minio_url's scheme (https:// vs
    http://) - the same "let the URL decide" rule every other outbound
    client in this codebase follows (see app.core.tls: httpx respects a
    client's http(s):// scheme with no separate flag). The Helm-deployed
    production MinIO (Phase 5) is configured with an https:// URL, so the
    default path there is TLS with the internal CA bundle - exactly the
    compliant behaviour issue #13 requires. Local dev / docker-compose,
    which run MinIO over plaintext like every other service in that stack,
    configure http:// and get an unencrypted client, matching how the LLM
    and doc-search clients already behave in the same environment.

    TODO(#<follow-up>): docker-compose's MinIO (and the rest of the local
    stack) is planned to move to TLS-by-default; when that lands, the
    http:// fallback here becomes dead code for every environment, not
    just production.

    When secure and settings.ca_bundle_path are both set, an explicit
    urllib3 PoolManager is built that trusts that CA bundle - the same
    internal CA every other outbound client verifies against. Otherwise no
    explicit http_client is passed and the SDK falls back to its own
    default trust store (or is irrelevant, for a plaintext connection).
    """
    secure = settings.minio_url.startswith("https://")
    endpoint = _strip_scheme(settings.minio_url)

    http_client = None
    if secure and settings.ca_bundle_path:
        http_client = urllib3.PoolManager(ca_certs=settings.ca_bundle_path)

    return Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
        http_client=http_client,
    )


def _strip_scheme(url: str) -> str:
    """Reduce a possibly-schemed URL to the bare host:port the SDK expects.

    urlsplit only populates `.netloc` when the input has a "//" authority
    section, so a bare "host:port" (no scheme) parses its host into
    `.scheme` and port into `.path` instead - a naive `.netloc or .path`
    fallback would return just the port. Guarding on "//" in the input
    keeps a schemeless host:port passed through unchanged.
    """
    if "//" not in url:
        return url
    return urlsplit(url).netloc
