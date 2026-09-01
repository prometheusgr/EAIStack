"""TLS trust plumbing: every outbound HTTP client verifies against the CA bundle.

Phase 5 (Decision 2) mounts the internal CA's ca.crt into the backend pod and
points every outbound HTTP client at it. The verify= expression itself lives
in one place, app.core.tls: `httpx_verify()` returns
`settings.ca_bundle_path or True`, and `get_ssl_context()` returns a
process-wide cached ssl.SSLContext for call sites that build a new httpx
client per request/call (avoiding a re-parse of the CA bundle PEM file on
every one of those calls). One uniform rule, no URL-scheme sniffing: httpx
ignores `verify` entirely for plaintext http:// URLs, so passing the bundle
unconditionally is already correct for the hops SECURITY.md allows to stay
unencrypted.

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

    Needed wherever the assertion inspects a *constructed* SSLContext, or the
    call site now builds one via app.core.tls.get_ssl_context: both
    ssl.create_default_context and httpx load the bundle eagerly, so those
    tests cannot use a path that does not exist. Tests that assert only the
    raw constructor argument (httpx_verify()'s low-frequency call sites) use
    the CA_BUNDLE sentinel instead and never touch the filesystem. This
    certificate is generated per-test, never trusted by anything, and never
    leaves tmp_path.
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
    """Set settings.ca_bundle_path for the duration of a single test.

    Also resets app.core.tls's cached SSLContext, both before and after the
    setattr: a previous test may have already populated the cache from a
    different ca_bundle_path value, and this test's own value must not leak
    into whichever test runs next.
    """
    from app.core import tls as tls_module

    def _set(path: str | None):
        tls_module.reset_ssl_context_cache()
        monkeypatch.setattr(settings, "ca_bundle_path", path)

    yield _set
    tls_module.reset_ssl_context_cache()


@pytest.mark.unit
def test_ca_bundle_path_defaults_to_none_preserving_default_trust_store():
    """Unset means "use the system trust store" — local dev and docker-compose
    talk plain HTTP and must not be forced to load a bundle that isn't there.
    """
    assert settings.ca_bundle_path is None


# --- app.core.tls: shared verify= helper and SSLContext caching --------------


@pytest.mark.unit
def test_get_ssl_context_is_built_once_and_reused(ca_bundle_path, tmp_path):
    """The CA bundle PEM must be parsed at most once per process, not once
    per client construction — call sites that build a fresh httpx client per
    request (llm_client, doc_search_client, embedding_service) would
    otherwise re-parse the same file on every single call.
    """
    bundle = _write_throwaway_ca(tmp_path)
    ca_bundle_path(str(bundle))

    from app.core import tls as tls_module

    first_context = tls_module.get_ssl_context()
    second_context = tls_module.get_ssl_context()

    assert first_context is second_context


@pytest.mark.unit
def test_get_ssl_context_calls_create_default_context_only_once(ca_bundle_path, tmp_path):
    """Same guarantee as test_get_ssl_context_is_built_once_and_reused, proven
    from the other direction: ssl.create_default_context (the expensive PEM
    parse) must be invoked exactly once across two client-construction call
    sites, not once per call site.
    """
    bundle = _write_throwaway_ca(tmp_path)
    ca_bundle_path(str(bundle))

    from app.core import tls as tls_module

    with patch.object(
        tls_module.ssl, "create_default_context", wraps=tls_module.ssl.create_default_context
    ) as mock_create_context:
        tls_module.get_ssl_context()
        tls_module.get_ssl_context()

    assert mock_create_context.call_count == 1


@pytest.mark.unit
def test_httpx_verify_returns_bundle_path_when_set(ca_bundle_path):
    """httpx_verify() is the low-frequency-call-site helper (JWKS fetches,
    token exchange): it returns the raw path/bool httpx_verify has always
    returned, not an SSLContext.
    """
    ca_bundle_path(CA_BUNDLE)

    from app.core.tls import httpx_verify

    assert httpx_verify() == CA_BUNDLE


@pytest.mark.unit
def test_httpx_verify_returns_true_when_unset(ca_bundle_path):
    """With no bundle configured, httpx_verify() falls back to True (httpx's
    default trust store), not None, which would disable verification.
    """
    ca_bundle_path(None)

    from app.core.tls import httpx_verify

    assert httpx_verify() is True


# --- Site 1: doc-search MCP client (async) -----------------------------------


@pytest.mark.unit
async def test_doc_search_mcp_client_verifies_against_ca_bundle(ca_bundle_path, tmp_path):
    """Call site 1 — backend → doc-search over Streamable HTTP.

    If this client skips the bundle, every agent tool call fails once
    doc-search is behind TLS. This session is opened on every tool call, so
    the call site passes the cached SSLContext (app.core.tls.get_ssl_context)
    rather than the raw path — asserted here by identity against that same
    cache, since httpx>=0.28 keeps no readable path/string once a client is
    built from an SSLContext.
    """
    bundle = _write_throwaway_ca(tmp_path)
    ca_bundle_path(str(bundle))

    from app.core import tls as tls_module
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

    assert mock_client.call_args.kwargs["verify"] is tls_module.get_ssl_context()


@pytest.mark.unit
async def test_doc_search_mcp_client_uses_default_trust_store_when_unset(ca_bundle_path):
    """With no bundle configured the client must fall back to httpx's default
    trust store, not to a None that would disable verification. The
    call site still passes an SSLContext (not bare True) — get_ssl_context()
    always returns ssl.create_default_context(cafile=None) when unset, which
    is httpx's own default trust store, just pre-built.
    """
    ca_bundle_path(None)

    from app.core import tls as tls_module
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

    verify_arg = mock_client.call_args.kwargs["verify"]
    assert isinstance(verify_arg, ssl.SSLContext)
    assert verify_arg is tls_module.get_ssl_context()


@pytest.mark.unit
async def test_doc_search_mcp_client_keeps_redirect_following(ca_bundle_path, tmp_path):
    """Building the client directly (create_mcp_http_client takes no verify=)
    must not silently drop the MCP SDK's follow_redirects default.
    """
    bundle = _write_throwaway_ca(tmp_path)
    ca_bundle_path(str(bundle))

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
    Keycloak is behind TLS: the whole API becomes unauthenticated-only. This
    client is cached process-wide already (see _jwks_cache), so the call
    site uses httpx_verify() directly rather than get_ssl_context().
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


@pytest.mark.unit
def test_chat_openai_client_reuses_cached_ssl_context(
    ca_bundle_path, db_session, monkeypatch, tmp_path
):
    """get_llm_client builds two httpx clients (sync + async) on every call —
    both must reuse the same cached SSLContext, not each parse the bundle
    themselves.
    """
    bundle = _write_throwaway_ca(tmp_path)
    ca_bundle_path(str(bundle))

    from app.core import llm_client as llm_client_module
    from app.core import tls as tls_module

    monkeypatch.setattr(settings, "llm_provider", "llama-cpp")

    client = llm_client_module.get_llm_client(db_session)

    expected_context = tls_module.get_ssl_context()
    assert _ssl_context_of(client.http_client) is expected_context
    assert _ssl_context_of(client.http_async_client) is expected_context


# --- Site 5: Keycloak token exchange (async) ---------------------------------


@pytest.mark.unit
async def test_keycloak_token_exchange_verifies_against_ca_bundle(ca_bundle_path, db_session):
    """Call site 5 — backend → Keycloak token endpoint.

    Every authorization-code and refresh-token grant flows through here, so a
    missing bundle breaks login entirely rather than degrading one feature.
    This is a low-frequency, per-login call, so it uses httpx_verify()
    directly rather than get_ssl_context().

    Calls exchange_token directly (bypassing FastAPI's dependency
    injection), so it must supply its own db session and a minimal
    Request-like stand-in for the rate-limit check (issue #25) added ahead
    of the Keycloak call — a fresh db_session's bucket starts full, so this
    fake request never trips the limiter and reaches the mocked
    httpx.AsyncClient exactly as before.
    """
    ca_bundle_path(CA_BUNDLE)

    from app.api import auth as auth_api

    class _FakeClientAddress:
        host = "127.0.0.1"

    class _FakeRequest:
        client = _FakeClientAddress()
        headers: dict = {}

    with patch.object(auth_api.httpx, "AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.side_effect = RuntimeError("stop after construction")
        with pytest.raises(Exception):
            await auth_api.exchange_token(
                auth_api.TokenExchangeRequest(
                    grant_type="authorization_code",
                    code="some-code",
                    redirect_uri="https://frontend/callback",
                ),
                _FakeRequest(),
                db_session,
            )

    # Fails clearly here, rather than via a misleading AttributeError on
    # call_args below, if a future change ever makes the rate-limit check
    # trip before reaching httpx.AsyncClient - see this test's docstring.
    assert (
        mock_client.called
    ), "rate limiting must not have short-circuited before the Keycloak call"
    assert mock_client.call_args.kwargs["verify"] == CA_BUNDLE


# --- Site 6: embedding-server, synchronous client ----------------------------


@pytest.mark.unit
def test_embedding_client_verifies_against_ca_bundle(
    ca_bundle_path, db_session, monkeypatch, tmp_path
):
    """Call site 6 — backend → embedding-server for indexing.

    A synchronous httpx.Client, not an AsyncClient — easy to miss when
    grepping. Without the bundle, document indexing fails. This runs once per
    document chunk during ingestion, so the call site passes the cached
    SSLContext (app.core.tls.get_ssl_context) rather than the raw path.
    """
    bundle = _write_throwaway_ca(tmp_path)
    ca_bundle_path(str(bundle))

    from app.core import tls as tls_module
    from app.services import embedding_service

    monkeypatch.setattr(settings, "embedding_provider", "llama-cpp")

    with patch.object(embedding_service.httpx, "Client") as mock_client:
        mock_client.return_value.__enter__.side_effect = RuntimeError("stop after construction")
        with pytest.raises(RuntimeError):
            embedding_service.generate_embedding(db_session, "some text")

    assert mock_client.call_args.kwargs["verify"] is tls_module.get_ssl_context()
