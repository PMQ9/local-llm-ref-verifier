"""Stage 3: Audit manuscript citations using the local LLM.

Compares the manuscript body text against verified references to find
citation issues. The manuscript text stays entirely local.
"""

import json
import logging

from .models import AuditReport, VerificationResult
from .ollama_client import OllamaClient
from .prompts import AUDIT_PROMPT_TEMPLATE, AUDIT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def audit_manuscript(
    body_text: str,
    verification: VerificationResult,
    client: OllamaClient,
) -> AuditReport:
    """Run the citation audit using the local LLM."""
    # Prepare reference summary for the prompt
    refs_summary = []
    for vref in verification.references:
        refs_summary.append({
            "ref_id": vref.ref_id,
            "status": vref.status.value,
            "confidence": vref.confidence,
            "title": vref.canonical_title,
            "authors": vref.canonical_authors,
            "year": vref.canonical_year,
            "doi": vref.canonical_doi,
        })

    references_json = json.dumps(refs_summary, indent=2)

    # Truncate body text if extremely long (to fit context window)
    max_body_chars = 30000
    if len(body_text) > max_body_chars:
        logger.warning(
            "Body text truncated from %d to %d chars for audit",
            len(body_text),
            max_body_chars,
        )
        body_text = body_text[:max_body_chars] + "\n\n[... text truncated ...]"

    prompt = AUDIT_PROMPT_TEMPLATE.format(
        references_json=references_json,
        body_text=body_text,
    )

    logger.info("Running citation audit with %d verified references", len(verification.references))

    report = client.chat_structured(
        prompt=prompt,
        response_model=AuditReport,
        system_prompt=AUDIT_SYSTEM_PROMPT,
    )

    logger.info(
        "Audit complete: %d issues found (%s)",
        report.issues_found,
        report.summary[:100],
    )

    return report
