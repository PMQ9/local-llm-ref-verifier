"""PDF text extraction and reference section isolation.

Uses pdfplumber as primary extractor with PyMuPDF (fitz) as fallback.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

REFERENCE_HEADINGS = re.compile(
    r"^\s*(references|bibliography|works\s+cited|literature\s+cited|citations)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class ParsedPDF:
    """Result of parsing a PDF."""

    full_text: str
    reference_section: str
    body_text: str


def extract_text_pdfplumber(pdf_path: Path) -> str:
    """Extract text from PDF using pdfplumber."""
    import pdfplumber

    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def extract_text_pymupdf(pdf_path: Path) -> str:
    """Extract text from PDF using PyMuPDF (fallback)."""
    import fitz

    text_parts = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n\n".join(text_parts)


def extract_text(pdf_path: Path) -> str:
    """Extract full text from a PDF, trying pdfplumber first then PyMuPDF."""
    try:
        text = extract_text_pdfplumber(pdf_path)
        if text.strip():
            return text
        logger.warning("pdfplumber returned empty text, trying PyMuPDF")
    except Exception as e:
        logger.warning("pdfplumber failed: %s, trying PyMuPDF", e)

    try:
        return extract_text_pymupdf(pdf_path)
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from {pdf_path}: {e}") from e


def split_reference_section(full_text: str) -> tuple[str, str]:
    """Split text into body and reference section.

    Returns (body_text, reference_section). If no reference heading is found,
    returns the full text as body and an empty string for references.
    """
    matches = list(REFERENCE_HEADINGS.finditer(full_text))
    if not matches:
        logger.warning(
            "No reference section heading found. "
            "The full text will be used as body with no isolated reference section."
        )
        return full_text, ""

    # Use the last match (in case "References" appears in a table of contents too)
    last_match = matches[-1]
    body = full_text[: last_match.start()].strip()
    refs = full_text[last_match.end() :].strip()
    return body, refs


def parse_pdf(pdf_path: str | Path) -> ParsedPDF:
    """Parse a PDF and split into body text and reference section."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not pdf_path.suffix.lower() == ".pdf":
        raise ValueError(f"Expected a PDF file, got: {pdf_path.suffix}")

    full_text = extract_text(pdf_path)
    body_text, reference_section = split_reference_section(full_text)

    logger.info(
        "Parsed %s: %d chars total, %d chars body, %d chars references",
        pdf_path.name,
        len(full_text),
        len(body_text),
        len(reference_section),
    )

    return ParsedPDF(
        full_text=full_text,
        reference_section=reference_section,
        body_text=body_text,
    )
