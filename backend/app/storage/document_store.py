"""DocumentStore: the service boundary for uploaded knowledge-base files in
MinIO.

Every backend code path that reads or writes an uploaded document's bytes
goes through this class, not the raw Minio client - this is where object
keys get built via app.storage.object_keys (so per-user isolation can't be
bypassed by a call site constructing its own key) and where MinIO's
transient-vs-real error distinctions are normalized for callers like the
retention sweep.
"""

import logging
from typing import BinaryIO, Iterable

from minio import Minio
from minio.deleteobjects import DeleteObject
from minio.error import S3Error

from app.storage.object_keys import build_object_key, key_belongs_to_user

logger = logging.getLogger(__name__)


class DocumentStoreDeleteError(Exception):
    """Raised when a batched delete_many() call fails for one or more objects.

    The MinIO SDK's remove_objects() does not raise for per-object failures
    the way remove_object() does - it returns a generator of DeleteError
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
    """Upload, download, and delete uploaded document objects in MinIO."""

    def __init__(self, client: Minio, bucket: str):
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
        MinIO Helm chart or an air-gap setup script), so this is a
        first-run/local-dev convenience, not the primary provisioning path.

        bucket_exists() then make_bucket() is a check-then-act race: under
        concurrent first-uploads, two requests can both observe the bucket
        missing and both call make_bucket(). MinIO reports the loser of that
        race as S3Error(BucketAlreadyOwnedByYou), which means the bucket now
        exists (by the caller's own prior request) - treated as success
        rather than propagated, since the precondition upload() actually
        needs ("the bucket exists") now holds.
        """
        if not self._client.bucket_exists(self._bucket):
            try:
                self._client.make_bucket(self._bucket)
            except S3Error as e:
                if e.code != "BucketAlreadyOwnedByYou":
                    raise

        key = build_object_key(user_id=user_id, kb_id=kb_id, filename=filename)
        self._client.put_object(
            self._bucket,
            key,
            data,
            length,
            content_type=content_type,
        )
        return key

    def download(self, storage_key: str, *, user_id: str) -> bytes:
        """Fetch the raw bytes of a stored object, verifying user_id owns it.

        Always closes and releases the underlying HTTP response, per the
        MinIO SDK's documented usage pattern - an unreleased connection
        leaks a pooled socket on every call.
        """
        _verify_owns_storage_key(storage_key, user_id=user_id)

        response = self._client.get_object(self._bucket, storage_key)
        try:
            data: bytes = response.read()
            return data
        finally:
            response.close()
            response.release_conn()

    def delete(self, storage_key: str, *, user_id: str) -> None:
        """Delete one stored object, verifying user_id owns it.

        Idempotent: an object already gone (NoSuchKey) is treated as
        success, since the retention sweep may retry a purge whose DB
        transaction committed but whose object delete failed partway
        through. Any other S3 error still propagates.
        """
        _verify_owns_storage_key(storage_key, user_id=user_id)

        try:
            self._client.remove_object(self._bucket, storage_key)
        except S3Error as e:
            if e.code != "NoSuchKey":
                raise

    def delete_many(self, storage_keys: list[str]) -> None:
        """Delete multiple stored objects in one batched SDK call.

        A no-op for an empty list, matching the retention sweep's shape of
        calling this once per purge batch (see
        app.services.retention_service) - some batches purge no
        file-backed documents at all.

        Errors are drained fully so a lazily-evaluated generator's HTTP
        request actually completes; the MinIO SDK does not raise for
        individual per-object failures the way delete() does, so any
        collected DeleteError is logged (with the failing keys and reasons)
        and re-raised as DocumentStoreDeleteError - a partial failure here
        must not look like success to the caller.
        """
        if not storage_keys:
            return

        delete_objects: Iterable[DeleteObject] = (DeleteObject(key) for key in storage_keys)
        errors = list(self._client.remove_objects(self._bucket, delete_objects))
        if errors:
            logger.error(
                "delete_many failed for %d of %d object(s) in bucket %r: %s",
                len(errors),
                len(storage_keys),
                self._bucket,
                "; ".join(f"{e.name}: {e.code} ({e.message})" for e in errors),
            )
            raise DocumentStoreDeleteError(
                f"Failed to delete {len(errors)} of {len(storage_keys)} object(s) "
                f"from bucket {self._bucket!r}"
            )
