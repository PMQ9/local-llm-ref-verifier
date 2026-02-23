# Changelog

## Unreleased

### Added
- Integration test suite with 8 real research papers (3 IEEE, 3 Vancouver, 2 APA)
- Fake-citation JSON fixtures for verifier testing (3 fake refs per paper)
- Pytest `slow` marker for live API tests
- IEEE parser: support for unquoted-title references (arXiv/NeurIPS/ICML style)
- Vancouver parser: support for colon-separated author format
- Vancouver parser: fix split regex to avoid splitting on year strings like "2020."

### Fixed
- Reference heading detection now handles leading dots from column extraction artifacts
- Unicode normalization: added em-dash, non-breaking space, ff/ffi/ffl ligatures
- Base parser split regex no longer treats years as reference numbers
