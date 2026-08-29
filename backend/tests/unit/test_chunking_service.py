"""TDD tests for structure-aware markdown chunking.

chunk_document is pure and deterministic: plain text in, a list of Chunk
objects out, no DB or network. This is what makes it directly testable
without a database, per docs/RETRIEVAL_IMPROVEMENT_PROMPTS.md's chunking
requirements.

Token counts throughout use a cheap whitespace-split approximation
(app.services.chunking_service._approximate_token_count), not the real
llama.cpp tokenizer — the exact token boundary the embedding server will
see is not available outside the server itself, so this is a deliberate
approximation, good enough to hit roughly-sized chunks.
"""

import pytest

from app.services.chunking_service import (
    MAX_CHUNK_TOKENS,
    MIN_CHUNK_TOKENS,
    Chunk,
    chunk_document,
)


def _words(n: int, prefix: str = "word") -> str:
    """Build a paragraph of n space-separated tokens, for hitting size targets precisely."""
    return " ".join(f"{prefix}{i}" for i in range(n))


@pytest.mark.unit
def test_chunk_document_with_no_headings_returns_single_implicit_section():
    """A document with no markdown headings is still one section (heading_path=None)."""
    content = "Just a plain paragraph with no structure at all."

    chunks = chunk_document(content, title="Plain Doc")

    assert len(chunks) == 1
    assert chunks[0].heading_path is None
    assert chunks[0].text == content
    assert chunks[0].chunk_index == 0


@pytest.mark.unit
def test_chunk_document_content_shorter_than_one_chunk_produces_single_chunk():
    """Short content doesn't get padded, split, or overlapped — it's just one chunk."""
    content = "Short."

    chunks = chunk_document(content, title="Short Doc")

    assert len(chunks) == 1
    assert chunks[0].text == "Short."


@pytest.mark.unit
def test_chunk_document_tracks_heading_path_through_nested_sections():
    """Each chunk records the full heading path down to its own section."""
    content = (
        "# Deployment Guide\n\n"
        "Intro text.\n\n"
        "## TLS\n\n"
        "TLS intro.\n\n"
        "### Certificate rotation\n\n"
        "Rotate certs every 90 days.\n"
    )

    chunks = chunk_document(content, title="Deployment Guide")

    heading_paths = {c.heading_path for c in chunks}
    assert "Deployment Guide" in heading_paths
    assert "Deployment Guide > TLS" in heading_paths
    assert "Deployment Guide > TLS > Certificate rotation" in heading_paths


@pytest.mark.unit
def test_chunk_document_heading_with_no_body_produces_no_orphan_chunk():
    """A heading immediately followed by another heading (no body text) contributes
    no empty chunk for itself.
    """
    content = (
        "# Section A\n\n## Empty Subsection\n\n## Subsection With Body\n\nActual content here.\n"
    )

    chunks = chunk_document(content, title="Doc")

    assert all(c.text.strip() for c in chunks)
    assert not any(c.heading_path == "Section A > Empty Subsection" for c in chunks)


@pytest.mark.unit
def test_chunk_document_never_splits_a_fenced_code_block():
    """A fenced code block larger than the target chunk size stays whole rather
    than being bisected — a split code block is worse than an oversized chunk.
    """
    code_lines = "\n".join(f"line_{i} = {i}" for i in range(400))
    content = f"# Script\n\nHere is the script:\n\n```python\n{code_lines}\n```\n\nEnd of script.\n"

    chunks = chunk_document(content, title="Doc")

    fenced_block = f"```python\n{code_lines}\n```"
    matching = [c for c in chunks if fenced_block in c.text]
    assert len(matching) == 1, "the fenced code block must appear intact in exactly one chunk"


@pytest.mark.unit
def test_chunk_document_ignores_hash_comments_inside_fenced_code_blocks():
    """A '#'-prefixed comment line inside a fenced code block (a common shell/
    Python/YAML comment) must not be misdetected as a markdown heading — doing
    so would bisect the fenced block, which the earlier no-split test already
    establishes must never happen.
    """
    content = (
        "# Script\n\n"
        "Here is the deploy script:\n\n"
        "```bash\n"
        "#!/bin/bash\n"
        "# Deploy the app\n"
        "echo hello\n"
        "```\n\n"
        "## Real Section\n\n"
        "Actual content here.\n"
    )

    chunks = chunk_document(content, title="Doc")

    fenced_block = "```bash\n#!/bin/bash\n# Deploy the app\necho hello\n```"
    matching = [c for c in chunks if fenced_block in c.text]
    assert len(matching) == 1, "the fenced code block must appear intact in exactly one chunk"

    real_section = [c for c in chunks if "Actual content here." in c.text]
    assert len(real_section) == 1
    assert real_section[0].heading_path == "Script > Real Section", (
        "the '# Deploy the app' comment inside the fence must not be treated as a "
        "heading and pushed onto the heading path"
    )


@pytest.mark.unit
def test_chunk_document_splits_long_section_into_multiple_target_sized_chunks():
    """A section much longer than MAX_CHUNK_TOKENS is split into multiple chunks,
    each within the target range (allowing for the oversized-code-block escape hatch,
    not exercised by this plain-text case).
    """
    long_body = "\n\n".join(_words(80, prefix=f"para{p}_w") for p in range(20))
    content = f"# Big Section\n\n{long_body}\n"

    chunks = chunk_document(content, title="Doc")

    assert len(chunks) > 1
    for chunk in chunks[:-1]:
        # Every non-final chunk should be within the target ceiling; only an
        # atomic oversized element (unused here) is allowed to exceed it.
        assert chunk.token_count <= MAX_CHUNK_TOKENS


@pytest.mark.unit
def test_chunk_document_applies_overlap_between_consecutive_chunks_in_same_section():
    """Consecutive chunks within the same section share a trailing/leading
    overlap, so a fact split across a chunk boundary isn't lost entirely to
    either chunk.
    """
    long_body = "\n\n".join(_words(80, prefix=f"para{p}_w") for p in range(20))
    content = f"# Big Section\n\n{long_body}\n"

    chunks = chunk_document(content, title="Doc")

    assert len(chunks) > 1
    first_chunk_tail = chunks[0].text.split()[-1]
    second_chunk_words = chunks[1].text.split()
    assert first_chunk_tail in second_chunk_words[:150], (
        "expected the end of the first chunk to reappear near the start of the "
        "second chunk (overlap)"
    )


@pytest.mark.unit
def test_chunk_document_does_not_overlap_across_section_boundaries():
    """Overlap only happens within a section — carrying trailing text from one
    section's chunk into an unrelated next section would pollute that
    section's heading-path context.
    """
    section_a_body = _words(600, prefix="a_word")
    section_b_body = _words(50, prefix="b_word")
    content = f"# Section A\n\n{section_a_body}\n\n# Section B\n\n{section_b_body}\n"

    chunks = chunk_document(content, title="Doc")

    section_b_chunks = [c for c in chunks if c.heading_path == "Section B"]
    assert len(section_b_chunks) == 1
    assert "a_word" not in section_b_chunks[0].text


@pytest.mark.unit
def test_chunk_document_assigns_sequential_zero_based_chunk_index():
    """chunk_index is 0-based and sequential across the whole document, in
    the order chunks are produced (not reset per section).

    Each section is large enough to still produce multiple chunks even
    after a small trailing chunk would be merged into its neighbor (see
    test_chunk_document_merges_small_trailing_chunk_into_previous_chunk) -
    this test is about index sequencing, not the merge behavior itself.
    """
    content = (
        "# Section A\n\n" + _words(2200, prefix="a_word") + "\n\n"
        "# Section B\n\n" + _words(2200, prefix="b_word") + "\n"
    )

    chunks = chunk_document(content, title="Doc")

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert len(chunks) > 2


@pytest.mark.unit
def test_chunk_embed_text_prepends_title_and_heading_path():
    """Chunk.embed_text is the title + heading path + chunk text, the context
    that gets embedded — separate from (and composed with) the
    "search_document: " prefix applied later by embed_document.
    """
    chunk = Chunk(
        chunk_index=0,
        heading_path="TLS > Certificate rotation",
        text="Rotate certs every 90 days.",
        token_count=6,
        title="Deployment Guide",
    )

    assert chunk.embed_text == (
        "Deployment Guide > TLS > Certificate rotation\n\nRotate certs every 90 days."
    )


@pytest.mark.unit
def test_chunk_embed_text_omits_heading_path_separator_when_no_heading():
    """A chunk with no enclosing heading embeds as just title + text, without
    a dangling separator.
    """
    chunk = Chunk(
        chunk_index=0,
        heading_path=None,
        text="Just a plain paragraph.",
        token_count=4,
        title="Plain Doc",
    )

    assert chunk.embed_text == "Plain Doc\n\nJust a plain paragraph."


@pytest.mark.unit
def test_chunk_document_oversized_code_block_alone_exceeds_max_but_is_kept_whole():
    """A fenced code block bigger than MAX_CHUNK_TOKENS on its own is still
    never split — this pins the escape hatch the earlier no-split test
    exercises, checking the resulting chunk's token_count directly.
    """
    code_lines = "\n".join(f"line_{i} = {i}" for i in range(600))
    content = f"# Script\n\n```python\n{code_lines}\n```\n"

    chunks = chunk_document(content, title="Doc")

    code_chunks = [c for c in chunks if "```python" in c.text]
    assert len(code_chunks) == 1
    assert code_chunks[0].token_count > MAX_CHUNK_TOKENS


@pytest.mark.unit
def test_chunk_document_heading_path_disambiguates_a_heading_containing_the_separator():
    """A heading whose own title contains the literal " > " separator must
    not become indistinguishable from genuine nesting in heading_path - a
    heading titled "Migrating v1 > v2" is one level, not two.
    """
    content = "# Guide\n\n## Migrating v1 > v2\n\nUpgrade steps here.\n"

    chunks = chunk_document(content, title="Guide")

    heading_paths = {c.heading_path for c in chunks}
    assert "Guide > Migrating v1 -> v2" in heading_paths
    assert "Guide > Migrating v1 > v2" not in heading_paths


@pytest.mark.unit
def test_chunk_document_merges_small_trailing_chunk_into_previous_chunk():
    """A final chunk below MIN_CHUNK_TOKENS is merged into the previous
    chunk rather than left as a tiny fragment on its own - the documented
    guarantee at the top of this module (MIN_CHUNK_TOKENS's comment) and in
    chunk_document's own docstring.
    """
    # Two large paragraphs force the packer to split across chunks (with
    # overlap absorbing part of the boundary), leaving a short trailing
    # paragraph that would otherwise become its own tiny final chunk.
    paragraph_one = _words(950, prefix="p1_w")
    paragraph_two = _words(950, prefix="p2_w")
    short_trailing_paragraph = _words(30, prefix="tail_w")
    content = f"# Section\n\n{paragraph_one}\n\n{paragraph_two}\n\n{short_trailing_paragraph}\n"

    chunks = chunk_document(content, title="Doc")

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.token_count >= MIN_CHUNK_TOKENS, (
            f"chunk with {chunk.token_count} tokens is below MIN_CHUNK_TOKENS "
            f"({MIN_CHUNK_TOKENS}) and should have been merged into a neighbor"
        )
    assert "tail_w0" in chunks[-1].text


@pytest.mark.unit
def test_chunk_document_small_trailing_chunk_merges_even_as_sole_chunk():
    """A whole section shorter than MIN_CHUNK_TOKENS (no previous chunk to
    merge into) is still returned as-is - merging only applies when there is
    a neighbor to merge into, matching the existing short-document behavior
    (test_chunk_document_content_shorter_than_one_chunk_produces_single_chunk).
    """
    content = "# Section\n\nJust a short paragraph.\n"

    chunks = chunk_document(content, title="Doc")

    assert len(chunks) == 1
    assert chunks[0].text == "Just a short paragraph."


@pytest.mark.unit
def test_min_and_max_chunk_token_constants_are_sane():
    """Pin the target range documented in docs/RETRIEVAL_IMPROVEMENT_PROMPTS.md
    (roughly 500-1000 tokens) so a future change to these constants is a
    deliberate, visible edit rather than a silent drift.
    """
    assert MIN_CHUNK_TOKENS == 500
    assert MAX_CHUNK_TOKENS == 1000
