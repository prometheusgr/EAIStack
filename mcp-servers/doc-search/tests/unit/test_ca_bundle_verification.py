"""TLS trust plumbing: doc-search's outbound HTTP clients verify against the CA bundle.

The doc-search pod mounts the internal CA's ca.crt the same way the backend does
(Phase 5, Decision 2), and points every outbound client at it via
`verify=settings.ca_bundle_path or True`. One uniform rule, no URL-scheme
sniffing: httpx ignores `verify` for plaintext http:// URLs, so passing the path
unconditionally is already correct for hops that stay unencrypted.

Each test asserts the *constructor argument* rather than an attribute on the
finished client, because httpx>=0.28 builds its SSLContext eagerly and retains
no readable `verify`.

Covers call sites 3 and 7 of Decision 2's seven-site inventory; the backend
owns the other five in its own suite.
"""

from unittest.mock import patch

import pytest

import app.auth as auth_module
import app.search as search_module
from app.config import settings

CA_BUNDLE = "/etc/ssl/eaistack/ca.crt"


@pytest.fixture
def ca_bundle_path(monkeypatch):
    """Set settings.ca_bundle_path for the duration of a single test."""

    def _set(path: str | None):
        monkeypatch.setattr(settings, "ca_bundle_path", path)

    return _set


@pytest.mark.unit
def test_ca_bundle_path_defaults_to_none_preserving_default_trust_store():
    """Unset means "use the system trust store" — local dev and docker-compose
    talk plain HTTP and must not be forced to load a bundle that isn't there.
    """
    assert settings.ca_bundle_path is None


# --- Site 3: Keycloak JWKS fetch (async) -------------------------------------


@pytest.mark.unit
def test_jwks_http_client_verifies_against_ca_bundle(ca_bundle_path, monkeypatch):
    """Call site 3 — doc-search → Keycloak JWKS.

    doc-search verifies every bearer token against Keycloak itself rather than
    trusting the backend's word, so a missing bundle makes it reject every
    token once Keycloak is behind TLS.
    """
    ca_bundle_path(CA_BUNDLE)
    monkeypatch.setattr(auth_module, "_http_client", None)

    with patch.object(auth_module.httpx, "AsyncClient") as mock_client:
        auth_module._get_http_client()

    assert mock_client.call_args.kwargs["verify"] == CA_BUNDLE


@pytest.mark.unit
def test_jwks_http_client_uses_default_trust_store_when_unset(ca_bundle_path, monkeypatch):
    """With no bundle configured the client must fall back to httpx's default
    trust store (verify=True), not to a None that would disable verification.
    """
    ca_bundle_path(None)
    monkeypatch.setattr(auth_module, "_http_client", None)

    with patch.object(auth_module.httpx, "AsyncClient") as mock_client:
        auth_module._get_http_client()

    assert mock_client.call_args.kwargs["verify"] is True


# --- Site 7: embedding-server, synchronous client ----------------------------


@pytest.mark.unit
def test_query_embedding_client_verifies_against_ca_bundle(ca_bundle_path, monkeypatch):
    """Call site 7 — doc-search → embedding-server at query time.

    A synchronous httpx.Client, not an AsyncClient — easy to miss when
    grepping. Without the bundle, every knowledge-base query fails.
    """
    ca_bundle_path(CA_BUNDLE)

    monkeypatch.setattr(
        search_module,
        "resolve_embedding_config",
        lambda db: search_module.EmbeddingConfig(
            provider="llama-cpp",
            url="https://embedding-server:8002/v1",
            model="nomic-embed-text-v1.5.Q4_K_M.gguf",
            timeout=60,
        ),
    )

    with patch.object(search_module.httpx, "Client") as mock_client:
        mock_client.return_value.__enter__.side_effect = RuntimeError("stop after construction")
        with pytest.raises(RuntimeError):
            search_module.generate_query_embedding(db=None, text="anything")

    assert mock_client.call_args.kwargs["verify"] == CA_BUNDLE
