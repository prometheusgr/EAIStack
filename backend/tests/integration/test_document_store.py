"""Integration tests for DocumentStore against a real MinIO server.

MinIO is an external boundary (per AGENTS.md): these tests run against a
real MinIO container via testcontainers, not a mock, so they actually
exercise the wire protocol the SDK speaks - bucket creation, object
upload/download/delete, and batch delete. Unit tests
(tests/unit/test_document_store.py) cover DocumentStore's own logic with a
mocked client; this file is the "does it actually work against MinIO"
check.

Runs over plaintext (secure=False), matching how every other local/CI
service in this stack talks - see app.storage.minio_client's
scheme-derived secure flag and issue #17 (tracked follow-up to make local
dev TLS-by-default).
"""

from io import BytesIO

import pytest
from minio import Minio
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from app.storage.document_store import DocumentStore

MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"


@pytest.fixture(scope="module")
def minio_container():
    """Start a real MinIO server for the duration of this test module."""
    container = (
        DockerContainer("minio/minio:latest")
        .with_env("MINIO_ROOT_USER", MINIO_ACCESS_KEY)
        .with_env("MINIO_ROOT_PASSWORD", MINIO_SECRET_KEY)
        .with_exposed_ports(9000)
        .with_command("server /data")
    )
    container.start()
    wait_for_logs(container, "API:", timeout=30)
    yield container
    container.stop()


@pytest.fixture
def document_store(minio_container):
    """A DocumentStore backed by the real MinIO container, with a fresh
    per-test bucket so tests don't see each other's objects.
    """
    import uuid

    host = minio_container.get_container_host_ip()
    port = minio_container.get_exposed_port(9000)
    client = Minio(
        f"{host}:{port}",
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
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

    result = document_store.download(key)

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

    document_store.delete(key)

    with pytest.raises(Exception):
        document_store.download(key)


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
            document_store.download(key)


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

    document_store.delete(key)
    document_store.delete(key)  # must not raise
