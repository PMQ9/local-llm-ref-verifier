"""Integration tests using real research papers.

Tests validate PDF extraction, style detection, and reference parsing against
real papers. Fake-citation JSON files test that injected citations can be
distinguished from real ones during verification.
"""

from pathlib import Path

import pytest

from ref_verifier.models import (
    ExtractionResult,
    Reference,
    VerificationStatus,
)
from ref_verifier.parsers import detect_style
from ref_verifier.pdf_parser import parse_pdf
from ref_verifier.reference_extractor import extract_from_pdf

FIXTURES = Path(__file__).parent / "fixtures"
PAPERS = FIXTURES / "papers"
EXPECTED = FIXTURES / "expected"

# (style, filename_stem, min_refs, layout)
PAPER_CASES = [
    ("ieee", "attention_is_all_you_need", 20, "two-column"),
    ("ieee", "deep_residual_learning", 20, "two-column"),
    ("ieee", "yolo", 10, "two-column"),
    ("vancouver", "covid_bibliometric", 15, "two-column"),
    ("vancouver", "covid_cardiovascular", 10, "two-column"),
    ("vancouver", "covid_open_access", 8, "single-column"),
    ("apa", "frontiers_discrimination_anxiety", 10, "single-column"),
    ("apa", "frontiers_scholarly_reading", 10, "single-column"),
    ("harvard", "rba_monetary_policy", 40, "single-column"),
    ("harvard", "rba_financial_conditions", 30, "single-column"),
    ("chicago", "mdpi_humanities_toy_tourism", 15, "single-column"),
    ("chicago", "mdpi_humanities_hui_identity", 10, "single-column"),
    ("chicago", "nber_labor_force", 10, "single-column"),
]

# Papers where auto-detect correctly identifies the style
DETECT_CORRECT = [
    ("ieee", "deep_residual_learning"),
    ("ieee", "yolo"),
    ("vancouver", "covid_bibliometric"),
    ("vancouver", "covid_cardiovascular"),
    ("vancouver", "covid_open_access"),
    ("apa", "frontiers_discrimination_anxiety"),
    ("apa", "frontiers_scholarly_reading"),
    ("harvard", "rba_monetary_policy"),
    ("harvard", "rba_financial_conditions"),
    ("chicago", "mdpi_humanities_toy_tourism"),
    ("chicago", "mdpi_humanities_hui_identity"),
    ("chicago", "nber_labor_force"),
]


def _pdf_path(style: str, name: str) -> Path:
    return PAPERS / style / f"{name}.pdf"


def _expected_path(style: str, name: str) -> Path:
    return EXPECTED / style / f"{name}.json"


def _fake_path(style: str, name: str) -> Path:
    return EXPECTED / style / f"{name}_fake.json"


def _skip_if_missing(path: Path):
    if not path.exists():
        pytest.skip(f"Fixture not found: {path.name}")


# ---------------------------------------------------------------------------
# PDF extraction tests
# ---------------------------------------------------------------------------


class TestPDFExtraction:
    """Test that real PDFs parse and have reference sections."""

    @pytest.mark.parametrize("style,name,min_refs,layout", PAPER_CASES)
    def test_pdf_parses_without_error(self, style, name, min_refs, layout):
        pdf = _pdf_path(style, name)
        _skip_if_missing(pdf)
        parsed = parse_pdf(pdf)
        assert len(parsed.full_text) > 1000

    @pytest.mark.parametrize("style,name,min_refs,layout", PAPER_CASES)
    def test_reference_section_found(self, style, name, min_refs, layout):
        pdf = _pdf_path(style, name)
        _skip_if_missing(pdf)
        parsed = parse_pdf(pdf)
        assert parsed.reference_section, f"No reference section found in {name}"


# ---------------------------------------------------------------------------
# Style detection tests
# ---------------------------------------------------------------------------


class TestStyleDetection:
    """Test citation style auto-detection on real papers."""

    @pytest.mark.parametrize("style,name", DETECT_CORRECT)
    def test_style_detected_correctly(self, style, name):
        pdf = _pdf_path(style, name)
        _skip_if_missing(pdf)
        parsed = parse_pdf(pdf)
        detected = detect_style(parsed.reference_section)
        assert detected == style, f"Expected {style}, got {detected}"


# ---------------------------------------------------------------------------
# Reference extraction tests
# ---------------------------------------------------------------------------


class TestReferenceExtraction:
    """Test that references are extracted with required fields."""

    @pytest.mark.parametrize("style,name,min_refs,layout", PAPER_CASES)
    def test_extracts_minimum_references(self, style, name, min_refs, layout):
        pdf = _pdf_path(style, name)
        _skip_if_missing(pdf)
        result = extract_from_pdf(pdf, style=style)
        assert len(result.references) >= min_refs, (
            f"Expected >= {min_refs} refs, got {len(result.references)}"
        )

    @pytest.mark.parametrize("style,name,min_refs,layout", PAPER_CASES)
    def test_references_have_title(self, style, name, min_refs, layout):
        pdf = _pdf_path(style, name)
        _skip_if_missing(pdf)
        result = extract_from_pdf(pdf, style=style)
        titled = [r for r in result.references if r.title]
        assert len(titled) >= len(result.references) * 0.5, (
            f"Only {len(titled)}/{len(result.references)} refs have titles"
        )

    @pytest.mark.parametrize("style,name,min_refs,layout", PAPER_CASES)
    def test_references_have_year(self, style, name, min_refs, layout):
        pdf = _pdf_path(style, name)
        _skip_if_missing(pdf)
        result = extract_from_pdf(pdf, style=style)
        with_year = [r for r in result.references if r.year]
        assert len(with_year) >= len(result.references) * 0.5, (
            f"Only {len(with_year)}/{len(result.references)} refs have years"
        )

    @pytest.mark.parametrize("style,name,min_refs,layout", PAPER_CASES)
    def test_extraction_matches_expected_count(self, style, name, min_refs, layout):
        """Extraction count matches saved expected output."""
        pdf = _pdf_path(style, name)
        expected_json = _expected_path(style, name)
        _skip_if_missing(pdf)
        _skip_if_missing(expected_json)

        result = extract_from_pdf(pdf, style=style)
        expected = ExtractionResult.model_validate_json(expected_json.read_text())
        assert len(result.references) == len(expected.references), (
            f"Ref count mismatch: {len(result.references)} vs "
            f"{len(expected.references)} expected"
        )


# ---------------------------------------------------------------------------
# Fake citation JSON tests
# ---------------------------------------------------------------------------


class TestFakeCitationDetection:
    """Test that fake citations in JSON files are structurally correct."""

    @pytest.mark.parametrize("style,name,min_refs,layout", PAPER_CASES)
    def test_fake_json_has_extra_refs(self, style, name, min_refs, layout):
        real_json = _expected_path(style, name)
        fake_json = _fake_path(style, name)
        _skip_if_missing(real_json)
        _skip_if_missing(fake_json)

        real = ExtractionResult.model_validate_json(real_json.read_text())
        fake = ExtractionResult.model_validate_json(fake_json.read_text())
        assert len(fake.references) == len(real.references) + 3

    @pytest.mark.parametrize("style,name,min_refs,layout", PAPER_CASES)
    def test_fake_refs_have_distinctive_content(self, style, name, min_refs, layout):
        real_json = _expected_path(style, name)
        fake_json = _fake_path(style, name)
        _skip_if_missing(real_json)
        _skip_if_missing(fake_json)

        real = ExtractionResult.model_validate_json(real_json.read_text())
        fake = ExtractionResult.model_validate_json(fake_json.read_text())

        fake_only = fake.references[len(real.references) :]
        titles = [r.title for r in fake_only]
        assert any("Does Not Exist" in t for t in titles)
        assert any("Hierarchical Attention" in t for t in titles)
        assert any("Bayesian Optimization" in t for t in titles)

    def test_fake_ref_has_invalid_doi(self):
        for style_dir in sorted(EXPECTED.iterdir()):
            if not style_dir.is_dir():
                continue
            for fake_json in sorted(style_dir.glob("*_fake.json")):
                result = ExtractionResult.model_validate_json(fake_json.read_text())
                fake_dois = [
                    r.doi for r in result.references if r.doi and "fake" in r.doi
                ]
                if fake_dois:
                    assert "10.9999/fake-doi-12345" in fake_dois
                    return
        pytest.skip("No fake JSON with DOI found")

    def test_fake_ref_has_future_year(self):
        for style_dir in sorted(EXPECTED.iterdir()):
            if not style_dir.is_dir():
                continue
            for fake_json in sorted(style_dir.glob("*_fake.json")):
                result = ExtractionResult.model_validate_json(fake_json.read_text())
                future_refs = [r for r in result.references if r.year == 2099]
                if future_refs:
                    return
        pytest.fail("No fake ref with year 2099 found")


# ---------------------------------------------------------------------------
# Mocked verification tests
# ---------------------------------------------------------------------------


class TestVerificationMocked:
    """Test verification with mocked HTTP responses."""

    @pytest.mark.httpx_mock(can_send_already_matched_responses=True)
    def test_real_ref_verifies_with_crossref_match(self, httpx_mock):
        """A real reference should be verified when CrossRef returns a match."""
        ref = Reference(
            id="ref_01",
            authors=["Guan WJ", "Ni ZY", "Hu Y"],
            title="Clinical characteristics of coronavirus disease 2019 in China",
            year=2020,
            journal="N Engl J Med",
            volume="382",
            pages="1708-1720",
            raw_text="1. Guan WJ, et al. Clinical characteristics. N Engl J Med. 2020;382:1708-1720.",
        )

        httpx_mock.add_response(
            json={
                "message": {
                    "items": [
                        {
                            "title": [
                                "Clinical Characteristics of Coronavirus Disease 2019 in China"
                            ],
                            "DOI": "10.1056/NEJMoa2002032",
                            "published": {"date-parts": [[2020]]},
                            "author": [
                                {"given": "Wei-jie", "family": "Guan"},
                            ],
                        }
                    ]
                }
            },
        )

        from ref_verifier.verifier import verify_single_reference

        result = verify_single_reference(ref)
        assert result.status == VerificationStatus.VERIFIED
        assert result.confidence >= 0.8

    @pytest.mark.httpx_mock(can_send_already_matched_responses=True)
    def test_fake_ref_not_found(self, httpx_mock):
        """A fake reference should be not_found when APIs return no match."""
        ref = Reference(
            id="ref_fake",
            authors=["Petrov, I. V.", "Chen, L."],
            title="This Paper Does Not Exist In Any Database Anywhere",
            year=2099,
            journal="Fictitious Review of Imaginary Science",
            raw_text="Petrov, I. V., & Chen, L. (2099). This Paper Does Not Exist.",
        )

        httpx_mock.add_response(json={"message": {"items": []}})
        httpx_mock.add_response(json={"data": []})

        from ref_verifier.verifier import verify_single_reference

        result = verify_single_reference(ref)
        assert result.status == VerificationStatus.NOT_FOUND
        assert result.confidence < 0.8


# ---------------------------------------------------------------------------
# Live API tests (slow, optional)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestLiveVerification:
    """Tests that hit real CrossRef/S2 APIs. Run with: pytest -m slow"""

    def test_real_refs_verify_live(self):
        """A few real references from the bibliometric paper should verify."""
        expected_json = _expected_path("vancouver", "covid_bibliometric")
        _skip_if_missing(expected_json)

        extraction = ExtractionResult.model_validate_json(expected_json.read_text())
        extraction.references = extraction.references[:3]

        from ref_verifier.verifier import verify_references

        result = verify_references(extraction)
        verified_count = sum(
            1 for v in result.references if v.status == VerificationStatus.VERIFIED
        )
        assert verified_count >= 2, (
            f"Expected at least 2/3 verified, got {verified_count}"
        )

    def test_fake_refs_fail_live(self):
        """Fake references should not verify against live APIs."""
        fake_json = _fake_path("vancouver", "covid_bibliometric")
        _skip_if_missing(fake_json)

        result = ExtractionResult.model_validate_json(fake_json.read_text())
        fake_refs = result.references[-3:]
        result.references = fake_refs

        from ref_verifier.verifier import verify_references

        vresult = verify_references(result)
        for v in vresult.references:
            assert v.status != VerificationStatus.VERIFIED, (
                f"Fake ref '{v.ref_id}' should not verify"
            )
