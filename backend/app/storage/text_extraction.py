"""Text extraction for uploaded knowledge-base documents.

Runs once, at upload time, before the extracted text is embedded and
stored in KnowledgeBase.content (see app.api.knowledge_base) - the rest of
the ingestion/search pipeline never sees the original file bytes again,
only this function's output. Supported formats are intentionally narrow
(plain text, PDF, DOCX): an unsupported content type is rejected here so
the upload endpoint can return a 415 rather than silently embedding empty
or garbled text.
"""

from io import BytesIO

from docx import Document as DocxDocument
from pypdf import PdfReader

_PDF_CONTENT_TYPE = "application/pdf"
_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PLAIN_TEXT_CONTENT_TYPE = "text/plain"


class UnsupportedContentTypeError(ValueError):
    """Raised when extract_text() is given a content type it cannot parse."""


def extract_text(data: bytes, *, content_type: str) -> str:
    """Extract plain text from uploaded file bytes.

    Args:
        data: the raw uploaded file bytes.
        content_type: the MIME type declared by the upload (validated by
            the caller against an allow-list before this is reached).

    Returns:
        The extracted text.

    Raises:
        UnsupportedContentTypeError: content_type is not one of the
            supported formats.
    """
    if content_type == _PLAIN_TEXT_CONTENT_TYPE:
        return _extract_plain_text(data)
    if content_type == _PDF_CONTENT_TYPE:
        return _extract_pdf_text(data)
    if content_type == _DOCX_CONTENT_TYPE:
        return _extract_docx_text(data)

    raise UnsupportedContentTypeError(f"Unsupported content type: {content_type!r}")


def _extract_plain_text(data: bytes) -> str:
    """Decode as UTF-8, replacing any invalid byte sequences rather than
    raising - a malformed encoding shouldn't fail an otherwise-fine upload.
    """
    return data.decode("utf-8", errors="replace")


def _extract_pdf_text(data: bytes) -> str:
    """Extract and concatenate text from every page, in order."""
    reader = PdfReader(BytesIO(data))
    return "\n".join(page.extract_text() for page in reader.pages)


def _extract_docx_text(data: bytes) -> str:
    """Extract and concatenate every paragraph's text, in document order."""
    document = DocxDocument(BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)
