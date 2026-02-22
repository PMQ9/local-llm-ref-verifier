# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"          # Install with dev dependencies
pytest                           # Run all tests
pytest tests/test_parsers.py     # Run a single test file
pytest -k test_apa_parser        # Run a single test by name
ref-verifier run paper.pdf -o output/ -m llama3.1   # Full pipeline
ref-verifier extract paper.pdf -o refs.json         # Stage 1 only
ref-verifier verify refs.json -o verified.json      # Stage 2 only
ref-verifier audit paper.pdf verified.json -o report.json -m llama3.1  # Stage 3 only
```

## Architecture

Privacy-preserving citation verification pipeline for unpublished manuscripts. The manuscript text never leaves the local machine.

**Three-stage pipeline** with strict data boundaries:

1. **Extract** (`reference_extractor.py`, `parsers/`) — Regex-based, no LLM, no internet. Parses PDF reference sections, auto-detects citation style (APA/IEEE/Vancouver/Harvard/Chicago), outputs `ExtractionResult`.

2. **Verify** (`verifier.py`, `sources/`) — Online, metadata only. Fallback chain: CrossRef → Semantic Scholar → Google Scholar. Sends only title/author/year/DOI externally. Returns confidence scores, canonical metadata, abstracts, and TLDR summaries. Outputs `VerificationResult`.

3. **Audit** (`auditor.py`, `prompts.py`) — Local LLM via Ollama. Compares manuscript body against verified references using abstracts/summaries to check claim correctness. Outputs `AuditReport`.

**Key design constraints:**
- Manuscript body text is only used in Stages 1 and 3 (both local). Stage 2 only receives reference metadata.
- `prompts.py` contains all LLM prompts as editable templates — modify these to tune audit behavior without touching code.
- All inter-stage data flows through Pydantic models in `models.py` and serializes to JSON.
- PDF extraction uses pdfplumber with PyMuPDF as fallback (`pdf_parser.py`).

## Testing

Tests use pytest with pytest-httpx for HTTP mocking. Test fixtures live in `tests/fixtures/` (sample PDF and reference JSON).

## After making changes

- Update `CHANGELOG.md` — very short and concise, no emojis.
- Update `README.md` — very short and concise, no emojis.
