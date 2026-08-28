"""MinIO object key construction for knowledge-base documents.

This is the structural user-isolation mechanism for object storage,
equivalent in purpose to a repository's `user_id` filter (see
docs/REPOSITORY_PATTERN.md) but for MinIO rather than a DB table: every
object key is namespaced under its owning user's id, and this is the only
function in the codebase that is allowed to build one. A caller with a
user_id and a kb_id can never construct a key outside that user's prefix.
"""

import posixpath


def build_object_key(*, user_id: str, kb_id: str, filename: str) -> str:
    """Build the MinIO object key for one uploaded document.

    Returns "{user_id}/{kb_id}/{filename}". Rejects a filename that is
    empty, contains a path separator, or has a ".." path *segment* - either
    would let the resulting key climb out of the user_id/kb_id prefix that
    keeps one user's objects unreachable from another's.

    Deliberately checks for a ".." *segment* (via PurePosixPath, after
    normalizing "\\" to "/") rather than the substring "..": a legitimate
    filename like "report..final.pdf" contains ".." as a substring but is
    not a traversal attempt, and must not be rejected.
    """
    if not filename:
        raise ValueError("filename must not be empty")

    if "/" in filename or "\\" in filename:
        raise ValueError(f"filename must not contain path separators: {filename!r}")

    if posixpath.normpath(filename) != filename or filename == "..":
        raise ValueError(f"filename must not be a path-traversal segment: {filename!r}")

    return f"{user_id}/{kb_id}/{filename}"


def key_belongs_to_user(storage_key: str, *, user_id: str) -> bool:
    """Check whether `storage_key` was built for `user_id`.

    The reciprocal of build_object_key: since every key is namespaced
    "{user_id}/{kb_id}/{filename}", ownership can be verified by checking
    the key's leading path segment against the caller's own user_id - the
    same structural check a repository makes by filtering a query on
    user_id (see docs/REPOSITORY_PATTERN.md), applied to a MinIO object
    path instead of a database row.
    """
    return storage_key.startswith(f"{user_id}/")
