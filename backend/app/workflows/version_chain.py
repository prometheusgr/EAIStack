"""Tamper evidence for the workflow version store (issue #83).

Every stored workflow version records a SHA-256 of its YAML text and a
chain hash binding that content to its position in its workflow's
history: the previous version's chain hash, its own sequence number, who
wrote it, when, and the change note they gave. Rewriting any version's
content or attribution directly in the database (bypassing
WorkflowVersionRepository, which has no update method at all) breaks every
chain hash from that version onward, and verify_chain names the first one
that no longer matches.

This is tamper *evidence*, not tamper *prevention*: someone with write
access to the table can recompute the whole chain. Prevention needs an
external anchor (the WORM archive in issue #89 is the planned one).

Pure functions only, no database access, so the hashing rules can be
tested and reasoned about on their own.
"""

import hashlib
from datetime import datetime
from typing import Iterable, Protocol


class ChainedVersion(Protocol):
    """The fields of a stored version that the chain hash covers."""

    id: str
    workflow_name: str
    sequence: int
    yaml_text: str
    content_hash: str
    chain_hash: str
    prev_chain_hash: str | None
    author_user_id: str
    change_note: str
    created_at: datetime


def compute_content_hash(yaml_text: str) -> str:
    """SHA-256 (hex) of a workflow definition's exact YAML text."""
    return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()


def compute_chain_hash(
    *,
    prev_chain_hash: str | None,
    workflow_name: str,
    sequence: int,
    content_hash: str,
    author_user_id: str,
    change_note: str,
    created_at: datetime,
) -> str:
    """SHA-256 (hex) binding one version to its predecessor.

    Fields are joined with a NUL separator, which none of them can contain
    in practice, so two different field combinations can't concatenate to
    the same input. created_at is hashed as its naive ISO form, which is how
    it is stored (see AuditLogRepository.record for the same convention).
    """
    parts = [
        prev_chain_hash or "",
        workflow_name,
        str(sequence),
        content_hash,
        author_user_id,
        change_note,
        created_at.replace(tzinfo=None).isoformat(),
    ]
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def verify_chain(versions: Iterable[ChainedVersion]) -> ChainedVersion | None:
    """Return the first version (oldest first) whose stored hashes don't
    match its own fields or its predecessor, or None if the chain is intact.

    Accepts versions in any order: they are checked in sequence order.
    """
    previous_chain_hash: str | None = None
    for version in sorted(versions, key=lambda v: v.sequence):
        expected_content_hash = compute_content_hash(version.yaml_text)
        expected_chain_hash = compute_chain_hash(
            prev_chain_hash=previous_chain_hash,
            workflow_name=version.workflow_name,
            sequence=version.sequence,
            content_hash=expected_content_hash,
            author_user_id=version.author_user_id,
            change_note=version.change_note,
            created_at=version.created_at,
        )
        if (
            version.content_hash != expected_content_hash
            or version.prev_chain_hash != previous_chain_hash
            or version.chain_hash != expected_chain_hash
        ):
            return version
        previous_chain_hash = version.chain_hash
    return None
