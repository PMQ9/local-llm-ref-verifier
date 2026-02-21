"""Tests for verification source modules and fuzzy matching logic."""

from ref_verifier.models import Reference, VerificationStatus
from ref_verifier.sources.crossref import _compute_confidence as crossref_confidence
from ref_verifier.sources.semantic_scholar import (
    _compute_confidence as s2_confidence,
)


def _make_ref(**kwargs) -> Reference:
    defaults = {
        "id": "ref_01",
        "authors": ["Smith, J."],
        "title": "Machine learning in healthcare",
        "year": 2020,
        "raw_text": "Smith (2020). Machine learning in healthcare.",
    }
    defaults.update(kwargs)
    return Reference(**defaults)


class TestCrossRefConfidence:
    def test_exact_doi_match(self):
        ref = _make_ref(doi="10.1038/s41591-020-0803-x")
        item = {"DOI": "10.1038/s41591-020-0803-x", "title": ["Different title"]}
        assert crossref_confidence(ref, item) == 1.0

    def test_exact_title_match(self):
        ref = _make_ref()
        item = {
            "title": ["Machine learning in healthcare"],
            "published": {"date-parts": [[2020]]},
        }
        conf = crossref_confidence(ref, item)
        assert conf > 0.95  # exact match + year bonus

    def test_similar_title(self):
        ref = _make_ref()
        item = {
            "title": ["Machine Learning in Healthcare: A Review"],
            "published": {"date-parts": [[2020]]},
        }
        conf = crossref_confidence(ref, item)
        assert conf > 0.7

    def test_completely_different_title(self):
        ref = _make_ref()
        item = {
            "title": ["Quantum computing and cryptography"],
            "published": {"date-parts": [[2022]]},
        }
        conf = crossref_confidence(ref, item)
        assert conf < 0.5

    def test_no_title_in_response(self):
        ref = _make_ref()
        item = {"title": [], "published": {"date-parts": [[2020]]}}
        assert crossref_confidence(ref, item) == 0.0


class TestSemanticScholarConfidence:
    def test_exact_title_match(self):
        ref = _make_ref()
        paper = {
            "title": "Machine learning in healthcare",
            "year": 2020,
            "externalIds": {},
        }
        conf = s2_confidence(ref, paper)
        assert conf > 0.95

    def test_doi_match(self):
        ref = _make_ref(doi="10.1038/test")
        paper = {
            "title": "Something else",
            "year": 2020,
            "externalIds": {"DOI": "10.1038/test"},
        }
        assert s2_confidence(ref, paper) == 1.0

    def test_no_title(self):
        ref = _make_ref()
        paper = {"title": "", "year": 2020, "externalIds": {}}
        assert s2_confidence(ref, paper) == 0.0


class TestModels:
    def test_verification_status_values(self):
        assert VerificationStatus.VERIFIED == "verified"
        assert VerificationStatus.NOT_FOUND == "not_found"
        assert VerificationStatus.AMBIGUOUS == "ambiguous"

    def test_reference_json_roundtrip(self):
        ref = _make_ref()
        data = ref.model_dump_json()
        restored = Reference.model_validate_json(data)
        assert restored.title == ref.title
        assert restored.authors == ref.authors
