"""Unit tests for DocumentStore - the service wrapping object storage for
uploaded knowledge-base documents.

Object storage is an external boundary (per AGENTS.md: mock only at the
service boundary), so these tests drive a real boto3 S3 client whose HTTP
layer is replaced by botocore's Stubber: every request DocumentStore makes
is checked against the exact S3 operation and parameters expected, and
boto3 itself validates the parameters against the S3 API model - closer to
the wire than a MagicMock, without a server. Real server interaction is
covered by tests/integration (testcontainers, SeaweedFS).
"""

from io import BytesIO

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from app.storage.document_store import (
    DocumentStore,
    DocumentStoreAccessDeniedError,
    DocumentStoreDeleteError,
)

BUCKET = "documents"
KEY = "user-1/doc-1/spec.pdf"


@pytest.fixture
def stubbed():
    """A DocumentStore over a real S3 client with a Stubber attached.

    Every test must queue exactly the calls it expects; Stubber raises on
    any unexpected call, and assert_no_pending_responses() at teardown
    fails a test that expected a call DocumentStore never made.
    """
    client = boto3.client(
        "s3",
        endpoint_url="http://s3.test",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=Config(s3={"addressing_style": "path"}),
    )
    with Stubber(client) as stubber:
        yield DocumentStore(client=client, bucket=BUCKET), stubber
        stubber.assert_no_pending_responses()


def _expect_bucket_exists(stubber):
    stubber.add_response("head_bucket", {}, {"Bucket": BUCKET})


def _expect_put(stubber, key=KEY, content_type="application/pdf"):
    stubber.add_response(
        "put_object",
        {},
        {
            "Bucket": BUCKET,
            "Key": key,
            "Body": ANY,
            "ContentLength": 10,
            "ContentType": content_type,
        },
    )


def _upload(store, filename="spec.pdf"):
    return store.upload(
        user_id="user-1",
        kb_id="doc-1",
        filename=filename,
        data=BytesIO(b"file bytes"),
        length=10,
        content_type="application/pdf",
    )


@pytest.mark.unit
def test_upload_creates_bucket_if_missing(stubbed):
    store, stubber = stubbed
    stubber.add_client_error("head_bucket", "404", http_status_code=404)
    stubber.add_response("create_bucket", {}, {"Bucket": BUCKET})
    _expect_put(stubber)

    _upload(store)


@pytest.mark.unit
def test_upload_skips_bucket_creation_if_it_exists(stubbed):
    store, stubber = stubbed
    _expect_bucket_exists(stubber)
    _expect_put(stubber)

    _upload(store)


@pytest.mark.unit
def test_upload_succeeds_when_bucket_is_created_concurrently_by_another_request(stubbed):
    """Under concurrent first-uploads, two requests can both see the bucket
    missing and both try to create it; S3 answers the loser with
    BucketAlreadyOwnedByYou, which means the precondition upload() needs
    ("the bucket exists") now holds."""
    store, stubber = stubbed
    stubber.add_client_error("head_bucket", "404", http_status_code=404)
    stubber.add_client_error("create_bucket", "BucketAlreadyOwnedByYou", http_status_code=409)
    _expect_put(stubber)

    assert _upload(store) == KEY


@pytest.mark.unit
def test_upload_does_not_mask_a_bucket_check_that_failed_for_another_reason(stubbed):
    """A 403 from the bucket check (wrong credentials, missing permission) is
    not "the bucket doesn't exist" - it must surface, not trigger a create."""
    store, stubber = stubbed
    stubber.add_client_error("head_bucket", "403", http_status_code=403)

    with pytest.raises(ClientError):
        _upload(store)


@pytest.mark.unit
def test_upload_writes_to_user_scoped_key(stubbed):
    """The object lands under user_id/kb_id/filename, never a bare filename -
    the structural user-isolation mechanism for object storage (see
    app.storage.object_keys). The expected Key in _expect_put asserts it."""
    store, stubber = stubbed
    _expect_bucket_exists(stubber)
    _expect_put(stubber)

    assert _upload(store) == "user-1/doc-1/spec.pdf"


@pytest.mark.unit
def test_delete_removes_the_object(stubbed):
    store, stubber = stubbed
    stubber.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": KEY})

    store.delete(KEY, user_id="user-1")


@pytest.mark.unit
def test_delete_is_idempotent_when_object_already_gone(stubbed):
    """A retention sweep retrying a partially-failed purge must not error on
    an object that is already gone. S3 normally answers that delete with a
    plain 204, but a server reporting NoSuchKey is tolerated too."""
    store, stubber = stubbed
    stubber.add_client_error("delete_object", "NoSuchKey", http_status_code=404)

    store.delete(KEY, user_id="user-1")  # must not raise


@pytest.mark.unit
def test_delete_reraises_other_s3_errors(stubbed):
    store, stubber = stubbed
    stubber.add_client_error("delete_object", "AccessDenied", http_status_code=403)

    with pytest.raises(ClientError):
        store.delete(KEY, user_id="user-1")


@pytest.mark.unit
def test_delete_rejects_a_storage_key_not_owned_by_the_given_user(stubbed):
    """No request is queued: any SDK call would make the Stubber raise."""
    store, _ = stubbed

    with pytest.raises(DocumentStoreAccessDeniedError):
        store.delete(KEY, user_id="user-2")


@pytest.mark.unit
def test_download_rejects_a_storage_key_not_owned_by_the_given_user(stubbed):
    store, _ = stubbed

    with pytest.raises(DocumentStoreAccessDeniedError):
        store.download(KEY, user_id="user-2")


@pytest.mark.unit
def test_download_returns_object_bytes(stubbed):
    store, stubber = stubbed
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(BytesIO(b"file bytes"), 10)},
        {"Bucket": BUCKET, "Key": KEY},
    )

    assert store.download(KEY, user_id="user-1") == b"file bytes"


@pytest.mark.unit
def test_delete_many_sends_every_key_in_one_batched_request(stubbed):
    store, stubber = stubbed
    keys = ["user-1/doc-1/a.pdf", "user-1/doc-2/b.pdf"]
    stubber.add_response(
        "delete_objects",
        {},
        {"Bucket": BUCKET, "Delete": {"Objects": [{"Key": k} for k in keys], "Quiet": True}},
    )

    store.delete_many(keys)


@pytest.mark.unit
def test_delete_many_splits_into_requests_of_at_most_1000_keys(stubbed):
    """S3's DeleteObjects accepts at most 1000 keys per request (the previous
    SDK chunked internally; boto3 does not)."""
    store, stubber = stubbed
    keys = [f"user-1/doc-{i}/f.pdf" for i in range(1500)]
    for chunk in (keys[:1000], keys[1000:]):
        stubber.add_response(
            "delete_objects",
            {},
            {"Bucket": BUCKET, "Delete": {"Objects": [{"Key": k} for k in chunk], "Quiet": True}},
        )

    store.delete_many(keys)


@pytest.mark.unit
def test_delete_many_raises_when_the_server_reports_partial_failures(stubbed):
    """A batch delete reports per-object failures in its response body rather
    than raising. Silently dropping them would let the retention sweep purge
    the DB row while the object survives, with no record left to reconcile."""
    store, stubber = stubbed
    stubber.add_response(
        "delete_objects",
        {"Errors": [{"Key": "user-1/doc-1/a.pdf", "Code": "AccessDenied", "Message": "denied"}]},
        {
            "Bucket": BUCKET,
            "Delete": {
                "Objects": [{"Key": "user-1/doc-1/a.pdf"}, {"Key": "user-1/doc-2/b.pdf"}],
                "Quiet": True,
            },
        },
    )

    with pytest.raises(DocumentStoreDeleteError):
        store.delete_many(["user-1/doc-1/a.pdf", "user-1/doc-2/b.pdf"])


@pytest.mark.unit
def test_delete_many_with_no_keys_does_not_call_the_sdk(stubbed):
    store, _ = stubbed

    store.delete_many([])
