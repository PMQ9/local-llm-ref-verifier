"""PDF text extraction and reference section isolation.

Uses pdfplumber as primary extractor with PyMuPDF (fitz) as fallback.
Multi-column layouts (e.g. IEEE two-column) are detected and extracted
column-by-column so that body text and references are never interleaved.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

REFERENCE_HEADINGS = re.compile(
    r"^\s*\.?\s*(references|bibliography|works\s+cited|literature\s+cited|citations)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class ParsedPDF:
    """Result of parsing a PDF."""

    full_text: str
    reference_section: str
    body_text: str


def _find_column_gap_from_centers(
    word_centers: list[float], page_width: float
) -> float | None:
    """Find the x-coordinate of a vertical gap between columns.

    Takes a list of word center x-coordinates and the page width. Divides
    the page into narrow vertical bins and looks for a low-density region
    in the middle 40%. Returns the center of the gap, or None if single-column.
    """
    if not word_centers:
        return None

    bin_width = 10
    n_bins = int(page_width / bin_width) + 1
    bins = [0] * n_bins

    for cx in word_centers:
        b = min(int(cx / bin_width), n_bins - 1)
        bins[b] += 1

    # Look for a minimum in the middle 40% of the page
    lo = int(n_bins * 0.30)
    hi = int(n_bins * 0.70)
    if lo >= hi:
        return None

    mid_bins = bins[lo:hi]
    min_val = min(mid_bins)
    avg_val = sum(bins) / n_bins

    # The gap bin should have significantly fewer words than average
    if min_val > avg_val * 0.25:
        return None

    gap_bin = lo + mid_bins.index(min_val)
    return (gap_bin + 0.5) * bin_width


# ---------------------------------------------------------------------------
# pdfplumber extraction
# ---------------------------------------------------------------------------


def _extract_page_pdfplumber(page) -> str:
    """Extract text from a pdfplumber page, splitting columns if detected."""
    words = page.extract_words()
    if not words:
        return page.extract_text() or ""

    centers = [(float(w["x0"]) + float(w["x1"])) / 2 for w in words]
    gap_x = _find_column_gap_from_centers(centers, page.width)

    if gap_x is None:
        return page.extract_text() or ""

    left = page.crop((0, 0, gap_x, page.height))
    right = page.crop((gap_x, 0, page.width, page.height))

    left_text = left.extract_text() or ""
    right_text = right.extract_text() or ""

    return left_text + "\n" + right_text


def extract_text_pdfplumber(pdf_path: Path) -> str:
    """Extract text from PDF using pdfplumber with column-aware extraction."""
    import pdfplumber

    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = _extract_page_pdfplumber(page)
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


# ---------------------------------------------------------------------------
# PyMuPDF (fitz) extraction
# ---------------------------------------------------------------------------


def _extract_page_pymupdf(page) -> str:
    """Extract text from a PyMuPDF page, splitting columns if detected."""
    import fitz

    # page.get_text("words") returns (x0, y0, x1, y1, word, block, line, word_no)
    words = page.get_text("words")
    if not words:
        return page.get_text()

    centers = [(w[0] + w[2]) / 2 for w in words]
    rect = page.rect
    gap_x = _find_column_gap_from_centers(centers, rect.width)

    if gap_x is None:
        return page.get_text()

    left_rect = fitz.Rect(0, 0, gap_x, rect.height)
    right_rect = fitz.Rect(gap_x, 0, rect.width, rect.height)

    left_text = page.get_text(clip=left_rect) or ""
    right_text = page.get_text(clip=right_rect) or ""

    return left_text + "\n" + right_text


def extract_text_pymupdf(pdf_path: Path) -> str:
    """Extract text from PDF using PyMuPDF with column-aware extraction."""
    import fitz

    text_parts = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text_parts.append(_extract_page_pymupdf(page))
    return "\n\n".join(text_parts)


# ---------------------------------------------------------------------------
# Common extraction pipeline
# ---------------------------------------------------------------------------


_MIN_SPACE_RATIO = 0.06


def _space_ratio(text: str) -> float:
    """Return the fraction of characters that are spaces."""
    if not text:
        return 0.0
    return text.count(" ") / len(text)


def extract_text(pdf_path: Path) -> str:
    """Extract full text from a PDF, trying pdfplumber first then PyMuPDF.

    Falls back to PyMuPDF if pdfplumber returns empty text or produces
    output with very few spaces (indicating broken word separation).
    """
    try:
        text = extract_text_pdfplumber(pdf_path)
        if not text.strip():
            logger.warning("pdfplumber returned empty text, trying PyMuPDF")
        elif _space_ratio(text) < _MIN_SPACE_RATIO:
            logger.warning(
                "pdfplumber text has low space ratio (%.1f%%), "
                "likely missing word separators; trying PyMuPDF",
                _space_ratio(text) * 100,
            )
        else:
            return text
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


def _normalize_unicode(text: str) -> str:
    """Normalize common Unicode characters from PDF extraction to ASCII.

    Curly quotes, en/em dashes, and other typographic characters are replaced
    with their ASCII equivalents so that regex parsers work reliably.
    """
    replacements = {
        "\u201c": '"',  # left double quotation mark
        "\u201d": '"',  # right double quotation mark
        "\u2018": "'",  # left single quotation mark
        "\u2019": "'",  # right single quotation mark
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u00a0": " ",  # non-breaking space
        "\ufb01": "fi",  # fi ligature
        "\ufb02": "fl",  # fl ligature
        "\ufb00": "ff",  # ff ligature
        "\ufb03": "ffi",  # ffi ligature
        "\ufb04": "ffl",  # ffl ligature
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def parse_pdf(pdf_path: str | Path) -> ParsedPDF:
    """Parse a PDF and split into body text and reference section."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not pdf_path.suffix.lower() == ".pdf":
        raise ValueError(f"Expected a PDF file, got: {pdf_path.suffix}")

    full_text = _normalize_unicode(extract_text(pdf_path))
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
