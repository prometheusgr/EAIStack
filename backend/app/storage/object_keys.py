"""MinIO object key construction for knowledge-base documents.

This is the structural user-isolation mechanism for object storage,
equivalent in purpose to a repository's `user_id` filter (see
docs/REPOSITORY_PATTERN.md) but for MinIO rather than a DB table: every
object key is namespaced under its owning user's id, and this is the only
function in the codebase that is allowed to build one. A caller with a
user_id and a kb_id can never construct a key outside that user's prefix.
"""


def build_object_key(*, user_id: str, kb_id: str, filename: str) -> str:
    """Build the MinIO object key for one uploaded document.

    Returns "{user_id}/{kb_id}/{filename}". Rejects a filename that is
    empty or contains a path separator (or "..") - either would let the
    resulting key climb out of the user_id/kb_id prefix that keeps one
    user's objects unreachable from another's.
    """
    if not filename:
        raise ValueError("filename must not be empty")

    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(f"filename must not contain path separators: {filename!r}")

    return f"{user_id}/{kb_id}/{filename}"
