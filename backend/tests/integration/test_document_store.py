"""Integration tests for DocumentStore against a real SeaweedFS S3 gateway.

Object storage is an external boundary (per AGENTS.md): these tests run
against a real SeaweedFS container via testcontainers, not a mock, so they
actually exercise the wire protocol the SDK speaks - bucket creation, object
upload/download/delete, and batch delete. Unit tests
(tests/unit/test_document_store.py) cover DocumentStore's own logic with a
mocked client; this file is the "does it actually work against the real
S3 server" check (issue #94 swapped MinIO for SeaweedFS; the SDK is still
the MinIO Python client, which speaks the generic S3 API).

Runs over plaintext (secure=False), matching how every other local/CI
service in this stack talks - see app.storage.object_storage_client's
scheme-derived secure flag and issue #17 (tracked follow-up to make local
dev TLS-by-default).
"""

import urllib.request
from io import BytesIO

import pytest
from minio import Minio
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_container_is_ready

from app.storage.document_store import DocumentStore

ACCESS_KEY = "test-access-key"
SECRET_KEY = "test-secret-key"
S3_PORT = 8333

# Keep in sync with docker-compose.yml's seaweedfs service and
# infra/helm/charts/seaweedfs/values.yaml: one pinned tag, never `latest`.
SEAWEEDFS_IMAGE = "chrislusf/seaweedfs:4.48"


@wait_container_is_ready()
def _wait_for_s3_gateway(container: DockerContainer) -> None:
    """Poll the gateway's /healthz until it answers 200 (raises until then)."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(S3_PORT)
    with urllib.request.urlopen(f"http://{host}:{port}/healthz", timeout=2) as response:
        assert response.status == 200


@pytest.fixture(scope="module")
def object_storage_container():
    """Start a real SeaweedFS server (master + volume + filer + S3 gateway
    in one process) for the duration of this test module.

    -volume.max=0 lets the volume server size its slot count from free disk
    instead of the default cap: SeaweedFS pre-allocates several volumes per
    bucket, and the fresh-bucket-per-test fixture below would otherwise
    exhaust the default slots partway through the module.
    """
    container = (
        DockerContainer(SEAWEEDFS_IMAGE)
        .with_env("AWS_ACCESS_KEY_ID", ACCESS_KEY)
        .with_env("AWS_SECRET_ACCESS_KEY", SECRET_KEY)
        .with_exposed_ports(S3_PORT)
        .with_command(f"server -dir=/data -volume.max=0 -s3 -s3.port={S3_PORT}")
    )
    container.start()
    _wait_for_s3_gateway(container)
    yield container
    container.stop()


@pytest.fixture
def document_store(object_storage_container):
    """A DocumentStore backed by the real SeaweedFS container, with a fresh
    per-test bucket so tests don't see each other's objects.
    """
    import uuid

    host = object_storage_container.get_container_host_ip()
    port = object_storage_container.get_exposed_port(S3_PORT)
    client = Minio(
        f"{host}:{port}",
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        secure=False,
    )
    bucket = f"test-{uuid.uuid4().hex[:12]}"
    return DocumentStore(client=client, bucket=bucket)


@pytest.mark.integration
def test_upload_then_download_round_trips_bytes(document_store):
    """Uploaded bytes come back unchanged on download."""
    key = document_store.upload(
        user_id="user-1",
        kb_id="doc-1",
        filename="spec.pdf",
        data=BytesIO(b"real file bytes"),
        length=len(b"real file bytes"),
        content_type="application/pdf",
    )

    result = document_store.download(key, user_id="user-1")

    assert result == b"real file bytes"


@pytest.mark.integration
def test_upload_creates_the_bucket_on_first_use(document_store):
    """The configured bucket doesn't need to exist beforehand."""
    document_store.upload(
        user_id="user-1",
        kb_id="doc-1",
        filename="notes.txt",
        data=BytesIO(b"hello"),
        length=5,
        content_type="text/plain",
    )

    assert document_store._client.bucket_exists(document_store._bucket)


@pytest.mark.integration
def test_delete_removes_the_object(document_store):
    """A deleted object is actually gone from the server, not just locally
    forgotten.
    """
    key = document_store.upload(
        user_id="user-1",
        kb_id="doc-1",
        filename="notes.txt",
        data=BytesIO(b"hello"),
        length=5,
        content_type="text/plain",
    )

    document_store.delete(key, user_id="user-1")

    with pytest.raises(Exception):
        document_store.download(key, user_id="user-1")


@pytest.mark.integration
def test_delete_many_removes_every_object(document_store):
    """A batched delete removes every given object, matching the retention
    sweep's batched-purge shape.
    """
    keys = [
        document_store.upload(
            user_id="user-1",
            kb_id=f"doc-{i}",
            filename="notes.txt",
            data=BytesIO(b"hello"),
            length=5,
            content_type="text/plain",
        )
        for i in range(3)
    ]

    document_store.delete_many(keys)

    for key in keys:
        with pytest.raises(Exception):
            document_store.download(key, user_id="user-1")


@pytest.mark.integration
def test_delete_is_idempotent_against_a_real_server(document_store):
    """Deleting an object twice does not raise - the retention sweep may
    retry a purge whose object delete already succeeded.
    """
    key = document_store.upload(
        user_id="user-1",
        kb_id="doc-1",
        filename="notes.txt",
        data=BytesIO(b"hello"),
        length=5,
        content_type="text/plain",
    )

    document_store.delete(key, user_id="user-1")
    document_store.delete(key, user_id="user-1")  # must not raise
