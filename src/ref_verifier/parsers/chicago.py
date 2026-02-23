"""Chicago/Turabian reference parser.

Notes-Bibliography pattern: LastName, FirstName. "Title." Journal Vol, no. Issue (Year): Pages. DOI.
Author-Date pattern: LastName, FirstName. Year. Title. Journal Volume: Pages. DOI.
"""

import re

from ..models import Reference
from .base import BaseParser

# Chicago Notes-Bibliography: Author. "Title." Journal Vol, no. Issue (Year): Pages.
_CHICAGO_NB_PATTERN = re.compile(
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

# Chicago Author-Date: Author. Year. Title. Journal Volume: Pages.
_CHICAGO_AD_PATTERN = re.compile(
    r"^(?P<authors>.+?)\.\s+"  # Authors.
    r"(?P<year>\d{4}\w?)\.\s+"  # Year.
    r"(?P<title>.+?)\.\s+"  # Title.
    r"(?P<journal>[A-Z].+?)\s+"  # Journal
    r"(?P<volume>\d+)"  # Volume
    r"(?:\s*\((?P<issue>[^)]+)\))?"  # (Issue) optional
    r":\s*(?P<pages>[\d]+[–—-][\d]+)"  # : Pages
    r"\."  # .
    r"(?:\s*(?P<doi>https?://doi\.org/\S+?)\.?)?"  # DOI optional
    r"\s*$",
    re.DOTALL,
)

# Detection signals
_DOUBLE_QUOTES = re.compile(r'"[^"]+?"')
_NO_ISSUE = re.compile(r"no\.\s*\d+")
_YEAR_IN_PARENS_MID = re.compile(r"\(\d{4}\):")  # (Year): for NB variant
_FULL_FIRST_NAME = re.compile(r"^[A-Z][a-z]+,\s+[A-Z][a-z]+")
# Author-Date: "Author. Year." pattern — year after period then period
# Flexible: handles both "Name, First" and "Name,First" (no space)
_AUTHOR_DOT_YEAR_DOT = re.compile(
    r"^[A-Z][a-z]+,\s*[A-Z][a-z]+.*?\.\s*\d{4}\w?\."
)

# Match a complete Chicago AD reference for splitting
_CHICAGO_AD_FULL_REF = re.compile(
    r"[A-Z][a-zA-Z\u00C0-\u024F'-]+,\s+[A-Z][a-z]+"  # first author
    r".+?"  # rest of authors
    r"\.\s+\d{4}\w?\."  # . Year.
    r".+?"  # title and rest
    r"(?=\s[A-Z][a-zA-Z\u00C0-\u024F'-]+,\s+[A-Z][a-z]+.+?\.\s+\d{4}\w?\.|$)",
    re.DOTALL,
)


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

    def split_references(self, reference_section: str) -> list[str]:
        """Split Chicago references, handling multi-line PDF text."""
        text = reference_section.strip()

        # Try base splitting first (numbered or blank-line separated)
        base_refs = super().split_references(reference_section)

        # Check if base split produced complete references (have Author. Year.)
        ad_pattern = re.compile(r"^[A-Z].*?\.\s*\d{4}\w?\.")
        ad_matches = sum(1 for r in base_refs if ad_pattern.match(r))
        if len(base_refs) > 3 and ad_matches > len(base_refs) * 0.5:
            return base_refs

        # Join all lines and split on Author-Date pattern
        joined = re.sub(r"\s*\n\s*", " ", text)

        # Remove page headers (e.g. "Humanities 2024, 13, 64 22 of 23")
        joined = re.sub(
            r"\s+[A-Z][a-z]+\s+\d{4},\s*\d+,\s*\d+\s+\d+\s+of\s+\d+\s+",
            " ",
            joined,
        )
        # Remove standalone page numbers/headers (e.g. "Draft: November 21, 2022 Page 22")
        joined = re.sub(
            r"\s+Draft:.*?Page\s+\d+\s+", " ", joined
        )

        # Split on Author-Date pattern: "Author, First... Year."
        # Use flexible lookbehind (after period, page number, or DOI)
        parts = re.split(
            r"(?<=[\.\d])\s+(?=[A-Z][a-zA-Z\u00C0-\u024F'-]+,\s*[A-Z][a-z]+.*?\.\s*\d{4}\w?\.)",
            joined,
        )
        if len(parts) > 3:
            return [p.strip() for p in parts if p.strip()]

        # Try finding complete references with regex
        refs = _CHICAGO_AD_FULL_REF.findall(joined)
        if refs:
            return [r.strip() for r in refs if r.strip()]

        return base_refs

    def score_match(self, raw_text: str) -> float:
        score = 0.0
        # Notes-Bibliography signals
        if _DOUBLE_QUOTES.search(raw_text):
            score += 0.2
        if _NO_ISSUE.search(raw_text):
            score += 0.2
        if _YEAR_IN_PARENS_MID.search(raw_text):
            score += 0.3
        # Author-Date signals: "Author. Year. Title."
        if _AUTHOR_DOT_YEAR_DOT.search(raw_text):
            score += 0.45
        # Full first names (not just initials) — common in both variants
        if _FULL_FIRST_NAME.match(raw_text):
            score += 0.15
        # No [#] bracket (not IEEE)
        if not re.match(r"^\s*\[\d+\]", raw_text):
            score += 0.05
        # No "pp." (not Harvard)
        if "pp." not in raw_text and "pp " not in raw_text:
            score += 0.1
        # No (Year) after author — distinguishes from APA/Harvard
        if not re.search(r"\(\d{4}\)\s*[.,]", raw_text):
            score += 0.05
        return min(score, 1.0)

    def parse_reference(self, raw_text: str, ref_id: str) -> Reference | None:
        text = raw_text.strip()

        # Try Notes-Bibliography pattern first
        m = _CHICAGO_NB_PATTERN.match(text)
        if m:
            return self._build_ref(m, raw_text, ref_id, nb=True)

        # Try Author-Date pattern
        m = _CHICAGO_AD_PATTERN.match(text)
        if m:
            return self._build_ref(m, raw_text, ref_id, nb=False)

        return self._parse_loose(text, raw_text, ref_id)

    def _build_ref(self, m, raw_text, ref_id, nb=True):
        doi = m.group("doi")
        if doi:
            doi = re.sub(r"^https?://doi\.org/", "", doi).rstrip(".")

        year_str = m.group("year")
        year = int(re.match(r"\d{4}", year_str).group())

        return Reference(
            id=ref_id,
            authors=_parse_chicago_authors(m.group("authors")),
            title=m.group("title").strip(),
            year=year,
            journal=m.group("journal").strip(),
            volume=m.group("volume"),
            pages=m.group("pages"),
            doi=doi,
            raw_text=raw_text.strip(),
        )

    def _parse_loose(self, text: str, raw_text: str, ref_id: str) -> Reference | None:
        """Looser fallback for Chicago-like references."""
        # Try NB style first (double-quoted title)
        ref = self._parse_loose_nb(text, raw_text, ref_id)
        if ref:
            return ref

        # Try Author-Date style (Author. Year. Title.)
        return self._parse_loose_ad(text, raw_text, ref_id)

    def _parse_loose_nb(self, text: str, raw_text: str, ref_id: str) -> Reference | None:
        """Loose parsing for Notes-Bibliography variant."""
        title_match = re.search(r'"(.+?)"', text)
        if not title_match:
            return None

        year_match = re.search(r"\((\d{4})\)", text)
        if not year_match:
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

    def _parse_loose_ad(self, text: str, raw_text: str, ref_id: str) -> Reference | None:
        """Loose parsing for Author-Date variant."""
        # Look for "Author. Year. Title." pattern
        year_match = re.search(r"\.\s+(\d{4}\w?)\.\s+", text)
        if not year_match:
            return None

        authors_str = text[: year_match.start()].strip()
        after_year = text[year_match.end() :].strip()

        if not authors_str or not after_year:
            return None

        # Extract DOI
        doi = None
        doi_match = re.search(r"https?://doi\.org/(\S+?)\.?\s*$", after_year)
        if doi_match:
            doi = doi_match.group(1).rstrip(".")
            after_year = after_year[: doi_match.start()].strip()

        # Try to split "Title. Journal Volume: Pages."
        # Title ends at a period followed by a journal-like name
        # (starts with uppercase, usually a known journal)
        title = None
        journal = None
        volume = None
        pages = None

        # Try to find "Journal Volume: Pages" at the end
        jvp_match = re.search(
            r"([A-Z][A-Za-z\s&:]+?)\s+(\d+)(?:\s*\([^)]*\))?\s*:\s*([\d]+[–—-][\d]+)\s*\.?\s*$",
            after_year,
        )
        if jvp_match:
            title = after_year[: jvp_match.start()].strip().rstrip(".")
            journal = jvp_match.group(1).strip()
            volume = jvp_match.group(2)
            pages = jvp_match.group(3)
        else:
            # Try "Journal, Volume(Issue), Pages" format (NBER style)
            jvp_match2 = re.search(
                r"([A-Z][A-Za-z\s&:]+?),\s*(\d+)(?:\([^)]*\))?,?\s*([\d]+[–—-][\d]+)?\s*\.?\s*$",
                after_year,
            )
            if jvp_match2:
                title = after_year[: jvp_match2.start()].strip().rstrip(".")
                journal = jvp_match2.group(1).strip()
                volume = jvp_match2.group(2)
                pages = jvp_match2.group(3)
            else:
                # Just extract title as first sentence
                parts = after_year.split(". ", 1)
                title = parts[0].strip().rstrip(".")
                if len(parts) > 1:
                    rest = parts[1].strip()
                    # Try to get journal name from rest
                    j_match = re.match(r"([A-Z][A-Za-z\s&:]+?)(?:\s+\d|\.|$)", rest)
                    if j_match:
                        journal = j_match.group(1).strip()

        if not title or len(title) < 3:
            return None

        year_str = year_match.group(1)
        year = int(re.match(r"\d{4}", year_str).group())

        return Reference(
            id=ref_id,
            authors=_parse_chicago_authors(authors_str),
            title=title,
            year=year,
            journal=journal,
            volume=volume,
            pages=pages,
            doi=doi,
            raw_text=raw_text.strip(),
        )
