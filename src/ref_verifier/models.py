"""Pydantic data models shared across all pipeline stages.

These models serve double duty:
1. Data validation and serialization between stages
2. Structured output schemas for Ollama (via model_json_schema())
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Stage 1: Reference Extraction ---


class Reference(BaseModel):
    """A single reference extracted from the manuscript."""

    id: str = Field(description="Short key, e.g. 'ref_01'")
    authors: list[str] = Field(description="List of author names as they appear")
    title: str
    year: Optional[int] = None
    journal: Optional[str] = Field(None, description="Journal or venue name")
    volume: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    raw_text: str = Field(description="Original reference string from PDF")


class ExtractionResult(BaseModel):
    """Output of Stage 1: extracted references from a manuscript."""

    source_pdf: str
    references: list[Reference]
    model_used: str = Field(description="Ollama model name used for extraction")


# --- Stage 2: Online Verification ---


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class VerifiedReference(BaseModel):
    """A reference with verification metadata attached."""

    ref_id: str = Field(description="Matches Reference.id")
    status: VerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    source: Optional[str] = Field(
        None,
        description="Which API confirmed it: crossref, semantic_scholar, google_scholar",
    )
    canonical_title: Optional[str] = None
    canonical_doi: Optional[str] = None
    canonical_authors: Optional[list[str]] = None
    canonical_year: Optional[int] = None
    abstract: Optional[str] = Field(
        None, description="Paper abstract from the source API"
    )
    tldr: Optional[str] = Field(
        None, description="Short summary (e.g. Semantic Scholar TLDR)"
    )
    notes: Optional[str] = None


class VerificationResult(BaseModel):
    """Output of Stage 2: verified references with stats."""

    references: list[VerifiedReference]
    stats: dict = Field(
        default_factory=dict,
        description='e.g. {"verified": 12, "not_found": 3, "ambiguous": 1}',
    )


# --- Stage 3: Audit ---


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class AuditIssue(BaseModel):
    issue_type: str = Field(
        description="e.g. uncited_reference, missing_from_list, misquoted_claim, unsupported_claim"
    )
    severity: IssueSeverity
    ref_id: Optional[str] = None
    description: str
    manuscript_excerpt: Optional[str] = Field(
        None, description="Relevant quote from manuscript"
    )


class AuditReport(BaseModel):
    """Output of Stage 3: audit results."""

    issues: list[AuditIssue]
    summary: str = Field(description="Human-readable summary paragraph")
    total_references: int
    verified_count: int
    issues_found: int
