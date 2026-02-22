"""Harvard reference parser.

Pattern: LastName, F.M. (Year) 'Title', Journal, Vol(Issue), pp. Pages. doi:...
"""

import re

from ..models import Reference
from .base import BaseParser

# Harvard: Authors (Year) 'Title', Journal, Vol(Issue), pp. Pages.
_HARVARD_PATTERN = re.compile(
    r"^(?P<authors>.+?)\s+"  # Authors
    r"\((?P<year>\d{4})\)\s+"  # (Year)
    r"['\u2018\u2019](?P<title>.+?)['\u2018\u2019],?\s+"  # 'Title'
    r"(?P<journal>.+?),"  # Journal,
    r"\s*(?:vol\.\s*)?(?P<volume>\d+)"  # vol. X or just X
    r"(?:\((?P<issue>[^)]+)\))?"  # (Issue) optional
    r",\s*pp\.\s*(?P<pages>[\d]+[–—-][\d]+)"  # pp. Pages
    r"\."  # .
    r"(?:\s*doi:\s*(?P<doi>\S+?)\.?)?"  # doi: optional
    r"\s*$",
    re.DOTALL,
)

# Detection signals
_SINGLE_QUOTES = re.compile(r"[\u2018\u2019'].*?[\u2018\u2019']")
_YEAR_AFTER_AUTHOR_PAREN = re.compile(r"[A-Z][a-z]+.*?\(\d{4}\)\s")
_PP_PREFIX = re.compile(r"pp\.\s*\d+")


def _parse_harvard_authors(author_str: str) -> list[str]:
    """Parse Harvard authors: LastName, F.M. and LastName, F."""
    author_str = author_str.strip().rstrip(".")
    # Replace " and " with a delimiter
    author_str = re.sub(r"\s+and\s+", " ;; ", author_str)
    # Split on ";;" first, then handle comma-separated within
    if ";;" in author_str:
        parts = [a.strip() for a in author_str.split(";;") if a.strip()]
        return parts

    # Single author or comma-separated "Last, F., Last, F."
    # Split on ", " followed by uppercase (new author)
    parts = re.split(r",\s+(?=[A-Z][a-z])", author_str)
    return [p.strip().rstrip(",") for p in parts if p.strip()]


class HarvardParser(BaseParser):
    name = "harvard"

    def score_match(self, raw_text: str) -> float:
        score = 0.0
        # Single quotes around title (strongest Harvard signal)
        if _SINGLE_QUOTES.search(raw_text):
            score += 0.35
        # (Year) after author
        if _YEAR_AFTER_AUTHOR_PAREN.search(raw_text):
            score += 0.2
        # "pp." before page numbers
        if _PP_PREFIX.search(raw_text):
            score += 0.2
        # No [#] bracket (not IEEE)
        if not re.match(r"^\s*\[\d+\]", raw_text):
            score += 0.1
        # Author with "Last, F." pattern
        if re.match(r"^[A-Z][a-z]+,\s+[A-Z]\.", raw_text):
            score += 0.15
        return min(score, 1.0)

    def parse_reference(self, raw_text: str, ref_id: str) -> Reference | None:
        text = raw_text.strip()

        m = _HARVARD_PATTERN.match(text)
        if not m:
            return self._parse_loose(text, raw_text, ref_id)

        doi = m.group("doi")
        if doi:
            doi = doi.rstrip(".")

        return Reference(
            id=ref_id,
            authors=_parse_harvard_authors(m.group("authors")),
            title=m.group("title").strip(),
            year=int(m.group("year")),
            journal=m.group("journal").strip(),
            volume=m.group("volume"),
            pages=m.group("pages"),
            doi=doi,
            raw_text=raw_text.strip(),
        )

    def _parse_loose(self, text: str, raw_text: str, ref_id: str) -> Reference | None:
        """Looser fallback for Harvard-like references."""
        # Must have (Year) and single-quoted title
        year_match = re.search(r"\((\d{4})\)", text)
        title_match = re.search(r"[\u2018\u2019'](.+?)[\u2018\u2019']", text)
        if not year_match or not title_match:
            return None

        authors_str = text[: year_match.start()].strip()
        rest = text[title_match.end() :].strip().lstrip(",").strip()

        doi = None
        doi_match = re.search(r"doi:\s*(\S+?)\.?\s*$", rest, re.IGNORECASE)
        if doi_match:
            doi = doi_match.group(1).rstrip(".")
            rest = rest[: doi_match.start()].strip()

        # Extract pages
        pages = None
        pages_match = re.search(r"pp\.\s*([\d]+[–—-][\d]+)", rest)
        if pages_match:
            pages = pages_match.group(1)

        # Extract volume
        volume = None
        vol_match = re.search(r"(?:vol\.\s*)?(\d+)(?:\([^)]*\))?", rest)
        if vol_match:
            volume = vol_match.group(1)

        # Journal is the text before volume
        journal = None
        if vol_match:
            journal = rest[: vol_match.start()].strip().rstrip(",").strip()
        elif rest:
            journal = rest.rstrip(".").strip()

        return Reference(
            id=ref_id,
            authors=_parse_harvard_authors(authors_str),
            title=title_match.group(1).strip(),
            year=int(year_match.group(1)),
            journal=journal if journal else None,
            volume=volume,
            pages=pages,
            doi=doi,
            raw_text=raw_text.strip(),
        )
