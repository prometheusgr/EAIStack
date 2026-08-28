"""Unit tests for build_object_key - the structural user-isolation mechanism
for MinIO object paths (see app.storage.object_keys module docstring).

Covers the path-traversal guard specifically: it must reject real traversal
attempts while not rejecting a filename that merely contains the substring
".." as part of a legitimate name (e.g. "report..final.pdf").
"""

import pytest

from app.storage.object_keys import build_object_key


@pytest.mark.unit
def test_build_object_key_returns_user_scoped_path():
    """Test: the key is "{user_id}/{kb_id}/{filename}"."""
    key = build_object_key(user_id="user-1", kb_id="doc-1", filename="spec.pdf")

    assert key == "user-1/doc-1/spec.pdf"


@pytest.mark.unit
def test_build_object_key_rejects_empty_filename():
    """Test: an empty-string filename is rejected - distinct from filename
    being None, which FastAPI's own request validation already rejects
    before this function is ever reached for an upload.
    """
    with pytest.raises(ValueError):
        build_object_key(user_id="user-1", kb_id="doc-1", filename="")


@pytest.mark.unit
@pytest.mark.parametrize(
    "filename",
    [
        "report..final.pdf",
        "notes...txt",
        "..hidden-file.txt",
        "archive..2024..txt",
    ],
)
def test_build_object_key_allows_filenames_containing_literal_dot_dot(filename):
    """Test: a filename that merely contains the substring ".." (not a
    "../"-style path-traversal segment) is a legitimate filename and must
    not be rejected.
    """
    key = build_object_key(user_id="user-1", kb_id="doc-1", filename=filename)

    assert key == f"user-1/doc-1/{filename}"


@pytest.mark.unit
@pytest.mark.parametrize(
    "filename",
    [
        "../../etc/passwd",
        "..\\..\\secrets",
        "../secret.txt",
        "..",
        "foo/../../bar.txt",
    ],
)
def test_build_object_key_rejects_path_traversal_attempts(filename):
    """Test: an actual path-traversal filename (a ".." path segment, forward
    or backward slash) is still rejected - the substring-widening fix must
    not weaken this guarantee.
    """
    with pytest.raises(ValueError):
        build_object_key(user_id="user-1", kb_id="doc-1", filename=filename)


@pytest.mark.unit
@pytest.mark.parametrize("filename", ["a/b.txt", "a\\b.txt"])
def test_build_object_key_rejects_path_separators(filename):
    """Test: a filename containing a path separator is rejected even without
    a ".." segment - it would still let the caller nest the key under an
    attacker-chosen subpath within the user's own prefix.
    """
    with pytest.raises(ValueError):
        build_object_key(user_id="user-1", kb_id="doc-1", filename=filename)
