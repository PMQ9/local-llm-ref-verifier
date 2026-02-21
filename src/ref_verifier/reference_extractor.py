"""Stage 1: Extract and normalize references using a local LLM.

Sends the reference section text to Ollama and gets back structured
Reference objects. Batches large reference lists to stay within
context window limits.
"""

import logging
from pathlib import Path

from .models import ExtractionResult, Reference
from .ollama_client import OllamaClient
from .pdf_parser import parse_pdf

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a reference extraction assistant. Your job is to parse academic \
reference lists into structured JSON. Be precise with author names, titles, \
years, and DOIs. If a field is not present in the reference, leave it as null."""

EXTRACTION_PROMPT_TEMPLATE = """\
Extract each reference from the text below into structured JSON. \
For each reference, extract: authors (as a list), title, year, journal, \
volume, pages, and DOI (if present). Also include the original raw text.

Assign sequential IDs like ref_01, ref_02, etc.{batch_note}

Here are examples of how to parse references:

Example input:
Smith, J., & Doe, A. (2020). Machine learning in healthcare. Nature Medicine, 26(3), 309-316. https://doi.org/10.1038/s41591-020-0803-x

Example output for that reference:
- id: "ref_01"
- authors: ["Smith, J.", "Doe, A."]
- title: "Machine learning in healthcare"
- year: 2020
- journal: "Nature Medicine"
- volume: "26(3)"
- pages: "309-316"
- doi: "10.1038/s41591-020-0803-x"
- raw_text: "Smith, J., & Doe, A. (2020). Machine learning in healthcare. Nature Medicine, 26(3), 309-316. https://doi.org/10.1038/s41591-020-0803-x"

Now extract all references from this text:

---
{reference_text}
---"""

# Pydantic model for batched extraction (list of references)
from pydantic import BaseModel, Field


class _ReferenceList(BaseModel):
    references: list[Reference] = Field(description="List of extracted references")


MAX_REFS_PER_BATCH = 20
CHARS_PER_BATCH = 8000


def _split_into_batches(reference_text: str) -> list[str]:
    """Split reference text into batches by character count."""
    lines = reference_text.split("\n")
    batches = []
    current_batch: list[str] = []
    current_len = 0

    for line in lines:
        if current_len + len(line) > CHARS_PER_BATCH and current_batch:
            batches.append("\n".join(current_batch))
            current_batch = []
            current_len = 0
        current_batch.append(line)
        current_len += len(line) + 1

    if current_batch:
        batches.append("\n".join(current_batch))

    return batches


def extract_references(
    reference_text: str,
    client: OllamaClient,
    start_id: int = 1,
) -> list[Reference]:
    """Extract references from a block of reference text using the local LLM."""
    batch_note = ""
    if start_id > 1:
        batch_note = f" Start numbering from ref_{start_id:02d}."

    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        reference_text=reference_text,
        batch_note=batch_note,
    )

    result = client.chat_structured(
        prompt=prompt,
        response_model=_ReferenceList,
        system_prompt=SYSTEM_PROMPT,
    )

    return result.references


def extract_from_pdf(
    pdf_path: str | Path,
    client: OllamaClient,
) -> ExtractionResult:
    """Full Stage 1 pipeline: PDF → parsed text → extracted references."""
    parsed = parse_pdf(pdf_path)

    if not parsed.reference_section:
        logger.warning(
            "No reference section found in %s. Using last portion of text.", pdf_path
        )
        # Fallback: use the last 20% of the text as a rough reference section
        cutoff = int(len(parsed.full_text) * 0.8)
        ref_text = parsed.full_text[cutoff:]
    else:
        ref_text = parsed.reference_section

    # Split into batches if the reference section is large
    batches = _split_into_batches(ref_text)
    all_references: list[Reference] = []

    for i, batch in enumerate(batches):
        logger.info("Processing batch %d/%d (%d chars)", i + 1, len(batches), len(batch))
        start_id = len(all_references) + 1
        refs = extract_references(batch, client, start_id=start_id)
        all_references.extend(refs)

    logger.info("Extracted %d references from %s", len(all_references), pdf_path)

    return ExtractionResult(
        source_pdf=str(pdf_path),
        references=all_references,
        model_used=client.model,
    )
