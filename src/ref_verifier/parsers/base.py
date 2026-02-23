"""Base class for citation style parsers."""

import re
from abc import ABC, abstractmethod

from ..models import Reference


class BaseParser(ABC):
    """Base class for rule-based reference parsers."""

    name: str = "unknown"

    @abstractmethod
    def parse_reference(self, raw_text: str, ref_id: str) -> Reference | None:
        """Parse a single reference string into a Reference object.

        Returns None if the text doesn't match this parser's style.
        """
        ...

    @abstractmethod
    def score_match(self, raw_text: str) -> float:
        """Score how well a reference string matches this parser's style.

        Returns 0.0–1.0, where 1.0 = perfect match for this style.
        Used by the style detector to pick the best parser.
        """
        ...

    def split_references(self, reference_section: str) -> list[str]:
        """Split a reference section into individual reference strings.

        Default implementation tries numbered entries, blank lines, then
        falls back to joining all lines into one block for subclass splitting.
        Override for style-specific splitting.
        """
        text = reference_section.strip()

        # Try numbered splitting first: [1], [2], ... or 1. 2. ...
        # Limit to 1-3 digit numbers to avoid splitting on years like "2020."
        numbered = re.split(r"\n(?=\[\d+\]|\d{1,3}\.\s)", text)
        if len(numbered) > 1:
            return [re.sub(r"\s*\n\s*", " ", r).strip() for r in numbered if r.strip()]

        # Fall back to blank-line splitting
        paragraphs = re.split(r"\n\s*\n", text)
        if len(paragraphs) > 1:
            return [re.sub(r"\s*\n\s*", " ", p).strip() for p in paragraphs if p.strip()]

        # Last resort: each line is a reference (common in dense reference lists)
        lines = text.split("\n")
        return [l.strip() for l in lines if l.strip()]

    def parse_all(self, reference_section: str) -> list[Reference]:
        """Parse an entire reference section into a list of References."""
        raw_refs = self.split_references(reference_section)
        results = []
        for i, raw in enumerate(raw_refs):
            ref = self.parse_reference(raw, ref_id=f"ref_{i + 1:02d}")
            if ref:
                results.append(ref)
        return results
