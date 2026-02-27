"""CLI entry point for the reference verifier pipeline.

Commands:
  ref-verifier extract <pdf>           Stage 1: Extract references (regex, no LLM)
  ref-verifier verify <json>           Stage 2: Verify references online
  ref-verifier audit <pdf> <json>      Stage 3: Audit citations (local LLM)
  ref-verifier run <pdf>               Run all 3 stages
"""

import logging
import sys
from pathlib import Path

import click

from .models import ExtractionResult, VerificationResult
from .parsers import PARSERS

STYLE_CHOICES = list(PARSERS.keys())


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


@click.group()
@click.version_option(package_name="local-llm-ref-verifier")
def main():
    """Privacy-preserving citation verification for unpublished manuscripts."""
    pass


@main.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None)
@click.option(
    "-s", "--style",
    type=click.Choice(STYLE_CHOICES, case_sensitive=False),
    default=None,
    help="Force citation style (auto-detected if omitted)",
)
@click.option("-v", "--verbose", is_flag=True)
def extract(pdf_path: Path, output: Path | None, style: str | None, verbose: bool):
    """Stage 1: Extract references from a PDF manuscript (no LLM needed)."""
    _setup_logging(verbose)

    from .reference_extractor import extract_from_pdf

    result = extract_from_pdf(pdf_path, style=style)

    output = output or Path(f"{pdf_path.stem}_references.json")
    output.write_text(result.model_dump_json(indent=2))
    click.echo(f"Detected style: {result.model_used}")
    click.echo(f"Extracted {len(result.references)} references -> {output}")


@main.command()
@click.argument("json_path", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None)
@click.option("--google-scholar", is_flag=True, help="Enable Google Scholar (slow, rate-limited)")
@click.option("-v", "--verbose", is_flag=True)
def verify(json_path: Path, output: Path | None, google_scholar: bool, verbose: bool):
    """Stage 2: Verify extracted references against online sources."""
    _setup_logging(verbose)

    from .verifier import verify_references

    extraction = ExtractionResult.model_validate_json(json_path.read_text())
    result = verify_references(extraction, use_google_scholar=google_scholar)

    output = output or Path(f"{json_path.stem}_verified.json")
    output.write_text(result.model_dump_json(indent=2))

    click.echo(f"Verification complete -> {output}")
    click.echo(f"  Verified: {result.stats.get('verified', 0)}")
    click.echo(f"  Ambiguous: {result.stats.get('ambiguous', 0)}")
    click.echo(f"  Not found: {result.stats.get('not_found', 0)}")


@main.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.argument("verified_json", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None)
@click.option("-m", "--model", default="llama3.1", help="Ollama model name")
@click.option("-v", "--verbose", is_flag=True)
def audit(
    pdf_path: Path,
    verified_json: Path,
    output: Path | None,
    model: str,
    verbose: bool,
):
    """Stage 3: Audit manuscript citations against verified references."""
    _setup_logging(verbose)

    from .auditor import audit_manuscript
    from .ollama_client import OllamaClient
    from .pdf_parser import parse_pdf

    client = OllamaClient(model=model)
    parsed = parse_pdf(pdf_path)
    verification = VerificationResult.model_validate_json(verified_json.read_text())

    report = audit_manuscript(parsed.body_text, verification, client)

    output = output or Path(f"{pdf_path.stem}_audit.json")
    output.write_text(report.model_dump_json(indent=2))

    click.echo(f"Audit complete -> {output}")
    click.echo(f"\n{report.summary}")
    click.echo(f"\nIssues found: {report.issues_found}")
    for issue in report.issues:
        icon = {"error": "X", "warning": "!", "info": "i"}[issue.severity.value]
        click.echo(f"  [{icon}] {issue.description}")


@main.command()
def gui():
    """Launch the graphical user interface."""
    from .gui import launch_gui

    launch_gui()


@main.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output-dir", type=click.Path(path_type=Path), default=Path("output"))
@click.option("-m", "--model", default="llama3.1", help="Ollama model name (for Stage 3 audit)")
@click.option(
    "-s", "--style",
    type=click.Choice(STYLE_CHOICES, case_sensitive=False),
    default=None,
    help="Force citation style (auto-detected if omitted)",
)
@click.option("--google-scholar", is_flag=True, help="Enable Google Scholar (slow, rate-limited)")
@click.option("-v", "--verbose", is_flag=True)
def run(
    pdf_path: Path,
    output_dir: Path,
    model: str,
    style: str | None,
    google_scholar: bool,
    verbose: bool,
):
    """Run the full pipeline: extract -> verify -> audit."""
    _setup_logging(verbose)

    from .auditor import audit_manuscript
    from .ollama_client import OllamaClient
    from .pdf_parser import parse_pdf
    from .reference_extractor import extract_from_pdf
    from .verifier import verify_references

    output_dir.mkdir(parents=True, exist_ok=True)

    # Stage 1: Extract (rule-based, no LLM)
    click.echo("Stage 1: Extracting references (regex)...")
    extraction = extract_from_pdf(pdf_path, style=style)
    ext_path = output_dir / "extracted_references.json"
    ext_path.write_text(extraction.model_dump_json(indent=2))
    click.echo(f"  Style: {extraction.model_used}")
    click.echo(f"  Extracted {len(extraction.references)} references -> {ext_path}")

    # Stage 2: Verify (online APIs)
    click.echo("Stage 2: Verifying references online...")
    verification = verify_references(extraction, use_google_scholar=google_scholar)
    ver_path = output_dir / "verification_results.json"
    ver_path.write_text(verification.model_dump_json(indent=2))
    click.echo(f"  Verified: {verification.stats.get('verified', 0)}")
    click.echo(f"  Ambiguous: {verification.stats.get('ambiguous', 0)}")
    click.echo(f"  Not found: {verification.stats.get('not_found', 0)}")

    # Stage 3: Audit (local LLM)
    click.echo("Stage 3: Auditing citations (local LLM)...")
    client = OllamaClient(model=model)
    parsed = parse_pdf(pdf_path)
    report = audit_manuscript(parsed.body_text, verification, client)
    audit_path = output_dir / "audit_report.json"
    audit_path.write_text(report.model_dump_json(indent=2))

    click.echo(f"\n{'=' * 60}")
    click.echo("AUDIT REPORT")
    click.echo(f"{'=' * 60}")
    click.echo(report.summary)
    click.echo(f"\nIssues found: {report.issues_found}")
    for issue in report.issues:
        icon = {"error": "X", "warning": "!", "info": "i"}[issue.severity.value]
        click.echo(f"  [{icon}] {issue.description}")
    click.echo(f"\nAll outputs saved to {output_dir}/")
