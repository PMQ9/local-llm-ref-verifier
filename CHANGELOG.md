# Changelog

## Unreleased

### Added
- Cross-platform GUI (tkinter): `ref-verifier gui` launches a graphical interface with PDF browsing, Ollama model selection, progress tracking, extraction/verification/audit result tables, and clickable verification links
- Vancouver parser: support for Springer/LNCS author format (LastName, I., LastName, I.I.)
- Integration test suite with 13 real research papers across all 5 citation styles
- Real PDF samples for Harvard (2 RBA working papers) and Chicago (2 MDPI Humanities, 1 NBER)
- Harvard parser: custom split_references for line-wrapped author-date references
- Harvard parser: support for RBA-style author format (LastName FI without periods)
- Harvard parser: handle comma after (Year) and year-letter suffixes like (2009a)
- Chicago parser: Author-Date variant support alongside Notes-Bibliography
- Chicago parser: custom split_references for Author-Date formatted papers
- Fake-citation JSON fixtures for verifier testing (3 fake refs per paper)
- Pytest `slow` marker for live API tests
- IEEE parser: support for unquoted-title references (arXiv/NeurIPS/ICML style)
- Vancouver parser: support for colon-separated author format
- Vancouver parser: fix split regex to avoid splitting on year strings like "2020."

### Fixed
- Harvard/Chicago style detection: improved scoring to distinguish Author-Date formats
- Reference heading detection now handles leading dots from column extraction artifacts
- Unicode normalization: added em-dash, non-breaking space, ff/ffi/ffl ligatures
- Base parser split regex no longer treats years as reference numbers
