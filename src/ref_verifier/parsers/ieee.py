"""IEEE reference parser.

Pattern: [#] F. M. LastName, "Title," Journal, vol. X, no. Y, pp. Start-End, Mon. Year, doi: ...
"""

import re

from ..models import Reference
from .base import BaseParser

# Strip leading [#] bracket number
_BRACKET_NUM = re.compile(r"^\s*\[(\d+)\]\s*")

# IEEE: F. M. LastName, ..., "Title," Journal, vol. X, no. Y, pp. Start-End, Mon. Year.
_IEEE_PATTERN = re.compile(
    r'^(?P<authors>.+?),\s*"(?P<title>.+?),"?\s*'  # Authors, "Title,"
    r"(?P<journal>.+?),"  # Journal,
    r"\s*vol\.\s*(?P<volume>\S+),"  # vol. X,
    r"(?:\s*no\.\s*(?P<issue>\S+?),)?"  # no. Y, (optional)
    r"\s*pp?\.\s*(?P<pages>[\d]+(?:\s*[–—-]\s*[\d]+)*),"  # pp. Start-End or p. X,
    r"\s*(?:(?P<month>[A-Z][a-z]+\.?\s+)?(?P<year>\d{4}))"  # Mon. Year
    r"(?:,\s*doi:\s*(?P<doi>\S+?))?"  # , doi: ... (optional)
    r"\.?\s*$",
    re.DOTALL,
)

# Signals for detection
_BRACKET_START = re.compile(r"^\s*\[\d+\]")
_QUOTED_TITLE = re.compile(r'".+?"')
_VOL_NO_PP = re.compile(r"vol\.\s*\d+")
_IEEE_DOI = re.compile(r"doi:\s*\S+")


def _parse_ieee_authors(author_str: str) -> list[str]:
    """Parse IEEE author string: F. M. Last, F. M. Last, and F. M. Last."""
    author_str = author_str.strip()
    # Replace " and " with ", "
    author_str = re.sub(r"\s+and\s+", ", ", author_str)
    parts = [a.strip() for a in author_str.split(",") if a.strip()]

    # IEEE format: initials before last name, so "F. M. LastName" is one author
    # Rejoin parts that are just initials with their following last name
    authors = []
    current = ""
    for part in parts:
        if current:
            current += ", " + part
        else:
            current = part
        # Check if current looks like a complete author (has a last name = word without period)
        words = current.strip().split()
        has_lastname = any(not w.endswith(".") for w in words)
        if has_lastname:
            authors.append(current.strip())
            current = ""
    if current:
        authors.append(current.strip())
    return authors


class IEEEParser(BaseParser):
    name = "ieee"

    def score_match(self, raw_text: str) -> float:
        score = 0.0
        if _BRACKET_START.match(raw_text):
            score += 0.3
        if _QUOTED_TITLE.search(raw_text):
            score += 0.2
        if _VOL_NO_PP.search(raw_text):
            score += 0.3
        if _IEEE_DOI.search(raw_text):
            score += 0.1
        # Authors with initials first: "F. M. LastName"
        text = _BRACKET_NUM.sub("", raw_text).strip()
        if re.match(r"^[A-Z]\.\s", text):
            score += 0.1
        return min(score, 1.0)

    def split_references(self, reference_section: str) -> list[str]:
        """IEEE refs are numbered [1], [2], etc."""
        parts = re.split(r"\n(?=\s*\[\d+\])", reference_section.strip())
        refs = []
        for p in parts:
            p = p.strip()
            if p:
                # Rejoin multi-line refs into one line
                p = re.sub(r"\s*\n\s*", " ", p)
                refs.append(p)
        return refs if refs else super().split_references(reference_section)

    def parse_reference(self, raw_text: str, ref_id: str) -> Reference | None:
        text = raw_text.strip()
        # Strip [#] prefix
        text = _BRACKET_NUM.sub("", text).strip()

        m = _IEEE_PATTERN.match(text)
        if not m:
            return self._parse_loose(text, raw_text, ref_id)

        doi = m.group("doi")
        if doi:
            doi = doi.rstrip(".")

        return Reference(
            id=ref_id,
            authors=_parse_ieee_authors(m.group("authors")),
            title=m.group("title").strip(),
            year=int(m.group("year")),
            journal=m.group("journal").strip(),
            volume=m.group("volume").rstrip(","),
            pages=m.group("pages"),
            doi=doi,
            raw_text=raw_text.strip(),
        )

    def _parse_loose(self, text: str, raw_text: str, ref_id: str) -> Reference | None:
        """Looser fallback for IEEE-like references."""
        # Must have quoted title
        title_match = re.search(r'"(.+?)"', text)
        if not title_match:
            return None

        authors_str = text[: title_match.start()].strip().rstrip(",")
        rest = text[title_match.end() :].strip().lstrip(",").strip()

        doi = None
        doi_match = re.search(r"doi:\s*(\S+?)\.?\s*$", rest, re.IGNORECASE)
        if doi_match:
            doi = doi_match.group(1).rstrip(".")

        # Extract volume
        vol_match = re.search(r"vol\.\s*(\S+?),", rest)
        volume = vol_match.group(1) if vol_match else None

        # Extract pages
        pages_match = re.search(r"pp?\.\s*([\d]+(?:\s*[–—-]\s*[\d]+)*)", rest)
        pages = pages_match.group(1) if pages_match else None

        # Extract year: search after pages to avoid matching page numbers as years
        year_search_start = pages_match.end() if pages_match else 0
        year_match = re.search(r"(\d{4})", rest[year_search_start:])
        year = int(year_match.group(1)) if year_match else None

        # Journal: text before "vol." or before the year
        journal = None
        if vol_match:
            journal = rest[: vol_match.start()].strip().rstrip(",").strip()
        elif year_match:
            abs_year_start = year_search_start + year_match.start()
            journal = rest[:abs_year_start].strip().rstrip(",").strip()

        return Reference(
            id=ref_id,
            authors=_parse_ieee_authors(authors_str),
            title=title_match.group(1).strip(),
            year=year,
            journal=journal if journal else None,
            volume=volume,
            pages=pages,
            doi=doi,
            raw_text=raw_text.strip(),
        )
