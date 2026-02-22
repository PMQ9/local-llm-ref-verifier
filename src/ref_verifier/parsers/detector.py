"""Auto-detect citation style from reference text and select the best parser."""

import logging

from .apa import APAParser
from .base import BaseParser
from .chicago import ChicagoParser
from .harvard import HarvardParser
from .ieee import IEEEParser
from .vancouver import VancouverParser

logger = logging.getLogger(__name__)

PARSERS: dict[str, BaseParser] = {
    "apa": APAParser(),
    "ieee": IEEEParser(),
    "vancouver": VancouverParser(),
    "harvard": HarvardParser(),
    "chicago": ChicagoParser(),
}


def detect_style(reference_section: str, sample_size: int = 5) -> str:
    """Detect the citation style from a reference section.

    Samples up to `sample_size` references, scores each against all parsers,
    and returns the style name with the highest total score.
    """
    # Get a few sample references to score against
    # Use a generic split first
    lines = [l.strip() for l in reference_section.strip().split("\n") if l.strip()]

    # Group into reference-sized chunks (blank-line or numbered)
    samples: list[str] = []
    current = ""
    for line in lines:
        # New numbered reference starts
        if line and (line[0] == "[" or (line[0].isdigit() and ". " in line[:5])):
            if current:
                samples.append(current.strip())
            current = line
        elif not line:
            if current:
                samples.append(current.strip())
            current = ""
        else:
            current += " " + line if current else line

    if current:
        samples.append(current.strip())

    # If we got very few samples, fall back to paragraph splitting
    if len(samples) < 2:
        samples = [p.strip() for p in reference_section.strip().split("\n\n") if p.strip()]
    if len(samples) < 2:
        samples = lines

    # Take up to sample_size
    samples = samples[:sample_size]

    if not samples:
        logger.warning("No reference samples found, defaulting to APA")
        return "apa"

    # Score each parser
    scores: dict[str, float] = {name: 0.0 for name in PARSERS}
    for sample in samples:
        for name, parser in PARSERS.items():
            scores[name] += parser.score_match(sample)

    # Normalize by number of samples
    for name in scores:
        scores[name] /= len(samples)

    best = max(scores, key=lambda k: scores[k])
    logger.info(
        "Style detection scores: %s → selected '%s'",
        {k: round(v, 2) for k, v in sorted(scores.items(), key=lambda x: -x[1])},
        best,
    )
    return best
