"""CrossRef API client for reference verification.

Queries the CrossRef works API by title and author, then uses fuzzy
string matching to compute a confidence score.
"""

import logging
import re
from typing import Optional

import httpx
from rapidfuzz import fuzz

from ..models import Reference, VerifiedReference, VerificationStatus

logger = logging.getLogger(__name__)

CROSSREF_API_URL = "https://api.crossref.org/works"
TIMEOUT = 30


def _build_query_params(ref: Reference) -> dict:
    params: dict[str, str | int] = {
        "query.bibliographic": ref.title,
        "rows": 3,
    }
    if ref.authors:
        params["query.author"] = ref.authors[0]
    return params


def _compute_confidence(ref: Reference, item: dict) -> float:
    """Compute confidence score between extracted ref and a CrossRef result."""
    # DOI exact match = instant high confidence
    if ref.doi and item.get("DOI"):
        if ref.doi.lower().strip() == item["DOI"].lower().strip():
            return 1.0

    # Title fuzzy match
    api_titles = item.get("title", [])
    if not api_titles:
        return 0.0

    api_title = api_titles[0]
    title_score = fuzz.token_sort_ratio(ref.title.lower(), api_title.lower()) / 100.0

    # Year match bonus
    year_bonus = 0.0
    published = item.get("published", {}).get("date-parts", [[None]])
    if published and published[0] and published[0][0]:
        api_year = published[0][0]
        if ref.year and api_year == ref.year:
            year_bonus = 0.05

    return min(title_score + year_bonus, 1.0)


def _extract_canonical(item: dict) -> dict:
    """Extract canonical metadata from a CrossRef work item."""
    authors = []
    for author in item.get("author", []):
        name_parts = [author.get("given", ""), author.get("family", "")]
        authors.append(" ".join(p for p in name_parts if p))

    titles = item.get("title", [])
    published = item.get("published", {}).get("date-parts", [[None]])
    year = published[0][0] if published and published[0] else None

    # CrossRef abstracts sometimes contain JATS XML tags; strip them
    abstract = item.get("abstract")
    if abstract:
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()

    return {
        "canonical_title": titles[0] if titles else None,
        "canonical_doi": item.get("DOI"),
        "canonical_authors": authors or None,
        "canonical_year": year,
        "abstract": abstract,
    }


def verify_reference(ref: Reference) -> Optional[VerifiedReference]:
    """Verify a single reference against CrossRef. Returns None on failure."""
    try:
        params = _build_query_params(ref)
        response = httpx.get(
            CROSSREF_API_URL,
            params=params,
            timeout=TIMEOUT,
            headers={"User-Agent": "local-llm-ref-verifier/0.1.0"},
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.warning("CrossRef API error for '%s': %s", ref.title[:50], e)
        return None

    items = data.get("message", {}).get("items", [])
    if not items:
        return None

    # Score each result and pick the best
    best_confidence = 0.0
    best_item = items[0]
    for item in items:
        conf = _compute_confidence(ref, item)
        if conf > best_confidence:
            best_confidence = conf
            best_item = item

    if best_confidence < 0.3:
        return None

    canonical = _extract_canonical(best_item)

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
        source="crossref",
        **canonical,
    )
