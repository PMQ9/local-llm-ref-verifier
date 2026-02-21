"""Tests for the PDF parser module."""

from ref_verifier.pdf_parser import split_reference_section


class TestSplitReferenceSection:
    def test_standard_references_heading(self):
        text = "This is the body.\n\nReferences\n\nSmith (2020). A paper."
        body, refs = split_reference_section(text)
        assert "This is the body." in body
        assert "Smith (2020)" in refs
        assert "References" not in refs

    def test_bibliography_heading(self):
        text = "Body text here.\n\nBibliography\n\n[1] Jones (2019)."
        body, refs = split_reference_section(text)
        assert "Body text" in body
        assert "Jones (2019)" in refs

    def test_works_cited_heading(self):
        text = "Some content.\n\nWorks Cited\n\nAuthor (2021)."
        body, refs = split_reference_section(text)
        assert "Some content" in body
        assert "Author (2021)" in refs

    def test_no_reference_heading(self):
        text = "Just a body of text with no reference section."
        body, refs = split_reference_section(text)
        assert body == text
        assert refs == ""

    def test_multiple_references_headings_uses_last(self):
        text = (
            "Table of Contents\nReferences...page 10\n\n"
            "Body text.\n\n"
            "References\n\nActual ref 1.\nActual ref 2."
        )
        body, refs = split_reference_section(text)
        assert "Actual ref 1" in refs
        assert "Table of Contents" in body

    def test_case_insensitive(self):
        text = "Body.\n\nREFERENCES\n\nRef here."
        body, refs = split_reference_section(text)
        assert "Ref here" in refs
