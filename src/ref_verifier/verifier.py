"""Stage 2: Online reference verification orchestrator.

Tries CrossRef → Semantic Scholar → Google Scholar in a fallback chain.
Only minimal reference metadata (title, authors, year) is sent externally.
"""

import logging
from collections import Counter

from .models import (
    ExtractionResult,
    Reference,
    VerificationResult,
    VerificationStatus,
    VerifiedReference,
)
from .sources import crossref, google_scholar, semantic_scholar

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.8


def verify_single_reference(
    ref: Reference,
    use_google_scholar: bool = False,
) -> VerifiedReference:
    """Verify a single reference using the fallback chain."""

    # Try CrossRef first
    result = crossref.verify_reference(ref)
    if result and result.confidence >= CONFIDENCE_THRESHOLD:
        logger.info("ref %s: verified via CrossRef (%.2f)", ref.id, result.confidence)
        return result

    # Try Semantic Scholar
    s2_result = semantic_scholar.verify_reference(ref)
    if s2_result and s2_result.confidence >= CONFIDENCE_THRESHOLD:
        logger.info(
            "ref %s: verified via Semantic Scholar (%.2f)",
            ref.id,
            s2_result.confidence,
        )
        return s2_result

    # Keep the better of CrossRef/S2 results so far
    best = result
    if s2_result and (best is None or s2_result.confidence > best.confidence):
        best = s2_result

    # Try Google Scholar as last resort (if enabled)
    if use_google_scholar:
        gs_result = google_scholar.verify_reference(ref)
        if gs_result and (best is None or gs_result.confidence > best.confidence):
            best = gs_result
            if gs_result.confidence >= CONFIDENCE_THRESHOLD:
                logger.info(
                    "ref %s: verified via Google Scholar (%.2f)",
                    ref.id,
                    gs_result.confidence,
                )
                return best

    # Return best result we found, or a NOT_FOUND
    if best:
        logger.info("ref %s: best confidence %.2f (%s)", ref.id, best.confidence, best.status.value)
        return best

    logger.warning("ref %s: not found in any source", ref.id)
    return VerifiedReference(
        ref_id=ref.id,
        status=VerificationStatus.NOT_FOUND,
        confidence=0.0,
        notes="Not found in CrossRef, Semantic Scholar, or Google Scholar",
    )


def verify_references(
    extraction: ExtractionResult,
    use_google_scholar: bool = False,
) -> VerificationResult:
    """Verify all references from a Stage 1 extraction result."""
    verified: list[VerifiedReference] = []

    for i, ref in enumerate(extraction.references):
        logger.info(
            "Verifying reference %d/%d: %s",
            i + 1,
            len(extraction.references),
            ref.title[:60],
        )
        result = verify_single_reference(ref, use_google_scholar=use_google_scholar)
        verified.append(result)

    # Compute stats
    status_counts = Counter(v.status.value for v in verified)
    stats = {
        "total": len(verified),
        "verified": status_counts.get("verified", 0),
        "ambiguous": status_counts.get("ambiguous", 0),
        "not_found": status_counts.get("not_found", 0),
    }

    logger.info("Verification complete: %s", stats)

    return VerificationResult(references=verified, stats=stats)
