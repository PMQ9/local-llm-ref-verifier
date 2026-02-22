"""Google Scholar verification via the scholarly library.

This is the last-resort fallback. Google Scholar aggressively rate-limits
scrapers, so this source includes delays and should only be used when
CrossRef and Semantic Scholar fail.
"""

import logging
import time
from typing import Optional

from rapidfuzz import fuzz

from ..models import Reference, VerifiedReference, VerificationStatus

logger = logging.getLogger(__name__)

DELAY_BETWEEN_REQUESTS = 3.0  # seconds


def _compute_confidence(ref: Reference, pub: dict) -> float:
    """Compute confidence between extracted ref and a scholarly result."""
    bib = pub.get("bib", {})
    api_title = bib.get("title", "")
    if not api_title:
        return 0.0

    title_score = fuzz.token_sort_ratio(ref.title.lower(), api_title.lower()) / 100.0

    # Year match bonus
    year_bonus = 0.0
    pub_year = bib.get("pub_year")
    if ref.year and pub_year:
        try:
            if int(pub_year) == ref.year:
                year_bonus = 0.05
        except (ValueError, TypeError):
            pass

    return min(title_score + year_bonus, 1.0)


def _extract_canonical(pub: dict) -> dict:
    """Extract canonical metadata from a scholarly publication."""
    bib = pub.get("bib", {})
    authors = bib.get("author", [])
    if isinstance(authors, str):
        authors = [authors]

    pub_year = bib.get("pub_year")
    year = None
    if pub_year:
        try:
            year = int(pub_year)
        except (ValueError, TypeError):
            pass

    return {
        "canonical_title": bib.get("title"),
        "canonical_doi": None,  # scholarly doesn't reliably provide DOIs
        "canonical_authors": authors or None,
        "canonical_year": year,
        "abstract": bib.get("abstract"),
    }


def verify_reference(ref: Reference) -> Optional[VerifiedReference]:
    """Verify a single reference against Google Scholar. Returns None on failure."""
    try:
        from scholarly import scholarly
    except ImportError:
        logger.warning("scholarly library not installed, skipping Google Scholar")
        return None

    try:
        time.sleep(DELAY_BETWEEN_REQUESTS)
        search_results = scholarly.search_pubs(ref.title)
        # Take up to 3 results
        pubs = []
        for _ in range(3):
            try:
                pubs.append(next(search_results))
            except StopIteration:
                break
    except Exception as e:
        logger.warning("Google Scholar error for '%s': %s", ref.title[:50], e)
        return None

    if not pubs:
        return None

    best_confidence = 0.0
    best_pub = pubs[0]
    for pub in pubs:
        conf = _compute_confidence(ref, pub)
        if conf > best_confidence:
            best_confidence = conf
            best_pub = pub

    if best_confidence < 0.3:
        return None

    # Fill publication details to get abstract (extra request)
    try:
        best_pub = scholarly.fill(best_pub, sections=["bib"])
    except Exception as e:
        logger.debug("Could not fill Google Scholar details: %s", e)

    canonical = _extract_canonical(best_pub)

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
        source="google_scholar",
        **canonical,
    )
