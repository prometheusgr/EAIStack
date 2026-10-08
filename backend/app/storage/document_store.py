"""DocumentStore: the service boundary for uploaded knowledge-base files in
object storage.

Every backend code path that reads or writes an uploaded document's bytes
goes through this class, not the raw S3 client - this is where object
keys get built via app.storage.object_keys (so per-user isolation can't be
bypassed by a call site constructing its own key) and where the S3 server's
transient-vs-real error distinctions are normalized for callers like the
retention sweep.
"""

import logging
from typing import BinaryIO

from botocore.client import BaseClient
from botocore.exceptions import ClientError

from app.storage.object_keys import build_object_key, key_belongs_to_user

logger = logging.getLogger(__name__)

# S3's DeleteObjects accepts at most 1000 keys per request (an API limit,
# not a tunable).
_MAX_KEYS_PER_DELETE_REQUEST = 1000


class DocumentStoreDeleteError(Exception):
    """Raised when a batched delete_many() call fails for one or more objects.

    S3's DeleteObjects does not raise for per-object failures the way
    DeleteObject does - it reports them in the response's `Errors` list
    instead, which is easy to silently discard. Raising here surfaces the
    failure to the caller (the retention sweep) so a partially-failed purge
    is a loud error, not a silently orphaned object with no way to detect or
    reconcile it later.
    """


class DocumentStoreAccessDeniedError(Exception):
    """Raised when a caller's user_id does not own the given storage_key.

    Mirrors how a repository signals an ownership violation structurally
    (see docs/REPOSITORY_PATTERN.md) - the difference here is that a
    repository query simply can't return another user's row, whereas
    download()/delete() take a bare storage_key string and so must verify
    ownership explicitly. Raising (rather than silently no-op'ing) matches
    this module's own DocumentStoreDeleteError precedent: a caller passing
    a storage_key it shouldn't have access to is a loud programming error,
    not a routine "not found".
    """


def _verify_owns_storage_key(storage_key: str, *, user_id: str) -> None:
    """Raise DocumentStoreAccessDeniedError unless user_id owns storage_key."""
    if not key_belongs_to_user(storage_key, user_id=user_id):
        raise DocumentStoreAccessDeniedError(
            f"user_id {user_id!r} does not own storage_key {storage_key!r}"
        )


class DocumentStore:
    """Upload, download, and delete uploaded document objects in object storage."""

    def __init__(self, client: BaseClient, bucket: str):
        self._client = client
        self._bucket = bucket

    def upload(
        self,
        *,
        user_id: str,
        kb_id: str,
        filename: str,
        data: BinaryIO,
        length: int,
        content_type: str,
    ) -> str:
        """Store an uploaded file's bytes and return its object key.

        Ensures the configured bucket exists before writing - the bucket is
        expected to already exist in every real deployment (created by the
        SeaweedFS Helm chart or an air-gap setup script), so this is a
        first-run/local-dev convenience, not the primary provisioning path.

        Checking and then creating is a check-then-act race: under concurrent
        first-uploads, two requests can both observe the bucket missing and
        both create it. The S3 server answers the loser with
        BucketAlreadyOwnedByYou, which means the bucket now exists (by the
        caller's own prior request) - treated as success rather than
        propagated, since the precondition upload() actually needs ("the
        bucket exists") now holds.
        """
        self._ensure_bucket_exists()

        key = build_object_key(user_id=user_id, kb_id=kb_id, filename=filename)
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentLength=length,
            ContentType=content_type,
        )
        return key

    def _ensure_bucket_exists(self) -> None:
        """Create the bucket if a HEAD on it reports 404.

        Any other failure (403 for bad credentials or a missing permission,
        a 5xx) propagates: it doesn't mean "missing", and creating a bucket
        in response to it would mask the real problem.
        """
        try:
            self._client.head_bucket(Bucket=self._bucket)
            return
        except ClientError as e:
            if _error_code(e) not in ("404", "NoSuchBucket", "NotFound"):
                raise

        try:
            self._client.create_bucket(Bucket=self._bucket)
        except ClientError as e:
            if _error_code(e) != "BucketAlreadyOwnedByYou":
                raise

    def download(self, storage_key: str, *, user_id: str) -> bytes:
        """Fetch the raw bytes of a stored object, verifying user_id owns it.

        Always closes the response body stream, so its pooled connection is
        returned even if reading fails partway.
        """
        _verify_owns_storage_key(storage_key, user_id=user_id)

        body = self._client.get_object(Bucket=self._bucket, Key=storage_key)["Body"]
        try:
            data: bytes = body.read()
            return data
        finally:
            body.close()

    def delete(self, storage_key: str, *, user_id: str) -> None:
        """Delete one stored object, verifying user_id owns it.

        Idempotent: an object already gone is treated as success, since the
        retention sweep may retry a purge whose DB transaction committed but
        whose object delete failed partway through. S3 answers that delete
        with a plain 204; a server that reports NoSuchKey instead is
        tolerated the same way. Any other S3 error still propagates.
        """
        _verify_owns_storage_key(storage_key, user_id=user_id)

        try:
            self._client.delete_object(Bucket=self._bucket, Key=storage_key)
        except ClientError as e:
            if _error_code(e) != "NoSuchKey":
                raise

    def delete_many(self, storage_keys: list[str]) -> None:
        """Delete multiple stored objects with batched DeleteObjects requests.

        A no-op for an empty list, matching the retention sweep's shape of
        calling this once per purge batch (see
        app.services.retention_service) - some batches purge no
        file-backed documents at all. Keys are sent in requests of at most
        _MAX_KEYS_PER_DELETE_REQUEST, S3's per-request limit.

        Quiet mode: the response lists only failures. Every failure across
        all requests is logged (with the failing keys and reasons) and
        raised as DocumentStoreDeleteError - a partial failure here must not
        look like success to the caller.
        """
        if not storage_keys:
            return

        errors: list[dict] = []
        for start in range(0, len(storage_keys), _MAX_KEYS_PER_DELETE_REQUEST):
            chunk = storage_keys[start : start + _MAX_KEYS_PER_DELETE_REQUEST]
            response = self._client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
            )
            errors.extend(response.get("Errors", []))

        if errors:
            logger.error(
                "delete_many failed for %d of %d object(s) in bucket %r: %s",
                len(errors),
                len(storage_keys),
                self._bucket,
                "; ".join(f"{e.get('Key')}: {e.get('Code')} ({e.get('Message')})" for e in errors),
            )
            raise DocumentStoreDeleteError(
                f"Failed to delete {len(errors)} of {len(storage_keys)} object(s) "
                f"from bucket {self._bucket!r}"
            )


def _error_code(error: ClientError) -> str:
    """The S3 error code of a ClientError ("NoSuchKey", "404", ...)."""
    return str(error.response.get("Error", {}).get("Code", ""))
