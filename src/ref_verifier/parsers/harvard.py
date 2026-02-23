"""Harvard reference parser.

Pattern (traditional): LastName, F.M. (Year) 'Title', Journal, Vol(Issue), pp. Pages. doi:...
Pattern (RBA variant): LastName FI and FI LastName (Year), 'Title', Journal, Vol(Issue), pp Pages.
"""

import re

from ..models import Reference
from .base import BaseParser

# Harvard strict: Authors (Year), 'Title', Journal, Vol(Issue), pp Pages.
_HARVARD_PATTERN = re.compile(
    r"^(?P<authors>.+?)\s+"  # Authors
    r"\((?P<year>\d{4}(?:\w)?)\)"  # (Year) or (2009a)
    r"[,.]?\s+"  # optional comma/period after year
    r"['\u2018\u2019](?P<title>.+?)['\u2018\u2019],?\s+"  # 'Title'
    r"(?P<journal>.+?),"  # Journal,
    r"\s*(?:vol\.\s*)?(?P<volume>\d+)"  # vol. X or just X
    r"(?:\((?P<issue>[^)]+)\))?"  # (Issue) optional
    r"(?:,\s*pp\.?\s*(?P<pages>[\d]+[–—-][\d]+))?"  # pp Pages optional
    r"\."  # .
    r"(?:\s*(?:doi:\s*)?(?P<doi>\S+?)\.?)?"  # doi optional
    r"\s*$",
    re.DOTALL,
)

# Detection signals
_SINGLE_QUOTES = re.compile(r"[\u2018\u2019'].*?[\u2018\u2019']")
_YEAR_AFTER_AUTHOR_PAREN = re.compile(
    r"[A-Z][a-z]+.*?\(\d{4}\w?\)[,\s]"
)
_PP_PREFIX = re.compile(r"\bpp\.?\s*\d+")

# Match a complete Harvard reference for splitting: starts with author(s) (Year)
# Handles both "LastName, F." and "LastName FI" author formats.
_HARVARD_FULL_REF = re.compile(
    r"(?:^|(?<=\.\s))"  # start of string or after ". "
    r"[A-Z][a-zA-Z\u00C0-\u024F'-]+[\s,]"  # first author starts with uppercase
    r".+?"  # author list
    r"\(\d{4}\w?\)"  # (Year)
    r".+?"  # rest of reference
    r"(?=\s[A-Z][a-zA-Z\u00C0-\u024F'-]+[\s,].+?\(\d{4}\w?\)|$)",  # lookahead next ref or end
    re.DOTALL,
)


def _parse_harvard_authors(author_str: str) -> list[str]:
    """Parse Harvard authors.

    Handles multiple formats:
    - LastName, F.M. and LastName, F.  (traditional)
    - LastName FI, FI LastName and FI LastName  (RBA style)
    """
    author_str = author_str.strip().rstrip(".,")
    # Replace " and " with a delimiter
    author_str = re.sub(r",?\s+and\s+", " ;; ", author_str)
    if ";;" in author_str:
        parts = [a.strip() for a in author_str.split(";;") if a.strip()]
        return parts

    # Single author or comma-separated
    # RBA style: "LastName FI, FI LastName, FI LastName"
    # Traditional: "LastName, F., LastName, F."
    # Try to detect RBA style (no periods after initials)
    if re.match(r"^[A-Z][a-z]+ [A-Z]{1,3}[,\s]", author_str):
        # RBA style: split on ", " between authors
        parts = [a.strip() for a in author_str.split(",") if a.strip()]
        return parts

    # Traditional: Split on ", " followed by uppercase (new author)
    parts = re.split(r",\s+(?=[A-Z][a-z])", author_str)
    return [p.strip().rstrip(",") for p in parts if p.strip()]


class HarvardParser(BaseParser):
    name = "harvard"

    def split_references(self, reference_section: str) -> list[str]:
        """Split Harvard references, handling line-wrapped PDF text."""
        text = reference_section.strip()

        # Join all lines (PDF wraps long references across lines)
        joined = re.sub(r"\s*\n\s*", " ", text)

        # Remove page headers/footers (e.g. standalone "32" or "Page 5 of 10")
        joined = re.sub(
            r"\s+\d{1,3}\s+(?=[A-Z][a-zA-Z\u00C0-\u024F'-]+[\s,].*?\(\d{4})", " ", joined
        )

        # Split on Harvard author-year pattern:
        # A new reference starts with an uppercase word (author surname)
        # followed eventually by (Year)
        parts = re.split(
            r"(?<=\.)\s+(?=[A-Z][a-zA-Z\u00C0-\u024F'-]+[\s,].{0,200}?\(\d{4}\w?\))",
            joined,
        )
        if len(parts) > 3:
            return [p.strip() for p in parts if p.strip()]

        # Fall back to base implementation
        return super().split_references(reference_section)

    def score_match(self, raw_text: str) -> float:
        score = 0.0
        # Single quotes around title (strong Harvard signal, BUT only if year
        # is in parentheses — otherwise it's likely Chicago AD with quotes)
        has_paren_year = bool(_YEAR_AFTER_AUTHOR_PAREN.search(raw_text))
        if _SINGLE_QUOTES.search(raw_text):
            if has_paren_year:
                score += 0.35
            else:
                score += 0.1  # weak signal without (Year)
        # (Year) after author — the KEY Harvard signal
        if has_paren_year:
            score += 0.25
        # "pp" or "pp." before page numbers
        if _PP_PREFIX.search(raw_text):
            score += 0.2
        # No [#] bracket (not IEEE)
        if not re.match(r"^\s*\[\d+\]", raw_text):
            score += 0.1
        # Author with "Last, F." or "Last FI" pattern
        if re.match(r"^[A-Z][a-z]+[,\s]+[A-Z][\.\s]", raw_text):
            score += 0.1
        # Negative: "Author. Year." pattern = Chicago AD, not Harvard
        if re.match(r"^[A-Z][a-z]+,\s*[A-Z][a-z]+.*?\.\s*\d{4}\w?\.", raw_text):
            score -= 0.2
        return max(min(score, 1.0), 0.0)

    def parse_reference(self, raw_text: str, ref_id: str) -> Reference | None:
        text = raw_text.strip()

        m = _HARVARD_PATTERN.match(text)
        if m:
            doi = m.group("doi")
            if doi:
                doi = re.sub(r"^https?://doi\.org/", "", doi).rstrip(".")

            year_str = m.group("year")
            year = int(re.match(r"\d{4}", year_str).group())

            return Reference(
                id=ref_id,
                authors=_parse_harvard_authors(m.group("authors")),
                title=m.group("title").strip(),
                year=year,
                journal=m.group("journal").strip(),
                volume=m.group("volume"),
                pages=m.group("pages"),
                doi=doi,
                raw_text=raw_text.strip(),
            )

        return self._parse_loose(text, raw_text, ref_id)

    def _parse_loose(self, text: str, raw_text: str, ref_id: str) -> Reference | None:
        """Looser fallback for Harvard-like references."""
        # Must have (Year) — with optional letter suffix like (2009a)
        year_match = re.search(r"\((\d{4})\w?\)", text)
        if not year_match:
            return None

        # Try to find single-quoted title
        title_match = re.search(r"[\u2018\u2019'](.+?)[\u2018\u2019']", text)

        authors_str = text[: year_match.start()].strip()
        after_year = text[year_match.end() :].strip().lstrip(".,").strip()

        if title_match and title_match.start() > year_match.end() - 5:
            title = title_match.group(1).strip()
            rest = text[title_match.end() :].strip().lstrip(",").strip()
        else:
            # No single-quoted title — try to extract title as first
            # comma-separated segment after year
            # Format: (Year), 'Title', Journal  OR  (Year) Title. Journal
            parts = re.split(r",\s+", after_year, maxsplit=1)
            if len(parts) >= 1:
                title = parts[0].strip().strip("''\u2018\u2019").rstrip(".")
                rest = parts[1] if len(parts) > 1 else ""
            else:
                return None

        if not title or len(title) < 5:
            return None

        # Extract DOI (various formats)
        doi = None
        doi_match = re.search(
            r"(?:doi:\s*|https?://doi\.org/)(\S+?)\.?\s*$", rest, re.IGNORECASE
        )
        if doi_match:
            doi = doi_match.group(1).rstrip(".")
            rest = rest[: doi_match.start()].strip()

        # Extract pages (pp or pp.)
        pages = None
        pages_match = re.search(r"\bpp\.?\s*([\d]+[–—-][\d]+)", rest)
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
            # Take text up to first comma or period as journal
            j_match = re.match(r"([^,]+)", rest)
            if j_match:
                journal = j_match.group(1).strip().rstrip(".")

        year = int(re.match(r"\d{4}", year_match.group(1)).group())

        return Reference(
            id=ref_id,
            authors=_parse_harvard_authors(authors_str),
            title=title,
            year=year,
            journal=journal if journal else None,
            volume=volume,
            pages=pages,
            doi=doi,
            raw_text=raw_text.strip(),
        )
