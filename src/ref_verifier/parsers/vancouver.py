"""Vancouver/NLM and AMA reference parser.

Vancouver: LastName AB, LastName CD. Title. J Abbrev. Year Mon;Vol(Issue):Pages.
AMA:       LastName AB, LastName CD. Title. J Abbrev. Year;Vol(Issue):Pages.

These two styles are very similar — this parser handles both.
"""

import re

from ..models import Reference
from .base import BaseParser

# Strip leading number (Vancouver/AMA are numbered)
_LEADING_NUM = re.compile(r"^\s*(\d+)\.\s*")

# Vancouver/AMA: LastName AB, ... Title. Journal. Year;Vol(Issue):Pages.
_VANC_PATTERN = re.compile(
    r"^(?P<authors>.+?)\.\s+"  # Authors.
    r"(?P<title>.+?)\.\s+"  # Title.
    r"(?P<journal>.+?)\.\s+"  # Journal.
    r"(?P<year>\d{4})"  # Year
    r"(?:\s+[A-Z][a-z]+(?:\s+\d{1,2})?)?"  # Optional month/day
    r";(?P<volume>\d+)"  # ;Volume
    r"(?:\((?P<issue>[^)]+)\))?"  # (Issue) optional
    r":(?P<pages>[\w\d]+[–—-][\w\d]+)"  # :Pages
    r"\."  # .
    r"(?:\s*doi:\s*(?P<doi>\S+?)\.?)?"  # doi: ... optional
    r"\s*$",
    re.DOTALL,
)

# Detection signals
_INITIALS_NO_PERIODS = re.compile(r"[A-Z][a-z]+ [A-Z]{1,4}[,.]")
_SEMICOLON_VOL = re.compile(r"\d{4}[^;]*;\d+")
_NO_QUOTES = re.compile(r'^[^"\']*$')


def _parse_vancouver_authors(author_str: str) -> list[str]:
    """Parse Vancouver/AMA authors: LastName AB, LastName CD, et al."""
    author_str = author_str.strip().rstrip(".")
    # Handle "et al" / "et al."
    author_str = re.sub(r",?\s*et al\.?$", "", author_str)
    parts = [a.strip() for a in author_str.split(",") if a.strip()]
    return parts


class VancouverParser(BaseParser):
    name = "vancouver"

    def score_match(self, raw_text: str) -> float:
        score = 0.0
        text = _LEADING_NUM.sub("", raw_text).strip()

        # LastName AB format (initials without periods)
        if _INITIALS_NO_PERIODS.match(text):
            score += 0.35
        # Year;Volume pattern (semicolon is distinctive)
        if _SEMICOLON_VOL.search(text):
            score += 0.35
        # No quotes around title
        if _NO_QUOTES.match(text):
            score += 0.1
        # No (Year) right after authors (not APA/Harvard)
        if not re.search(r"\(\d{4}\)\.", text[:100]):
            score += 0.1
        # No "vol." or "pp." labels (not IEEE)
        if "vol." not in text.lower() and "pp." not in text.lower():
            score += 0.1
        return min(score, 1.0)

    def split_references(self, reference_section: str) -> list[str]:
        """Vancouver refs are often numbered: 1. 2. etc."""
        parts = re.split(r"\n(?=\s*\d+\.\s)", reference_section.strip())
        refs = []
        for p in parts:
            p = re.sub(r"\s*\n\s*", " ", p.strip())
            if p:
                refs.append(p)
        return refs if len(refs) > 1 else super().split_references(reference_section)

    def parse_reference(self, raw_text: str, ref_id: str) -> Reference | None:
        text = raw_text.strip()
        text = _LEADING_NUM.sub("", text).strip()

        m = _VANC_PATTERN.match(text)
        if not m:
            return self._parse_loose(text, raw_text, ref_id)

        doi = m.group("doi")
        if doi:
            doi = doi.rstrip(".")

        return Reference(
            id=ref_id,
            authors=_parse_vancouver_authors(m.group("authors")),
            title=m.group("title").strip(),
            year=int(m.group("year")),
            journal=m.group("journal").strip(),
            volume=m.group("volume"),
            pages=m.group("pages"),
            doi=doi,
            raw_text=raw_text.strip(),
        )

    def _parse_loose(self, text: str, raw_text: str, ref_id: str) -> Reference | None:
        """Looser fallback for Vancouver-like references."""
        # Need initials-style authors and a year
        if not _INITIALS_NO_PERIODS.match(text):
            return None

        year_match = re.search(r"(\d{4})", text)
        if not year_match:
            return None

        # Split on periods to find authors, title, journal
        # Vancouver: Authors. Title. Journal. Year;...
        period_parts = re.split(r"\.\s+", text, maxsplit=3)
        if len(period_parts) < 2:
            return None

        authors_str = period_parts[0]
        title = period_parts[1] if len(period_parts) > 1 else ""

        journal = None
        volume = None
        pages = None
        doi = None

        if len(period_parts) > 2:
            rest = ". ".join(period_parts[2:])
            # Try to extract journal (text before year)
            journal_match = re.match(r"(.+?)\.?\s*\d{4}", rest)
            if journal_match:
                journal = journal_match.group(1).strip().rstrip(".")

            vol_match = re.search(r";(\d+)", rest)
            volume = vol_match.group(1) if vol_match else None

            pages_match = re.search(r":([\w\d]+[–—-][\w\d]+)", rest)
            pages = pages_match.group(1) if pages_match else None

            doi_match = re.search(r"doi:\s*(\S+?)\.?\s*$", rest, re.IGNORECASE)
            doi = doi_match.group(1).rstrip(".") if doi_match else None

        return Reference(
            id=ref_id,
            authors=_parse_vancouver_authors(authors_str),
            title=title.strip().rstrip("."),
            year=int(year_match.group(1)),
            journal=journal,
            volume=volume,
            pages=pages,
            doi=doi,
            raw_text=raw_text.strip(),
        )
