"""docgen command-line interface.

Commands: parse, render, diff, check, all. See docs/USAGE.md for the full
reference. Snapshot-first: parse produces snapshot.json; every other command
consumes snapshots, never the zip directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from docgen import __version__
from docgen.config import ConfigError, load_config
from docgen.constants import ALL_DOC_KEYS, ALL_FORMATS

app = typer.Typer(
    name="docgen",
    help=(
        "Generate living design documentation for Dynamics 365 CE / Power Platform "
        "solutions from an exported solution zip.\n\n"
        "Typical use: docgen all solution.zip -o out/ --no-llm"
    ),
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

ConfigOpt = typer.Option(None, "--config", "-c", help="Path to docgen.yaml (default: ./docgen.yaml if present).")
OutputOpt = typer.Option(None, "--output", "-o", help="Output folder (default: from config, 'out').")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"docgen {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
) -> None:
    """docgen — documentation that is regenerated from solution metadata, so it never drifts."""


def _load_config_or_exit(config_path: Optional[Path]):
    try:
        return load_config(config_path)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)


def _resolve_output(output: Optional[Path], config) -> Path:
    return Path(output) if output is not None else Path(config.output_dir)


def _check_zip(solution_zip: Path) -> None:
    import zipfile

    if not solution_zip.is_file():
        typer.secho(f"Solution zip not found: {solution_zip}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    if not zipfile.is_zipfile(solution_zip):
        typer.secho(f"Not a valid zip file: {solution_zip}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)


def _parse_docs_option(docs: Optional[str], config) -> list[str]:
    keys = [d.strip() for d in docs.split(",") if d.strip()] if docs else list(config.default_docs)
    unknown = [k for k in keys if k not in ALL_DOC_KEYS]
    if unknown:
        typer.secho(
            f"Unknown document key(s): {', '.join(unknown)}. Valid keys: {', '.join(ALL_DOC_KEYS)}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    return keys


def _parse_formats_option(formats: Optional[str], config) -> list[str]:
    fmts = [f.strip() for f in formats.split(",") if f.strip()] if formats else list(config.formats)
    unknown = [f for f in fmts if f not in ALL_FORMATS]
    if unknown:
        typer.secho(
            f"Unknown format(s): {', '.join(unknown)}. Valid formats: {', '.join(ALL_FORMATS)}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)
    return fmts


@app.command()
def parse(
    solution_zip: Path = typer.Argument(..., help="Exported solution zip file."),
    output: Optional[Path] = OutputOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Parse a solution zip into snapshot.json plus a parse-warnings report."""
    cfg = _load_config_or_exit(config)
    _check_zip(solution_zip)
    out_dir = _resolve_output(output, cfg)

    from docgen.commands import run_parse

    run_parse(solution_zip, out_dir)


@app.command()
def render(
    snapshot: Path = typer.Argument(..., help="Path to snapshot.json produced by `docgen parse`."),
    docs: Optional[str] = typer.Option(None, "--docs", help=f"Comma-separated document keys ({','.join(ALL_DOC_KEYS)}). Default: all."),
    format: Optional[str] = typer.Option(None, "--format", help="Comma-separated output formats: md,docx. Default: from config."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Fully offline: deterministic content only, placeholders for narrative."),
    output: Optional[Path] = OutputOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Render documentation from a snapshot."""
    cfg = _load_config_or_exit(config)
    if not snapshot.is_file():
        typer.secho(f"Snapshot not found: {snapshot}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    doc_keys = _parse_docs_option(docs, cfg)
    formats = _parse_formats_option(format, cfg)
    out_dir = _resolve_output(output, cfg)

    from docgen.commands import run_render

    run_render(snapshot, doc_keys, formats, out_dir, cfg, no_llm=no_llm)


@app.command()
def diff(
    old_snapshot: Path = typer.Argument(..., help="Older snapshot.json."),
    new_snapshot: Path = typer.Argument(..., help="Newer snapshot.json."),
    format: Optional[str] = typer.Option(None, "--format", help="Comma-separated output formats: md,docx."),
    output: Optional[Path] = OutputOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Compare two snapshots: release notes + changed-component report."""
    cfg = _load_config_or_exit(config)
    for p in (old_snapshot, new_snapshot):
        if not p.is_file():
            typer.secho(f"Snapshot not found: {p}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
    formats = _parse_formats_option(format, cfg)
    out_dir = _resolve_output(output, cfg)

    from docgen.commands import run_diff

    run_diff(old_snapshot, new_snapshot, formats, out_dir, cfg)


@app.command()
def check(
    snapshot: Path = typer.Argument(..., help="Path to snapshot.json."),
    output: Optional[Path] = OutputOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Run the hygiene checks only and write the hygiene report (fast)."""
    cfg = _load_config_or_exit(config)
    if not snapshot.is_file():
        typer.secho(f"Snapshot not found: {snapshot}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    out_dir = _resolve_output(output, cfg)

    from docgen.commands import run_check

    run_check(snapshot, out_dir, cfg)


@app.command("all")
def all_cmd(
    solution_zip: Path = typer.Argument(..., help="Exported solution zip file."),
    docs: Optional[str] = typer.Option(None, "--docs", help="Comma-separated document keys. Default: all."),
    format: Optional[str] = typer.Option(None, "--format", help="Comma-separated output formats: md,docx."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Fully offline: deterministic content only, placeholders for narrative."),
    output: Optional[Path] = OutputOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Parse + check + render everything in one step."""
    cfg = _load_config_or_exit(config)
    _check_zip(solution_zip)
    doc_keys = _parse_docs_option(docs, cfg)
    formats = _parse_formats_option(format, cfg)
    out_dir = _resolve_output(output, cfg)

    from docgen.commands import run_all

    run_all(solution_zip, doc_keys, formats, out_dir, cfg, no_llm=no_llm)


if __name__ == "__main__":
    app()
