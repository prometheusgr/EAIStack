"""TLS trust-store plumbing shared by every outbound HTTP client.

Phase 5 (Decision 2) mounts the internal CA's ca.crt into the pod and points
every outbound httpx client at it. This module has the one expression that
implements that rule (`httpx_verify()`) and a process-wide cache of the
parsed SSL trust store (`get_ssl_context()`), so callers stop re-parsing the
same PEM file on every request.
"""

import ssl

from app.core.config import settings

_ssl_context: ssl.SSLContext | None = None


def httpx_verify() -> str | bool:
    """The value to pass as httpx's `verify=` kwarg.

    The configured CA bundle path if set, else True (httpx's default trust
    store). httpx ignores `verify` entirely for plaintext http:// URLs, so
    passing this unconditionally is already correct for hops that stay
    unencrypted (local dev, docker-compose).
    """
    return settings.ca_bundle_path or True


def get_ssl_context() -> ssl.SSLContext:
    """Return a process-wide SSLContext built from the configured CA bundle.

    `httpx.Client(verify=<path-string>)` calls `ssl.create_default_context
    (cafile=path)` internally on every construction — reading and parsing
    the PEM file into a fresh X.509 trust store each time. Since
    settings.ca_bundle_path never changes within a process's lifetime, that
    work is done once here and the resulting context is reused across every
    client built afterward. Passing an SSLContext instead of a path/bool as
    `verify=` skips httpx's own internal context construction entirely.

    Callers that build a fresh httpx.Client/AsyncClient per call (the LLM
    client, the doc-search MCP client, the embedding service) should use
    this instead of `httpx_verify()`. Lower-frequency call sites (JWKS
    fetches, the token-exchange endpoint) already cache their http client
    or run rarely enough that the extra parse doesn't matter, and continue
    to use `httpx_verify()` directly.
    """
    global _ssl_context
    if _ssl_context is None:
        _ssl_context = ssl.create_default_context(cafile=settings.ca_bundle_path)
    return _ssl_context


def reset_ssl_context_cache() -> None:
    """Clear the cached SSLContext.

    Only meaningful in tests: settings.ca_bundle_path is fixed for the
    lifetime of a real process, but a test suite that monkeypatches it
    across multiple tests needs to force the next get_ssl_context() call to
    rebuild from the current value rather than reuse a previous test's
    cached context.
    """
    global _ssl_context
    _ssl_context = None
