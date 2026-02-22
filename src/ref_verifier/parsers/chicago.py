"""Chicago/Turabian (Notes-Bibliography) reference parser.

Bibliography pattern: LastName, FirstName. "Title." Journal Vol, no. Issue (Year): Pages. DOI.
"""

import re

from ..models import Reference
from .base import BaseParser

# Chicago bibliography: Author. "Title." Journal Vol, no. Issue (Year): Pages.
_CHICAGO_PATTERN = re.compile(
    r'^(?P<authors>.+?)\.\s+'  # Authors.
    r'"(?P<title>.+?)\.?"\s+'  # "Title."
    r"(?P<journal>.+?)\s+"  # Journal
    r"(?P<volume>\d+),\s*"  # Volume,
    r"no\.\s*(?P<issue>\d+)\s*"  # no. Issue
    r"\((?P<year>\d{4})\):\s*"  # (Year):
    r"(?P<pages>[\d]+[–—-][\d]+)"  # Pages
    r"\."  # .
    r"(?:\s*(?P<doi>https?://doi\.org/\S+?)\.?)?"  # DOI optional
    r"\s*$",
    re.DOTALL,
)

# Detection signals
_DOUBLE_QUOTES = re.compile(r'"[^"]+?"')
_NO_ISSUE = re.compile(r"no\.\s*\d+")
_YEAR_IN_PARENS_MID = re.compile(r"\(\d{4}\):")  # (Year): near the end is Chicago
_FULL_FIRST_NAME = re.compile(r"^[A-Z][a-z]+,\s+[A-Z][a-z]+")


def _parse_chicago_authors(author_str: str) -> list[str]:
    """Parse Chicago authors: LastName, FirstName, and FirstName LastName."""
    author_str = author_str.strip().rstrip(".")
    # Replace " and " with delimiter
    author_str = re.sub(r",?\s+and\s+", " ;; ", author_str)
    if ";;" in author_str:
        parts = [a.strip() for a in author_str.split(";;") if a.strip()]
        return parts
    # Single author: "LastName, FirstName MiddleName"
    return [author_str.strip()] if author_str else []


class ChicagoParser(BaseParser):
    name = "chicago"

    def score_match(self, raw_text: str) -> float:
        score = 0.0
        # Double quotes around title
        if _DOUBLE_QUOTES.search(raw_text):
            score += 0.2
        # "no." before issue number
        if _NO_ISSUE.search(raw_text):
            score += 0.2
        # (Year): pattern — year in parens followed by colon
        if _YEAR_IN_PARENS_MID.search(raw_text):
            score += 0.3
        # Full first names (not just initials)
        if _FULL_FIRST_NAME.match(raw_text):
            score += 0.15
        # No [#] bracket (not IEEE)
        if not re.match(r"^\s*\[\d+\]", raw_text):
            score += 0.05
        # No "pp." (not Harvard)
        if "pp." not in raw_text:
            score += 0.1
        return min(score, 1.0)

    def parse_reference(self, raw_text: str, ref_id: str) -> Reference | None:
        text = raw_text.strip()

        m = _CHICAGO_PATTERN.match(text)
        if not m:
            return self._parse_loose(text, raw_text, ref_id)

        doi = m.group("doi")
        if doi:
            doi = re.sub(r"^https?://doi\.org/", "", doi).rstrip(".")

        return Reference(
            id=ref_id,
            authors=_parse_chicago_authors(m.group("authors")),
            title=m.group("title").strip(),
            year=int(m.group("year")),
            journal=m.group("journal").strip(),
            volume=m.group("volume"),
            pages=m.group("pages"),
            doi=doi,
            raw_text=raw_text.strip(),
        )

    def _parse_loose(self, text: str, raw_text: str, ref_id: str) -> Reference | None:
        """Looser fallback for Chicago-like references."""
        # Must have double-quoted title
        title_match = re.search(r'"(.+?)"', text)
        if not title_match:
            return None

        year_match = re.search(r"\((\d{4})\)", text)
        if not year_match:
            # Chicago sometimes has year without parens at end
            year_match = re.search(r"(\d{4})", text)
        if not year_match:
            return None

        authors_str = text[: title_match.start()].strip().rstrip(".")
        rest = text[title_match.end() :].strip()

        doi = None
        doi_match = re.search(r"https?://doi\.org/(\S+?)\.?\s*$", rest)
        if doi_match:
            doi = doi_match.group(1).rstrip(".")
            rest = rest[: doi_match.start()].strip()

        # Extract volume, issue, pages from rest
        volume = None
        pages = None
        journal = None

        vol_match = re.search(r"(\d+),\s*no\.\s*\d+", rest)
        if vol_match:
            volume = vol_match.group(1)
            journal = rest[: vol_match.start()].strip().rstrip(".")

        pages_match = re.search(r":\s*([\d]+[–—-][\d]+)", rest)
        if pages_match:
            pages = pages_match.group(1)

        if not journal:
            # Journal is text between title and year/volume
            j_text = rest.lstrip(".").strip()
            if j_text:
                j_parts = re.split(r"\d+", j_text, maxsplit=1)
                if j_parts[0].strip():
                    journal = j_parts[0].strip().rstrip(",").strip()

        return Reference(
            id=ref_id,
            authors=_parse_chicago_authors(authors_str),
            title=title_match.group(1).strip().rstrip("."),
            year=int(year_match.group(1)),
            journal=journal,
            volume=volume,
            pages=pages,
            doi=doi,
            raw_text=raw_text.strip(),
        )
