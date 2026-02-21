"""Semantic Scholar API client for reference verification.

Queries the Semantic Scholar paper search API by title, then uses
fuzzy string matching to compute a confidence score.
"""

import logging
from typing import Optional

import httpx
from rapidfuzz import fuzz

from ..models import Reference, VerifiedReference, VerificationStatus

logger = logging.getLogger(__name__)

S2_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
TIMEOUT = 30
FIELDS = "title,authors,year,externalIds"


def _compute_confidence(ref: Reference, paper: dict) -> float:
    """Compute confidence score between extracted ref and an S2 result."""
    api_title = paper.get("title", "")
    if not api_title:
        return 0.0

    title_score = fuzz.token_sort_ratio(ref.title.lower(), api_title.lower()) / 100.0

    # DOI match bonus
    external_ids = paper.get("externalIds") or {}
    if ref.doi and external_ids.get("DOI"):
        if ref.doi.lower().strip() == external_ids["DOI"].lower().strip():
            return 1.0

    # Year match bonus
    year_bonus = 0.0
    if ref.year and paper.get("year") == ref.year:
        year_bonus = 0.05

    return min(title_score + year_bonus, 1.0)


def _extract_canonical(paper: dict) -> dict:
    """Extract canonical metadata from a Semantic Scholar paper."""
    authors = [a.get("name", "") for a in paper.get("authors", []) if a.get("name")]
    external_ids = paper.get("externalIds") or {}

    return {
        "canonical_title": paper.get("title"),
        "canonical_doi": external_ids.get("DOI"),
        "canonical_authors": authors or None,
        "canonical_year": paper.get("year"),
    }


def verify_reference(ref: Reference) -> Optional[VerifiedReference]:
    """Verify a single reference against Semantic Scholar. Returns None on failure."""
    try:
        response = httpx.get(
            S2_API_URL,
            params={"query": ref.title, "fields": FIELDS, "limit": 3},
            timeout=TIMEOUT,
            headers={"User-Agent": "local-llm-ref-verifier/0.1.0"},
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.warning("Semantic Scholar API error for '%s': %s", ref.title[:50], e)
        return None

    papers = data.get("data", [])
    if not papers:
        return None

    best_confidence = 0.0
    best_paper = papers[0]
    for paper in papers:
        conf = _compute_confidence(ref, paper)
        if conf > best_confidence:
            best_confidence = conf
            best_paper = paper

    if best_confidence < 0.3:
        return None

    canonical = _extract_canonical(best_paper)

    if best_confidence >= 0.85:
        status = VerificationStatus.VERIFIED
    elif best_confidence >= 0.5:
        status = VerificationStatus.AMBIGUOUS
    else:
        status = VerificationStatus.NOT_FOUND

    return VerifiedReference(
        ref_id=ref.id,
        status=status,
        confidence=round(best_confidence, 3),
        source="semantic_scholar",
        **canonical,
    )
