"""TLS trust plumbing: every outbound HTTP client verifies against the CA bundle.

Phase 5 (Decision 2) mounts the internal CA's ca.crt into the backend pod and
points every outbound HTTP client at it via `verify=settings.ca_bundle_path or True`.
One uniform rule, no URL-scheme sniffing: httpx ignores `verify` entirely for
plaintext http:// URLs, so passing the bundle path unconditionally is already
correct for the hops SECURITY.md allows to stay unencrypted.

These tests are load-bearing. Nothing else in CI exercises the TLS path
(docker-compose stays HTTP, the k3d smoke test is deferred), so a per-call-site
assertion is the only automated guard against a newly added HTTP client that
forgets the bundle. Each test asserts the *constructor argument*, because
httpx>=0.28 builds its SSLContext eagerly and keeps no readable `verify`
attribute on the finished client.

Covers backend call sites 1, 2, 4, 5, and 6 of Decision 2's seven-site
inventory; doc-search owns sites 3 and 7 in its own suite.
"""

import datetime
import ssl
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.core.config import settings

CA_BUNDLE = "/etc/ssl/eaistack/ca.crt"


def _write_throwaway_ca(tmp_path):
    """Write a self-signed CA to a temp file and return its path.

    Needed only where the assertion inspects a *constructed* client: httpx
    loads the bundle eagerly, so those tests cannot use a path that does not
    exist. Tests that assert on the constructor argument use the CA_BUNDLE
    sentinel instead and never touch the filesystem. This certificate is
    generated per-test, never trusted by anything, and never leaves tmp_path.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "EAIStack Test CA")])
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    bundle = tmp_path / "ca.crt"
    bundle.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return bundle


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


# --- Site 1: doc-search MCP client (async) -----------------------------------


@pytest.mark.unit
async def test_doc_search_mcp_client_verifies_against_ca_bundle(ca_bundle_path):
    """Call site 1 — backend → doc-search over Streamable HTTP.

    If this client skips the bundle, every agent tool call fails once
    doc-search is behind TLS.
    """
    ca_bundle_path(CA_BUNDLE)

    from app.mcp_client import doc_search_client

    with patch.object(doc_search_client.httpx, "AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.side_effect = RuntimeError("stop after construction")
        with pytest.raises(RuntimeError):
            await doc_search_client._open_doc_search_session(
                token="some.jwt.token",
                mcp_url="https://doc-search:8100/mcp",
                query="anything",
                top_k=5,
            )

    assert mock_client.call_args.kwargs["verify"] == CA_BUNDLE


@pytest.mark.unit
async def test_doc_search_mcp_client_uses_default_trust_store_when_unset(ca_bundle_path):
    """With no bundle configured the client must fall back to httpx's default
    trust store (verify=True), not to a None that would disable verification.
    """
    ca_bundle_path(None)

    from app.mcp_client import doc_search_client

    with patch.object(doc_search_client.httpx, "AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.side_effect = RuntimeError("stop after construction")
        with pytest.raises(RuntimeError):
            await doc_search_client._open_doc_search_session(
                token="some.jwt.token",
                mcp_url="https://doc-search:8100/mcp",
                query="anything",
                top_k=5,
            )

    assert mock_client.call_args.kwargs["verify"] is True


@pytest.mark.unit
async def test_doc_search_mcp_client_keeps_redirect_following(ca_bundle_path):
    """Building the client directly (create_mcp_http_client takes no verify=)
    must not silently drop the MCP SDK's follow_redirects default.
    """
    ca_bundle_path(CA_BUNDLE)

    from app.mcp_client import doc_search_client

    with patch.object(doc_search_client.httpx, "AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.side_effect = RuntimeError("stop after construction")
        with pytest.raises(RuntimeError):
            await doc_search_client._open_doc_search_session(
                token="some.jwt.token",
                mcp_url="https://doc-search:8100/mcp",
                query="anything",
                top_k=5,
            )

    assert mock_client.call_args.kwargs["follow_redirects"] is True


# --- Site 2: Keycloak JWKS fetch (async) -------------------------------------


@pytest.mark.unit
async def test_keycloak_jwks_fetch_verifies_against_ca_bundle(ca_bundle_path, monkeypatch):
    """Call site 2 — backend → Keycloak JWKS.

    If this client skips the bundle, every token verification fails once
    Keycloak is behind TLS: the whole API becomes unauthenticated-only.
    """
    ca_bundle_path(CA_BUNDLE)

    from app.core import auth as auth_module

    monkeypatch.setattr(auth_module, "_jwks_cache", None)
    monkeypatch.setattr(auth_module, "_jwks_cache_expiry", 0.0)

    with patch.object(auth_module.httpx, "AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.side_effect = RuntimeError("stop after construction")
        with pytest.raises(RuntimeError):
            await auth_module.get_keycloak_public_key()

    assert mock_client.call_args.kwargs["verify"] == CA_BUNDLE


# --- Site 4: ChatOpenAI → llama-server ---------------------------------------


def _ssl_context_of(http_client) -> ssl.SSLContext:
    """The SSLContext an httpx client actually verifies with.

    httpx>=0.28 resolves `verify` into an SSLContext at construction time and
    keeps no readable `verify` attribute, so a bundle path can only be
    confirmed through the context the connection pool ended up holding.
    """
    return http_client._transport._pool._ssl_context


@pytest.mark.unit
def test_chat_openai_client_verifies_against_ca_bundle(
    ca_bundle_path, db_session, monkeypatch, tmp_path
):
    """Call site 4 — backend → llama-server via ChatOpenAI.

    ChatOpenAI takes no verify= of its own, so the bundle has to arrive via a
    preconfigured httpx client. Asserted by loading a real (throwaway) CA file
    and checking the resulting SSLContext trusts exactly that certificate —
    httpx discards the path itself, so the loaded trust store is the only
    evidence the bundle was honored.
    """
    bundle = _write_throwaway_ca(tmp_path)
    ca_bundle_path(str(bundle))

    from app.core import llm_client as llm_client_module

    monkeypatch.setattr(settings, "llm_provider", "llama-cpp")

    client = llm_client_module.get_llm_client(db_session)

    trusted = _ssl_context_of(client.http_async_client).get_ca_certs()
    assert len(trusted) == 1, "the bundle should be the sole trust anchor, not an addition to it"
    assert dict(trusted[0]["subject"][0])["organizationName"] == "EAIStack Test CA"


@pytest.mark.unit
def test_chat_openai_configures_both_sync_and_async_http_clients(
    ca_bundle_path, db_session, monkeypatch, tmp_path
):
    """Both kwargs must be wired, not just the async one.

    langchain-openai hands http_client and http_async_client straight to the
    OpenAI SDK for the sync and async paths respectively. Chat inference uses
    the async path, but leaving the sync client unset would silently fall back
    to the default trust store for any synchronous invocation.
    """
    bundle = _write_throwaway_ca(tmp_path)
    ca_bundle_path(str(bundle))

    from app.core import llm_client as llm_client_module

    monkeypatch.setattr(settings, "llm_provider", "llama-cpp")

    client = llm_client_module.get_llm_client(db_session)

    for http_client in (client.http_client, client.http_async_client):
        trusted = _ssl_context_of(http_client).get_ca_certs()
        assert len(trusted) == 1
        assert dict(trusted[0]["subject"][0])["organizationName"] == "EAIStack Test CA"


# --- Site 5: Keycloak token exchange (async) ---------------------------------


@pytest.mark.unit
async def test_keycloak_token_exchange_verifies_against_ca_bundle(ca_bundle_path):
    """Call site 5 — backend → Keycloak token endpoint.

    Every authorization-code and refresh-token grant flows through here, so a
    missing bundle breaks login entirely rather than degrading one feature.
    """
    ca_bundle_path(CA_BUNDLE)

    from app.api import auth as auth_api

    with patch.object(auth_api.httpx, "AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.side_effect = RuntimeError("stop after construction")
        with pytest.raises(Exception):
            await auth_api.exchange_token(
                auth_api.TokenExchangeRequest(
                    grant_type="authorization_code",
                    code="some-code",
                    redirect_uri="https://frontend/callback",
                )
            )

    assert mock_client.call_args.kwargs["verify"] == CA_BUNDLE


# --- Site 6: embedding-server, synchronous client ----------------------------


@pytest.mark.unit
def test_embedding_client_verifies_against_ca_bundle(ca_bundle_path, db_session, monkeypatch):
    """Call site 6 — backend → embedding-server for indexing.

    A synchronous httpx.Client, not an AsyncClient — easy to miss when
    grepping. Without the bundle, document indexing fails.
    """
    ca_bundle_path(CA_BUNDLE)

    from app.services import embedding_service

    monkeypatch.setattr(settings, "embedding_provider", "llama-cpp")

    with patch.object(embedding_service.httpx, "Client") as mock_client:
        mock_client.return_value.__enter__.side_effect = RuntimeError("stop after construction")
        with pytest.raises(RuntimeError):
            embedding_service.generate_embedding(db_session, "some text")

    assert mock_client.call_args.kwargs["verify"] == CA_BUNDLE
