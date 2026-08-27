"""DocumentStore: the service boundary for uploaded knowledge-base files in
MinIO.

Every backend code path that reads or writes an uploaded document's bytes
goes through this class, not the raw Minio client - this is where object
keys get built via app.storage.object_keys (so per-user isolation can't be
bypassed by a call site constructing its own key) and where MinIO's
transient-vs-real error distinctions are normalized for callers like the
retention sweep.
"""

from typing import BinaryIO, Iterable

from minio import Minio
from minio.deleteobjects import DeleteObject
from minio.error import S3Error

from app.storage.object_keys import build_object_key


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
        """
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

        key = build_object_key(user_id=user_id, kb_id=kb_id, filename=filename)
        self._client.put_object(
            self._bucket,
            key,
            data,
            length,
            content_type=content_type,
        )
        return key

    def download(self, storage_key: str) -> bytes:
        """Fetch the raw bytes of a stored object.

        Always closes and releases the underlying HTTP response, per the
        MinIO SDK's documented usage pattern - an unreleased connection
        leaks a pooled socket on every call.
        """
        response = self._client.get_object(self._bucket, storage_key)
        try:
            data: bytes = response.read()
            return data
        finally:
            response.close()
            response.release_conn()

    def delete(self, storage_key: str) -> None:
        """Delete one stored object.

        Idempotent: an object already gone (NoSuchKey) is treated as
        success, since the retention sweep may retry a purge whose DB
        transaction committed but whose object delete failed partway
        through. Any other S3 error still propagates.
        """
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
        individual per-object failures the way delete() does; a
        best-effort sweep still succeeds if some file was already gone.
        """
        if not storage_keys:
            return

        delete_objects: Iterable[DeleteObject] = (DeleteObject(key) for key in storage_keys)
        errors = self._client.remove_objects(self._bucket, delete_objects)
        list(errors)
