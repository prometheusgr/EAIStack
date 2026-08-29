"""Structure-aware markdown chunking for knowledge-base documents.

A long document embedded as a single vector collapses everything into one
averaged representation, so specific facts inside it match poorly, and
content beyond the embedding server's context window (--ctx-size, see
docker-compose.yml) is silently truncated server-side with no error. This
module splits a document into passage-sized chunks instead, so
knowledge_base.py can store and retrieve individual passages
(see app.db.models.Embedding's chunk_index/chunk_text/heading_path columns).

Deliberately pure and deterministic: plain text in, a list of Chunk objects
out, no DB or network access, so it is directly unit-testable.
"""

import re
from dataclasses import dataclass

# Target chunk size in (approximate) tokens. A chunk below MIN_CHUNK_TOKENS
# is merged with adjacent content rather than left as a tiny fragment; one
# above MAX_CHUNK_TOKENS is split, except for an atomic element (a fenced
# code block) that exceeds it on its own, which is kept whole regardless —
# a bisected code block is worse than an oversized chunk.
MIN_CHUNK_TOKENS = 500
MAX_CHUNK_TOKENS = 1000

# Overlap between consecutive chunks *within the same section*, as a
# fraction of MAX_CHUNK_TOKENS. Repeating a chunk's trailing tokens at the
# start of the next chunk means a fact that happens to fall on a chunk
# boundary is not lost entirely to one side of the split.
CHUNK_OVERLAP_RATIO = 0.125

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_FENCED_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)


def _approximate_token_count(text: str) -> int:
    """A cheap whitespace-split stand-in for llama.cpp's real tokenizer.

    The exact token boundary the embedding server will apply is not
    available outside the server itself, so this is a deliberate
    approximation — good enough to target roughly-sized chunks, not an
    exact token budget.
    """
    return len(text.split())


@dataclass(frozen=True)
class Chunk:
    """One chunk of a document, ready to be embedded and stored.

    text is the chunk's own passage, stored verbatim in
    Embedding.chunk_text so retrieval can return it without re-splitting the
    document. embed_text is what actually gets embedded: title and heading
    path prepended, since a chunk extracted from its section loses the
    context that makes it meaningful otherwise. This composes with (is
    separate from) the "search_document: " prefix embed_document applies —
    embed_text is the argument to embed_document, not a replacement for it.
    """

    chunk_index: int
    heading_path: str | None
    text: str
    token_count: int
    title: str

    @property
    def embed_text(self) -> str:
        """Text to hand to embed_document: title, heading path, then the chunk."""
        context = self.title if self.heading_path is None else f"{self.title} > {self.heading_path}"
        return f"{context}\n\n{self.text}"


@dataclass(frozen=True)
class _Section:
    """One heading's worth of document: its full heading path and body text."""

    heading_path: str | None
    body: str


def _split_into_sections(content: str) -> list[_Section]:
    """Split content into sections at markdown ATX headings, tracking each
    section's full heading path (e.g. "Guide > TLS > Rotation").

    Content before the first heading (or the whole document, if there are
    no headings at all) becomes one section with heading_path=None. A
    heading immediately followed by another heading (no body text) produces
    no section of its own — there is nothing to chunk.
    """
    matches = list(_HEADING_PATTERN.finditer(content))
    if not matches:
        body = content.strip()
        return [_Section(heading_path=None, body=body)] if body else []

    sections: list[_Section] = []

    preamble = content[: matches[0].start()].strip()
    if preamble:
        sections.append(_Section(heading_path=None, body=preamble))

    heading_stack: list[tuple[int, str]] = []  # (level, title)
    for i, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()

        heading_stack = [entry for entry in heading_stack if entry[0] < level]
        heading_stack.append((level, title))
        heading_path = " > ".join(t for _, t in heading_stack)

        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()

        if body:
            sections.append(_Section(heading_path=heading_path, body=body))

    return sections


def _split_into_atoms(body: str) -> list[str]:
    """Split a section's body into atomic units for packing: fenced code
    blocks stay whole, everything else is split on blank-line paragraph
    breaks (and, if a paragraph alone still exceeds MAX_CHUNK_TOKENS, further
    into word-count-sized pieces — only a fenced code block is exempt from
    ever being split).
    """
    atoms: list[str] = []
    cursor = 0
    for match in _FENCED_CODE_BLOCK_PATTERN.finditer(body):
        before = body[cursor : match.start()].strip()
        if before:
            atoms.extend(_split_oversized_paragraphs(before))
        atoms.append(match.group(0))
        cursor = match.end()

    trailing = body[cursor:].strip()
    if trailing:
        atoms.extend(_split_oversized_paragraphs(trailing))

    return atoms


def _split_oversized_paragraphs(text: str) -> list[str]:
    """Split text on blank-line paragraph breaks, then further split any
    single paragraph that alone exceeds MAX_CHUNK_TOKENS into word-count
    sized pieces (e.g. one long paragraph with no internal blank lines).
    Only a fenced code block is exempt from ever being split — plain text
    always has a word boundary to split on.
    """
    pieces: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        if not paragraph.strip():
            continue

        words = paragraph.split()
        if len(words) <= MAX_CHUNK_TOKENS:
            pieces.append(paragraph)
            continue

        for start in range(0, len(words), MAX_CHUNK_TOKENS):
            pieces.append(" ".join(words[start : start + MAX_CHUNK_TOKENS]))

    return pieces


def _pack_atoms_into_chunks(atoms: list[str]) -> list[str]:
    """Greedily pack atoms (paragraphs / whole code blocks) into chunks
    targeting MAX_CHUNK_TOKENS, applying overlap between consecutive
    chunks. An atom that alone exceeds MAX_CHUNK_TOKENS (an oversized code
    block) becomes its own chunk rather than being split or merged.
    """
    if not atoms:
        return []

    overlap_tokens = int(MAX_CHUNK_TOKENS * CHUNK_OVERLAP_RATIO)

    chunks: list[str] = []
    current_atoms: list[str] = []
    current_tokens = 0

    def _flush():
        if current_atoms:
            chunks.append("\n\n".join(current_atoms))

    for atom in atoms:
        atom_tokens = _approximate_token_count(atom)

        if current_atoms and current_tokens + atom_tokens > MAX_CHUNK_TOKENS:
            flushed_text = "\n\n".join(current_atoms)
            _flush()

            overlap_text = _tail_tokens(flushed_text, overlap_tokens)
            current_atoms = [overlap_text] if overlap_text else []
            current_tokens = _approximate_token_count(overlap_text) if overlap_text else 0

        current_atoms.append(atom)
        current_tokens += atom_tokens

    _flush()
    return chunks


def _tail_tokens(text: str, n: int) -> str:
    """The last n whitespace-separated tokens of text, or "" if n <= 0."""
    if n <= 0:
        return ""
    words = text.split()
    return " ".join(words[-n:])


def chunk_document(content: str, *, title: str) -> list[Chunk]:
    """Split a document into structure-aware, passage-sized chunks.

    Splits on markdown heading boundaries first (never mixing text from two
    different sections into one chunk), then packs each section's
    paragraphs/code-blocks into chunks targeting MIN_CHUNK_TOKENS to
    MAX_CHUNK_TOKENS with overlap between consecutive chunks in the same
    section. A fenced code block is never split, even if that makes its
    chunk exceed MAX_CHUNK_TOKENS.

    A document with no headings, or shorter than one chunk, still returns a
    single Chunk (heading_path=None) rather than an empty list, so every
    document has at least one embeddable unit.
    """
    sections = _split_into_sections(content)

    chunk_texts: list[tuple[str | None, str]] = []
    for section in sections:
        atoms = _split_into_atoms(section.body)
        for chunk_text in _pack_atoms_into_chunks(atoms):
            chunk_texts.append((section.heading_path, chunk_text))

    return [
        Chunk(
            chunk_index=i,
            heading_path=heading_path,
            text=text,
            token_count=_approximate_token_count(text),
            title=title,
        )
        for i, (heading_path, text) in enumerate(chunk_texts)
    ]
