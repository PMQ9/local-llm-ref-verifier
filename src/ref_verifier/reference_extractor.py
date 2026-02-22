"""Stage 1: Extract and normalize references using rule-based regex parsers.

Auto-detects the citation style (APA, IEEE, Vancouver, Harvard, Chicago)
and applies the appropriate parser. No LLM or internet needed.
"""

import logging
from pathlib import Path

from .models import ExtractionResult, Reference
from .parsers import PARSERS, detect_style
from .pdf_parser import parse_pdf

logger = logging.getLogger(__name__)


def extract_references(
    reference_text: str,
    style: str | None = None,
) -> list[Reference]:
    """Extract references from a block of reference text.

    Args:
        reference_text: The raw reference section text.
        style: Force a specific style (apa, ieee, vancouver, harvard, chicago).
               If None, auto-detects the style.

    Returns:
        List of parsed Reference objects.
    """
    if not reference_text.strip():
        logger.warning("Empty reference text provided")
        return []

    if style is None:
        style = detect_style(reference_text)
    elif style not in PARSERS:
        raise ValueError(
            f"Unknown style '{style}'. Available: {list(PARSERS.keys())}"
        )

    parser = PARSERS[style]
    logger.info("Using %s parser", style.upper())

    references = parser.parse_all(reference_text)
    logger.info("Parsed %d references using %s style", len(references), style)

    return references


def extract_from_pdf(
    pdf_path: str | Path,
    style: str | None = None,
) -> ExtractionResult:
    """Full Stage 1 pipeline: PDF → parsed text → extracted references.

    Args:
        pdf_path: Path to the PDF manuscript.
        style: Force a specific citation style, or None to auto-detect.

    Returns:
        ExtractionResult with all parsed references.
    """
    parsed = parse_pdf(pdf_path)

    if not parsed.reference_section:
        logger.warning(
            "No reference section found in %s. Using last portion of text.", pdf_path
        )
        cutoff = int(len(parsed.full_text) * 0.8)
        ref_text = parsed.full_text[cutoff:]
    else:
        ref_text = parsed.reference_section

    if style is None:
        style = detect_style(ref_text)

    references = extract_references(ref_text, style=style)
    logger.info("Extracted %d references from %s", len(references), pdf_path)

    return ExtractionResult(
        source_pdf=str(pdf_path),
        references=references,
        model_used=f"regex:{style}",
    )
