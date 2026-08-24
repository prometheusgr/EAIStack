"""TLS trust plumbing: doc-search's outbound HTTP clients verify against the CA bundle.

The doc-search pod mounts the internal CA's ca.crt the same way the backend does
(Phase 5, Decision 2), and points every outbound client at it. The verify=
expression itself lives in one place, app.tls: `httpx_verify()` returns
`settings.ca_bundle_path or True`, and `get_ssl_context()` returns a
process-wide cached ssl.SSLContext for call sites that build a new httpx
client per call (avoiding a re-parse of the CA bundle PEM file on every one
of those calls). One uniform rule, no URL-scheme sniffing: httpx ignores
`verify` for plaintext http:// URLs, so passing the bundle unconditionally is
already correct for hops that stay unencrypted.

Each test asserts the *constructor argument* rather than an attribute on the
finished client, because httpx>=0.28 builds its SSLContext eagerly and retains
no readable `verify`.

Covers call sites 3 and 7 of Decision 2's seven-site inventory; the backend
owns the other five in its own suite.
"""

import datetime
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import app.auth as auth_module
import app.search as search_module
from app.config import settings

CA_BUNDLE = "/etc/ssl/eaistack/ca.crt"


def _write_throwaway_ca(tmp_path):
    """Write a self-signed CA to a temp file and return its path.

    Needed only where the assertion inspects a *constructed* SSLContext:
    ssl.create_default_context loads the bundle eagerly, so those tests
    cannot use a path that does not exist. This certificate is generated
    per-test, never trusted by anything, and never leaves tmp_path.
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

    Also resets app.tls's cached SSLContext, both before and after the
    setattr: a previous test may have already populated the cache from a
    different ca_bundle_path value, and this test's own value must not leak
    into whichever test runs next.
    """
    from app import tls as tls_module

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


# --- app.tls: shared verify= helper and SSLContext caching -------------------


@pytest.mark.unit
def test_get_ssl_context_is_built_once_and_reused(ca_bundle_path, tmp_path):
    """The CA bundle PEM must be parsed at most once per process, not once
    per client construction — generate_query_embedding builds a fresh httpx
    client on every knowledge-base query and would otherwise re-parse the
    same file on every single query.
    """
    bundle = _write_throwaway_ca(tmp_path)
    ca_bundle_path(str(bundle))

    from app import tls as tls_module

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

    from app import tls as tls_module

    with patch.object(
        tls_module.ssl, "create_default_context", wraps=tls_module.ssl.create_default_context
    ) as mock_create_context:
        tls_module.get_ssl_context()
        tls_module.get_ssl_context()

    assert mock_create_context.call_count == 1


@pytest.mark.unit
def test_httpx_verify_returns_bundle_path_when_set(ca_bundle_path):
    """httpx_verify() is the low-frequency-call-site helper (the already-
    cached JWKS client): it returns the raw path/bool it has always
    returned, not an SSLContext.
    """
    ca_bundle_path(CA_BUNDLE)

    from app.tls import httpx_verify

    assert httpx_verify() == CA_BUNDLE


@pytest.mark.unit
def test_httpx_verify_returns_true_when_unset(ca_bundle_path):
    """With no bundle configured, httpx_verify() falls back to True (httpx's
    default trust store), not None, which would disable verification.
    """
    ca_bundle_path(None)

    from app.tls import httpx_verify

    assert httpx_verify() is True


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
def test_query_embedding_client_verifies_against_ca_bundle(ca_bundle_path, tmp_path, monkeypatch):
    """Call site 7 — doc-search → embedding-server at query time.

    A synchronous httpx.Client, not an AsyncClient — easy to miss when
    grepping. Without the bundle, every knowledge-base query fails. This
    runs on every knowledge-base query, so the call site passes the cached
    SSLContext (app.tls.get_ssl_context) rather than the raw path.
    """
    bundle = _write_throwaway_ca(tmp_path)
    ca_bundle_path(str(bundle))

    from app import tls as tls_module

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

    assert mock_client.call_args.kwargs["verify"] is tls_module.get_ssl_context()
