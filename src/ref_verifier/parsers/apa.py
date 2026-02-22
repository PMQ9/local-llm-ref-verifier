"""APA (7th edition) reference parser.

Pattern: Author, A. A., & Author, B. B. (Year). Title. Journal, Vol(Issue), Pages. https://doi.org/...
"""

import re

from ..models import Reference
from .base import BaseParser

# APA: LastName, F. M., ..., & LastName, F. M. (YYYY). Title. Journal, Vol(Iss), Pages. DOI
_APA_PATTERN = re.compile(
    r"^(?P<authors>.+?)\s+"  # Authors block
    r"\((?P<year>\d{4})\)\.\s+"  # (Year).
    r"(?P<title>.+?)\.\s+"  # Title.
    r"(?P<journal>[^,]+?),"  # Journal,
    r"\s*(?P<volume>\d+)"  # Volume
    r"(?:\((?P<issue>[^)]+)\))?"  # (Issue) optional
    r"(?:,\s*(?P<pages>[\d]+[–—-][\d]+|Article\s+\w+))?"  # , Pages or Article
    r"\."  # .
    r"(?:\s*(?P<doi>https?://doi\.org/\S+))?"  # DOI optional
    r"\s*$",
    re.DOTALL,
)

# Simpler pattern for detection scoring
_APA_YEAR_AFTER_AUTHOR = re.compile(r"[A-Z][a-z]+,\s+[A-Z]\.\s.*?\(\d{4}\)\.")
_APA_DOI = re.compile(r"https://doi\.org/")


def _parse_apa_authors(author_str: str) -> list[str]:
    """Parse APA author string into a list of names."""
    # Remove trailing period if present
    author_str = author_str.strip().rstrip(".")
    # Handle "& " or ", &" separator for last author
    author_str = re.sub(r",?\s*&\s*", ", ", author_str)
    # Handle "..." for 21+ authors
    author_str = re.sub(r"\.\.\.", ",", author_str)
    # Split on ", " but not within "Last, F." pairs
    # APA authors: "Last, F. M." — split on the pattern between authors
    parts = re.split(r",\s+(?=[A-Z][a-z])", author_str)
    authors = []
    for part in parts:
        part = part.strip().rstrip(",")
        if part:
            authors.append(part)
    return authors


class APAParser(BaseParser):
    name = "apa"

    def score_match(self, raw_text: str) -> float:
        score = 0.0
        # (Year) after authors is the strongest APA signal
        if _APA_YEAR_AFTER_AUTHOR.search(raw_text):
            score += 0.4
        # No square brackets at start (not IEEE/Vancouver)
        if not re.match(r"^\s*\[\d+\]", raw_text):
            score += 0.1
        # Title NOT in quotes (not IEEE/Chicago/Harvard)
        if '"' not in raw_text and "'" not in raw_text:
            score += 0.15
        # DOI as https://doi.org/ (APA-specific format)
        if _APA_DOI.search(raw_text):
            score += 0.15
        # Authors with "Last, F." pattern
        if re.match(r"^[A-Z][a-z]+,\s+[A-Z]\.", raw_text):
            score += 0.2
        return min(score, 1.0)

    def parse_reference(self, raw_text: str, ref_id: str) -> Reference | None:
        m = _APA_PATTERN.match(raw_text.strip())
        if not m:
            return self._parse_loose(raw_text, ref_id)

        doi = m.group("doi")
        if doi:
            # Clean trailing period from DOI
            doi = doi.rstrip(".")
            # Extract just the DOI identifier
            doi = re.sub(r"^https?://doi\.org/", "", doi)

        return Reference(
            id=ref_id,
            authors=_parse_apa_authors(m.group("authors")),
            title=m.group("title").strip(),
            year=int(m.group("year")),
            journal=m.group("journal").strip(),
            volume=m.group("volume"),
            pages=m.group("pages"),
            doi=doi,
            raw_text=raw_text.strip(),
        )

    def _parse_loose(self, raw_text: str, ref_id: str) -> Reference | None:
        """Looser fallback parsing for APA-like references that don't match exactly."""
        text = raw_text.strip()

        # Must at least have (Year) pattern
        year_match = re.search(r"\((\d{4})\)\.", text)
        if not year_match:
            return None

        authors_str = text[: year_match.start()].strip()
        rest = text[year_match.end() :].strip()

        # Extract DOI
        doi = None
        doi_match = re.search(r"https?://doi\.org/(\S+?)\.?\s*$", rest)
        if doi_match:
            doi = doi_match.group(1).rstrip(".")
            rest = rest[: doi_match.start()].strip()

        # Split rest into title and journal info
        # Title ends at the first period followed by a capital letter (journal name)
        title_match = re.match(r"(.+?)\.\s+([A-Z].+)", rest, re.DOTALL)
        title = rest
        journal = None
        volume = None
        pages = None

        if title_match:
            title = title_match.group(1).strip()
            journal_part = title_match.group(2).strip().rstrip(".")

            # Try to extract journal, volume, pages
            jvp = re.match(
                r"(.+?),\s*(\d+)(?:\([^)]*\))?,?\s*([\d]+[–—-][\d]+|Article\s+\w+)?",
                journal_part,
            )
            if jvp:
                journal = jvp.group(1).strip()
                volume = jvp.group(2)
                pages = jvp.group(3)
            else:
                journal = journal_part

        return Reference(
            id=ref_id,
            authors=_parse_apa_authors(authors_str),
            title=title,
            year=int(year_match.group(1)),
            journal=journal,
            volume=volume,
            pages=pages,
            doi=doi,
            raw_text=raw_text.strip(),
        )
