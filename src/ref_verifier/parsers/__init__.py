"""Rule-based reference parsers for common academic citation styles."""

from .apa import APAParser
from .chicago import ChicagoParser
from .harvard import HarvardParser
from .ieee import IEEEParser
from .vancouver import VancouverParser
from .detector import detect_style, PARSERS

__all__ = [
    "APAParser",
    "ChicagoParser",
    "HarvardParser",
    "IEEEParser",
    "VancouverParser",
    "detect_style",
    "PARSERS",
]
