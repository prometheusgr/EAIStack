"""Unit tests for the object-storage client wrapper - TDD discipline.

Object storage itself is an external boundary (per AGENTS.md, integration
tests for it need a real server via testcontainers, not mocks) - these unit
tests only cover the deterministic logic that doesn't require a live server:
how the boto3 S3 client is constructed (endpoint, TLS verification, path-style
addressing) and how object keys are built for user isolation.
"""

from unittest.mock import patch

import pytest

from app.storage.object_keys import build_object_key
from app.storage.object_storage_client import build_object_storage_client


def _settings(mock_settings, *, url, ca_bundle_path=None):
    mock_settings.object_storage_url = url
    mock_settings.object_storage_access_key = "access-123"
    mock_settings.object_storage_secret_key = "secret-456"
    mock_settings.ca_bundle_path = ca_bundle_path


@pytest.mark.unit
def test_client_targets_the_configured_endpoint_with_its_scheme():
    """Test: the https:// URL (the Helm-deployed SeaweedFS, which serves TLS
    only) reaches boto3 unchanged - the scheme decides TLS, the same "let the
    URL decide" rule every other outbound client here follows (issue #13).
    """
    with patch("app.storage.object_storage_client.settings") as mock_settings:
        _settings(mock_settings, url="https://storage.internal:8333")

        client = build_object_storage_client()

    assert client.meta.endpoint_url == "https://storage.internal:8333"


@pytest.mark.unit
def test_client_uses_path_style_addressing():
    """Test: buckets are addressed as https://host/bucket/key, not
    https://bucket.host/key. SeaweedFS (and any in-cluster S3 server reached
    by a Service name) has no per-bucket DNS, so virtual-host addressing
    would send every request to a hostname that doesn't resolve.
    """
    with patch("app.storage.object_storage_client.settings") as mock_settings:
        _settings(mock_settings, url="http://seaweedfs:8333")

        client = build_object_storage_client()

    assert client.meta.config.s3["addressing_style"] == "path"


@pytest.mark.unit
def test_client_passes_credentials():
    with (
        patch("app.storage.object_storage_client.boto3.client") as mock_client,
        patch("app.storage.object_storage_client.settings") as mock_settings,
    ):
        _settings(mock_settings, url="https://storage.internal:8333")

        build_object_storage_client()

    _, kwargs = mock_client.call_args
    assert kwargs["aws_access_key_id"] == "access-123"
    assert kwargs["aws_secret_access_key"] == "secret-456"


@pytest.mark.unit
def test_client_verifies_tls_against_the_internal_ca_bundle_when_configured():
    """Test: with ca_bundle_path set, the client verifies the server against
    that bundle - the same internal CA every other outbound client trusts.
    A client on the default trust store would reject the cluster's
    cert-manager-issued certificate, or worse, tempt someone to turn
    verification off (issue #13).
    """
    with (
        patch("app.storage.object_storage_client.boto3.client") as mock_client,
        patch("app.storage.object_storage_client.settings") as mock_settings,
    ):
        _settings(
            mock_settings,
            url="https://storage.internal:8333",
            ca_bundle_path="/etc/ssl/certs/internal-ca.crt",
        )

        build_object_storage_client()

    _, kwargs = mock_client.call_args
    assert kwargs["verify"] == "/etc/ssl/certs/internal-ca.crt"


@pytest.mark.unit
def test_client_without_a_ca_bundle_keeps_default_verification_on():
    """Test: no ca_bundle_path means the default trust store - never
    verify=False. Verification is only ever narrowed to a specific CA, not
    disabled.
    """
    with (
        patch("app.storage.object_storage_client.boto3.client") as mock_client,
        patch("app.storage.object_storage_client.settings") as mock_settings,
    ):
        _settings(mock_settings, url="https://storage.internal:8333")

        build_object_storage_client()

    _, kwargs = mock_client.call_args
    assert kwargs["verify"] is True


@pytest.mark.unit
def test_a_schemeless_url_is_treated_as_plaintext_http():
    """Test: a bare host:port keeps meaning what it meant with the previous
    SDK - a plaintext connection (local dev only; every TLS deployment
    configures https:// explicitly).
    """
    with patch("app.storage.object_storage_client.settings") as mock_settings:
        _settings(mock_settings, url="storage.internal:8333")

        client = build_object_storage_client()

    assert client.meta.endpoint_url == "http://storage.internal:8333"


# --- Object key construction (user isolation) --------------------------------


@pytest.mark.unit
def test_build_object_key_scopes_by_user_and_document():
    """Test: object keys are namespaced as user_id/kb_id/filename.

    This is the structural user-isolation mechanism for stored objects (see
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
