"""Unit tests for DocumentStore - the service wrapping MinIO for uploaded
knowledge-base documents.

MinIO itself is an external boundary (per AGENTS.md: mock only at the
service boundary, not business logic), so these tests mock the Minio
client instance and verify DocumentStore's own logic - bucket
ensure-exists-once behavior, key construction delegation, and how it
translates SDK calls - not MinIO's behavior itself. Real MinIO
interaction is covered by tests/integration (testcontainers).
"""

from io import BytesIO
from unittest.mock import MagicMock

import pytest
from minio.error import S3Error

from app.storage.document_store import DocumentStore


def _s3_error(code: str) -> S3Error:
    return S3Error(
        code=code,
        message="test",
        resource="/bucket/obj",
        request_id="req-1",
        host_id="host-1",
        response=MagicMock(),
    )


@pytest.mark.unit
def test_upload_creates_bucket_if_missing():
    """Test: upload() creates the configured bucket when it doesn't exist yet."""
    client = MagicMock()
    client.bucket_exists.return_value = False
    store = DocumentStore(client=client, bucket="documents")

    store.upload(
        user_id="user-1",
        kb_id="doc-1",
        filename="spec.pdf",
        data=BytesIO(b"file bytes"),
        length=10,
        content_type="application/pdf",
    )

    client.bucket_exists.assert_called_once_with("documents")
    client.make_bucket.assert_called_once_with("documents")


@pytest.mark.unit
def test_upload_skips_bucket_creation_if_it_exists():
    """Test: upload() does not attempt to recreate an existing bucket."""
    client = MagicMock()
    client.bucket_exists.return_value = True
    store = DocumentStore(client=client, bucket="documents")

    store.upload(
        user_id="user-1",
        kb_id="doc-1",
        filename="spec.pdf",
        data=BytesIO(b"file bytes"),
        length=10,
        content_type="application/pdf",
    )

    client.make_bucket.assert_not_called()


@pytest.mark.unit
def test_upload_writes_to_user_scoped_key():
    """Test: upload() stores the object under the user/doc-scoped key, not a
    bare filename - the structural user-isolation mechanism for object
    storage (see app.storage.object_keys).
    """
    client = MagicMock()
    client.bucket_exists.return_value = True
    store = DocumentStore(client=client, bucket="documents")

    key = store.upload(
        user_id="user-1",
        kb_id="doc-1",
        filename="spec.pdf",
        data=BytesIO(b"file bytes"),
        length=10,
        content_type="application/pdf",
    )

    assert key == "user-1/doc-1/spec.pdf"
    args, kwargs = client.put_object.call_args
    assert args[0] == "documents"
    assert args[1] == "user-1/doc-1/spec.pdf"
    assert kwargs["content_type"] == "application/pdf"


@pytest.mark.unit
def test_delete_removes_the_object():
    """Test: delete() removes exactly the given object from the bucket."""
    client = MagicMock()
    store = DocumentStore(client=client, bucket="documents")

    store.delete("user-1/doc-1/spec.pdf")

    client.remove_object.assert_called_once_with("documents", "user-1/doc-1/spec.pdf")


@pytest.mark.unit
def test_delete_is_idempotent_when_object_already_gone():
    """Test: deleting an object that MinIO reports as already-gone does not
    raise - retention sweeps must tolerate a prior partial failure (DB row
    purged, object delete retried) without erroring on the second attempt.
    """
    client = MagicMock()
    client.remove_object.side_effect = _s3_error("NoSuchKey")
    store = DocumentStore(client=client, bucket="documents")

    store.delete("user-1/doc-1/spec.pdf")  # must not raise


@pytest.mark.unit
def test_delete_reraises_other_s3_errors():
    """Test: a non-"already gone" S3 error still propagates - only the
    idempotent NoSuchKey case is swallowed.
    """
    client = MagicMock()
    client.remove_object.side_effect = _s3_error("AccessDenied")
    store = DocumentStore(client=client, bucket="documents")

    with pytest.raises(S3Error):
        store.delete("user-1/doc-1/spec.pdf")


@pytest.mark.unit
def test_delete_many_batches_across_multiple_keys():
    """Test: delete_many() passes every given key to the SDK's batch
    remove_objects call, for the retention sweep's batched-delete shape.
    """
    client = MagicMock()
    client.remove_objects.return_value = iter([])  # no errors
    store = DocumentStore(client=client, bucket="documents")

    store.delete_many(["user-1/doc-1/a.pdf", "user-1/doc-2/b.pdf"])

    args, _ = client.remove_objects.call_args
    assert args[0] == "documents"
    delete_object_list = list(args[1])
    assert [obj._name for obj in delete_object_list] == [
        "user-1/doc-1/a.pdf",
        "user-1/doc-2/b.pdf",
    ]


@pytest.mark.unit
def test_delete_many_with_no_keys_does_not_call_the_sdk():
    """Test: an empty key list is a no-op, not an SDK call with an empty
    iterable - avoids an unnecessary round-trip during a sweep that found
    nothing to purge.
    """
    client = MagicMock()
    store = DocumentStore(client=client, bucket="documents")

    store.delete_many([])

    client.remove_objects.assert_not_called()


@pytest.mark.unit
def test_download_returns_object_bytes():
    """Test: download() returns the raw bytes of the stored object and
    always releases the underlying HTTP connection back to the pool.
    """
    client = MagicMock()
    response = MagicMock()
    response.read.return_value = b"file bytes"
    client.get_object.return_value = response
    store = DocumentStore(client=client, bucket="documents")

    result = store.download("user-1/doc-1/spec.pdf")

    assert result == b"file bytes"
    client.get_object.assert_called_once_with("documents", "user-1/doc-1/spec.pdf")
    response.close.assert_called_once()
    response.release_conn.assert_called_once()
