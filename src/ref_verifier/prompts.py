"""LLM prompts for the citation audit pipeline.

Edit these prompts to tune the audit behavior without touching code.
These are used by auditor.py with a local Ollama model.
"""

# --- Stage 3: Citation Audit ---

AUDIT_SYSTEM_PROMPT = """\
You are a citation audit assistant. Your job is to analyze a research \
manuscript's body text and compare it against a list of verified references. \
Identify any citation issues with precision."""

AUDIT_PROMPT_TEMPLATE = """\
Analyze the manuscript text below and compare it against the verified \
reference list. Identify the following issues:

1. **Uncited references**: References in the list that are never cited in the body text.
2. **Missing from list**: In-text citations (e.g., "Smith et al., 2020" or "[1]") \
that do not match any reference in the list.
3. **Misquoted claims**: Claims attributed to a reference that seem inconsistent \
with the reference's title/topic (based on the verified metadata).
4. **Year mismatches**: In-text citation years that don't match the reference's \
verified year.

For each issue, provide:
- issue_type: one of "uncited_reference", "missing_from_list", "misquoted_claim", "year_mismatch"
- severity: "error" for definite problems, "warning" for likely problems, "info" for minor notes
- ref_id: the reference ID if applicable (null otherwise)
- description: clear explanation of the issue
- manuscript_excerpt: the relevant quote from the manuscript (if applicable)

Also provide a summary paragraph and counts.

VERIFIED REFERENCES:
{references_json}

MANUSCRIPT TEXT:
{body_text}"""
