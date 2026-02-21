"""Stage 3: Audit manuscript citations using the local LLM.

Compares the manuscript body text against verified references to find
citation issues. The manuscript text stays entirely local.
"""

import json
import logging

from .models import AuditReport, VerificationResult
from .ollama_client import OllamaClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a citation audit assistant. Your job is to analyze a research \
manuscript's body text and compare it against a list of verified references. \
Identify any citation issues with precision."""

AUDIT_PROMPT_TEMPLATE = """\
Analyze the manuscript text below and compare it against the verified \
reference list. Identify the following issues:

1. **Uncited references**: References in the list that are never cited in the body text.
2. **Missing from list**: In-text citations (e.g., "Smith et al., 2020" or "[1]") \
that do not match any reference in the list.
3. **Misquoted claims**: Claims attributed to a reference that seem inconsistent \
with the reference's title/topic (based on the verified metadata).
4. **Year mismatches**: In-text citation years that don't match the reference's \
verified year.

For each issue, provide:
- issue_type: one of "uncited_reference", "missing_from_list", "misquoted_claim", "year_mismatch"
- severity: "error" for definite problems, "warning" for likely problems, "info" for minor notes
- ref_id: the reference ID if applicable (null otherwise)
- description: clear explanation of the issue
- manuscript_excerpt: the relevant quote from the manuscript (if applicable)

Also provide a summary paragraph and counts.

VERIFIED REFERENCES:
{references_json}

MANUSCRIPT TEXT:
{body_text}"""


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
        system_prompt=SYSTEM_PROMPT,
    )

    logger.info(
        "Audit complete: %d issues found (%s)",
        report.issues_found,
        report.summary[:100],
    )

    return report
