"""Unit tests for the MinIO client wrapper - TDD discipline.

MinIO itself is an external boundary (per AGENTS.md, integration tests for
it need a real MinIO via testcontainers, not mocks) - these unit tests only
cover the deterministic logic that doesn't require a live server: how the
client is constructed (secure=True, CA bundle wiring) and how object keys
are built for user isolation.
"""

from unittest.mock import patch

import pytest

from app.storage.minio_client import build_minio_client
from app.storage.object_keys import build_object_key


@pytest.mark.unit
def test_build_minio_client_uses_secure_true_for_an_https_url():
    """Test: an https:// minio_url (the Helm-deployed production MinIO,
    Phase 5) produces a client with secure=True - the compliant default
    for every real deployment, matching how the Helm chart already fronts
    MinIO with TLS ahead of any client that talks to it (issue #13).
    """
    with patch("app.storage.minio_client.Minio") as mock_minio, patch(
        "app.storage.minio_client.settings"
    ) as mock_settings:
        mock_settings.minio_url = "https://minio.internal:9000"
        mock_settings.minio_access_key = "access-123"
        mock_settings.minio_secret_key = "secret-456"
        mock_settings.ca_bundle_path = None

        build_minio_client()

        _, kwargs = mock_minio.call_args
        assert kwargs["secure"] is True


@pytest.mark.unit
def test_build_minio_client_uses_secure_false_for_a_plaintext_url():
    """Test: an http:// minio_url (docker-compose's local MinIO, which runs
    plaintext like every other service in that stack) produces a client
    with secure=False - the same "let the URL decide" rule httpx-based
    clients in this codebase already follow (see app.core.tls), applied to
    the MinIO SDK's separate secure= flag since its `endpoint` has no
    scheme of its own to sniff.
    """
    with patch("app.storage.minio_client.Minio") as mock_minio, patch(
        "app.storage.minio_client.settings"
    ) as mock_settings:
        mock_settings.minio_url = "http://minio:9000"
        mock_settings.minio_access_key = "access-123"
        mock_settings.minio_secret_key = "secret-456"
        mock_settings.ca_bundle_path = None

        build_minio_client()

        _, kwargs = mock_minio.call_args
        assert kwargs["secure"] is False


@pytest.mark.unit
def test_build_minio_client_passes_endpoint_and_credentials():
    """Test: the client is constructed from settings, not hardcoded values."""
    with patch("app.storage.minio_client.Minio") as mock_minio, patch(
        "app.storage.minio_client.settings"
    ) as mock_settings:
        mock_settings.minio_url = "https://minio.internal:9000"
        mock_settings.minio_access_key = "access-123"
        mock_settings.minio_secret_key = "secret-456"
        mock_settings.ca_bundle_path = None

        build_minio_client()

        args, kwargs = mock_minio.call_args
        assert args[0] == "minio.internal:9000"
        assert kwargs["access_key"] == "access-123"
        assert kwargs["secret_key"] == "secret-456"


@pytest.mark.unit
def test_build_minio_client_strips_scheme_from_endpoint():
    """Test: a configured https:// URL is reduced to a bare host:port.

    The Minio SDK's `endpoint` argument is host:port, not a full URL - if
    settings.minio_url ever carries a scheme (matching the pattern of
    llm_url/embedding_url elsewhere in Settings), passing it through
    unstripped would fail at connection time.
    """
    with patch("app.storage.minio_client.Minio") as mock_minio, patch(
        "app.storage.minio_client.settings"
    ) as mock_settings:
        mock_settings.minio_url = "https://minio.internal:9000"
        mock_settings.minio_access_key = "access-123"
        mock_settings.minio_secret_key = "secret-456"
        mock_settings.ca_bundle_path = None

        build_minio_client()

        args, _ = mock_minio.call_args
        assert args[0] == "minio.internal:9000"


@pytest.mark.unit
def test_build_minio_client_wires_ca_bundle_when_configured():
    """Test: when ca_bundle_path is set, the client's http_client trusts it.

    A client written against plaintext or the default trust store would
    silently undo Phase 5's deliberate TLS-ahead-of-client rollout - see
    issue #13. This asserts the CA bundle path actually reaches the
    underlying PoolManager's ca_certs, not just that some http_client is
    passed.
    """
    with patch("app.storage.minio_client.Minio") as mock_minio, patch(
        "app.storage.minio_client.settings"
    ) as mock_settings:
        mock_settings.minio_url = "https://minio.internal:9000"
        mock_settings.minio_access_key = "access-123"
        mock_settings.minio_secret_key = "secret-456"
        mock_settings.ca_bundle_path = "/etc/ssl/certs/internal-ca.crt"

        build_minio_client()

        _, kwargs = mock_minio.call_args
        http_client = kwargs["http_client"]
        assert http_client.connection_pool_kw["ca_certs"] == "/etc/ssl/certs/internal-ca.crt"


@pytest.mark.unit
def test_build_minio_client_no_ca_bundle_uses_default_trust_store():
    """Test: with no ca_bundle_path configured, no explicit http_client is
    forced - the SDK falls back to its own default trust store, matching
    local dev / docker-compose (which talk plain HTTP over the docker
    network and don't have a CA bundle mounted).
    """
    with patch("app.storage.minio_client.Minio") as mock_minio, patch(
        "app.storage.minio_client.settings"
    ) as mock_settings:
        mock_settings.minio_url = "minio.internal:9000"
        mock_settings.minio_access_key = "access-123"
        mock_settings.minio_secret_key = "secret-456"
        mock_settings.ca_bundle_path = None

        build_minio_client()

        _, kwargs = mock_minio.call_args
        assert kwargs.get("http_client") is None


# --- Object key construction (user isolation) --------------------------------


@pytest.mark.unit
def test_build_object_key_scopes_by_user_and_document():
    """Test: object keys are namespaced as user_id/kb_id/filename.

    This is the structural user-isolation mechanism for MinIO objects (see
    docs/REPOSITORY_PATTERN.md's ownership pattern, applied here to object
    storage instead of a DB table): a caller can never construct a key
    that reaches into another user's prefix without also supplying that
    user's user_id.
    """
    key = build_object_key(user_id="user-123", kb_id="doc-abc", filename="spec.pdf")
    assert key == "user-123/doc-abc/spec.pdf"


@pytest.mark.unit
def test_build_object_key_rejects_path_traversal_in_filename():
    """Test: a filename containing path separators can't escape the
    user/document prefix (e.g. an uploaded file named "../../other-user/x").
    """
    with pytest.raises(ValueError):
        build_object_key(user_id="user-123", kb_id="doc-abc", filename="../../etc/passwd")


@pytest.mark.unit
def test_build_object_key_rejects_empty_filename():
    """Test: an empty filename is rejected rather than producing a key
    ending in a bare trailing slash.
    """
    with pytest.raises(ValueError):
        build_object_key(user_id="user-123", kb_id="doc-abc", filename="")
