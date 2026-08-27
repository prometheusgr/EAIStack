"""Unit tests for text extraction from uploaded documents - TDD discipline.

Extraction libraries (pypdf, python-docx) are not an external boundary in
the LLM-mocking sense (per AGENTS.md, only app.core.llm_client is that
boundary) - they're deterministic parsing logic running on bytes we
control, so these tests build real minimal PDF/DOCX files in-memory and
extract from them for real, rather than mocking the library.
"""

from io import BytesIO

import pytest
from docx import Document as DocxDocument
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from app.storage.text_extraction import UnsupportedContentTypeError, extract_text


def _build_pdf_bytes(text: str) -> bytes:
    """Build a minimal one-page PDF whose content stream shows `text`.

    Uses the standard (non-embedded) Helvetica base-14 font, so no font
    file needs to ship with the test - just enough of a PDF for
    extract_text() to have real page content to parse.
    """
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)

    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    content_stream = StreamObject()
    content_stream.set_data(b"BT /F1 24 Tf 10 100 Td (" + text.encode("latin-1") + b") Tj ET")
    page[NameObject("/Contents")] = content_stream

    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    doc = DocxDocument()
    for para in paragraphs:
        doc.add_paragraph(para)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.mark.unit
def test_extract_text_from_plain_text():
    """Test: text/plain content is decoded as UTF-8 text unchanged."""
    result = extract_text(b"Hello, this is plain text.", content_type="text/plain")
    assert result == "Hello, this is plain text."


@pytest.mark.unit
def test_extract_text_from_plain_text_handles_non_utf8_gracefully():
    """Test: a plain-text file with invalid UTF-8 bytes doesn't raise -
    invalid sequences are replaced rather than crashing the upload.
    """
    result = extract_text(b"Valid text \xff\xfe more text", content_type="text/plain")
    assert "Valid text" in result
    assert "more text" in result


@pytest.mark.unit
def test_extract_text_from_docx():
    """Test: DOCX paragraphs are extracted as newline-joined text."""
    docx_bytes = _build_docx_bytes(["First paragraph.", "Second paragraph."])

    result = extract_text(
        docx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert "First paragraph." in result
    assert "Second paragraph." in result


@pytest.mark.unit
def test_extract_text_from_pdf():
    """Test: PDF page text is extracted."""
    pdf_bytes = _build_pdf_bytes("Hello from a PDF page")

    result = extract_text(pdf_bytes, content_type="application/pdf")

    assert "Hello from a PDF page" in result


@pytest.mark.unit
def test_extract_text_rejects_unsupported_content_type():
    """Test: an unrecognized content type raises a typed error at the
    extraction boundary rather than silently returning empty/garbage text -
    the upload endpoint uses this to return a 415 to the caller.
    """
    with pytest.raises(UnsupportedContentTypeError):
        extract_text(b"\x00\x01binary", content_type="application/x-executable")
