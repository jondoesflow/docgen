"""docgen command-line interface.

Commands: parse, render, diff, check, all. See docs/USAGE.md for the full
reference. Snapshot-first: parse produces a snapshot; every other command
consumes snapshots, never the source file directly.

Two input kinds are supported and the commands dispatch on them, so there is
one workflow to learn rather than two:

    docgen all MySolution.zip           → the solution document set
    docgen all Workshop.txt             → the meeting document set

`parse` writes `snapshot.json` for a solution and `transcript-snapshot.json`
for a transcript; `render` reads whichever kind it is given.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from docgen import __version__
from docgen.config import ConfigError, load_config
from docgen.constants import ALL_DOC_KEYS, ALL_FORMATS, ALL_TRANSCRIPT_DOC_KEYS

app = typer.Typer(
    name="docgen",
    help=(
        "Generate living design documentation for Dynamics 365 CE / Power Platform "
        "solutions from an exported solution zip, and consultancy documentation for "
        "workshops and meetings from a transcript.\n\n"
        "Typical use: docgen all solution.zip -o out/ --no-llm\n"
        "             docgen all workshop-transcript.txt -o out/ --no-llm"
    ),
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

ConfigOpt = typer.Option(None, "--config", "-c", help="Path to docgen.yaml (default: ./docgen.yaml if present).")
OutputOpt = typer.Option(None, "--output", "-o", help="Output folder (default: from config, 'out').")

SOLUTION_KIND = "solution"
TRANSCRIPT_KIND = "transcript"

model_app = typer.Typer(
    help=(
        "Choose the LLM provider/model and manage API keys. The active provider is a "
        "per-engagement decision: data goes to whichever provider is selected here."
    ),
    no_args_is_help=True,
)
app.add_typer(model_app, name="model")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"docgen {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
) -> None:
    """docgen — documentation regenerated from source material, so it never drifts."""


def _load_config_or_exit(config_path: Optional[Path]):
    try:
        return load_config(config_path)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)


def _resolve_output(output: Optional[Path], config) -> Path:
    return Path(output) if output is not None else Path(config.output_dir)


def _classify_source(source: Path) -> str:
    """Solution zip or meeting transcript? Decided by content, not just suffix."""
    import zipfile

    from docgen.transcripts import looks_like_transcript

    if not source.is_file():
        typer.secho(f"Input file not found: {source}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    if zipfile.is_zipfile(source):
        return SOLUTION_KIND
    if source.suffix.lower() == ".zip":
        typer.secho(f"Not a valid zip file: {source}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    if looks_like_transcript(source):
        return TRANSCRIPT_KIND
    typer.secho(
        f"Unrecognised input: {source}. Expected an exported solution zip, or a meeting "
        "transcript (.txt, .vtt, .md).",
        fg=typer.colors.RED, err=True,
    )
    raise typer.Exit(code=2)


def _snapshot_kind_or_exit(snapshot: Path) -> str:
    from docgen.snapshot.io import SnapshotVersionError, snapshot_kind

    if not snapshot.is_file():
        typer.secho(f"Snapshot not found: {snapshot}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    try:
        return snapshot_kind(snapshot)
    except SnapshotVersionError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)


def _parse_docs_option(docs: Optional[str], config, kind: str = SOLUTION_KIND) -> list[str]:
    valid = ALL_TRANSCRIPT_DOC_KEYS if kind == TRANSCRIPT_KIND else ALL_DOC_KEYS
    default = config.default_transcript_docs if kind == TRANSCRIPT_KIND else config.default_docs
    keys = [d.strip() for d in docs.split(",") if d.strip()] if docs else list(default)
    unknown = [k for k in keys if k not in valid]
    if unknown:
        typer.secho(
            f"Unknown {kind} document key(s): {', '.join(unknown)}. "
            f"Valid {kind} keys: {', '.join(valid)}",
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
    source: Path = typer.Argument(..., help="Exported solution zip, or a meeting transcript (.txt/.vtt/.md)."),
    output: Optional[Path] = OutputOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Parse a solution zip or a meeting transcript into a snapshot plus a warnings report."""
    cfg = _load_config_or_exit(config)
    kind = _classify_source(source)
    out_dir = _resolve_output(output, cfg)

    if kind == TRANSCRIPT_KIND:
        from docgen.commands import run_parse_transcript

        run_parse_transcript(source, out_dir, cfg)
        return

    from docgen.commands import run_parse

    run_parse(source, out_dir)


@app.command()
def render(
    snapshot: Path = typer.Argument(..., help="snapshot.json or transcript-snapshot.json from `docgen parse`."),
    docs: Optional[str] = typer.Option(
        None, "--docs",
        help=(f"Comma-separated document keys. Solution: {','.join(ALL_DOC_KEYS)}. "
              f"Transcript: {','.join(ALL_TRANSCRIPT_DOC_KEYS)}. Default: all for that kind."),
    ),
    format: Optional[str] = typer.Option(None, "--format", help="Comma-separated output formats: md,docx. Default: from config."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Fully offline: deterministic content only, placeholders for narrative."),
    check_learn: bool = typer.Option(False, "--check-learn", help="Verify deprecation-rule Microsoft Learn references are reachable (network; solution snapshots only)."),
    output: Optional[Path] = OutputOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Render documentation from a snapshot. The document set follows the snapshot kind."""
    cfg = _load_config_or_exit(config)
    kind = _snapshot_kind_or_exit(snapshot)
    doc_keys = _parse_docs_option(docs, cfg, kind)
    formats = _parse_formats_option(format, cfg)
    out_dir = _resolve_output(output, cfg)

    if kind == TRANSCRIPT_KIND:
        from docgen.commands import run_render_transcript

        run_render_transcript(snapshot, doc_keys, formats, out_dir, cfg, no_llm=no_llm)
        if check_learn:
            typer.secho("  --check-learn applies to solution snapshots only — skipped.",
                        fg=typer.colors.YELLOW)
        return

    from docgen.commands import run_learn_check, run_render

    run_render(snapshot, doc_keys, formats, out_dir, cfg, no_llm=no_llm)
    if check_learn:
        run_learn_check(out_dir, cfg)


@app.command()
def diff(
    old_snapshot: Path = typer.Argument(..., help="Older snapshot.json."),
    new_snapshot: Path = typer.Argument(..., help="Newer snapshot.json."),
    format: Optional[str] = typer.Option(None, "--format", help="Comma-separated output formats: md,docx."),
    output: Optional[Path] = OutputOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Compare two solution snapshots: release notes + changed-component report."""
    cfg = _load_config_or_exit(config)
    for p in (old_snapshot, new_snapshot):
        if _snapshot_kind_or_exit(p) != SOLUTION_KIND:
            typer.secho(f"{p} is a transcript snapshot; `docgen diff` compares solution snapshots.",
                        fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
    formats = _parse_formats_option(format, cfg)
    out_dir = _resolve_output(output, cfg)

    from docgen.commands import run_diff

    run_diff(old_snapshot, new_snapshot, formats, out_dir, cfg)


@app.command()
def check(
    snapshot: Path = typer.Argument(..., help="snapshot.json or transcript-snapshot.json."),
    output: Optional[Path] = OutputOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Run the hygiene checks only and write the hygiene report (fast).

    For a solution snapshot that is the build hygiene report; for a transcript
    snapshot it is the discovery hygiene report — is this good enough to design
    and estimate from?
    """
    cfg = _load_config_or_exit(config)
    kind = _snapshot_kind_or_exit(snapshot)
    out_dir = _resolve_output(output, cfg)

    if kind == TRANSCRIPT_KIND:
        from docgen.commands import run_check_transcript

        run_check_transcript(snapshot, out_dir, cfg)
        return

    from docgen.commands import run_check

    run_check(snapshot, out_dir, cfg)


@app.command("all")
def all_cmd(
    source: Path = typer.Argument(..., help="Exported solution zip, or a meeting transcript (.txt/.vtt/.md)."),
    docs: Optional[str] = typer.Option(None, "--docs", help="Comma-separated document keys. Default: all for the input kind."),
    format: Optional[str] = typer.Option(None, "--format", help="Comma-separated output formats: md,docx."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Fully offline: deterministic content only, placeholders for narrative."),
    check_learn: bool = typer.Option(False, "--check-learn", help="Verify deprecation-rule Microsoft Learn references are reachable (network; solutions only)."),
    output: Optional[Path] = OutputOpt,
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Parse + render everything in one step (solutions also get the hygiene check)."""
    cfg = _load_config_or_exit(config)
    kind = _classify_source(source)
    doc_keys = _parse_docs_option(docs, cfg, kind)
    formats = _parse_formats_option(format, cfg)
    out_dir = _resolve_output(output, cfg)

    if kind == TRANSCRIPT_KIND:
        from docgen.commands import run_all_transcript

        run_all_transcript(source, doc_keys, formats, out_dir, cfg, no_llm=no_llm)
        if check_learn:
            typer.secho("  --check-learn applies to solutions only — skipped.", fg=typer.colors.YELLOW)
        return

    from docgen.commands import run_all

    run_all(source, doc_keys, formats, out_dir, cfg, no_llm=no_llm, check_learn=check_learn)


@model_app.command("list")
def model_list(config: Optional[Path] = ConfigOpt) -> None:
    """Supported providers with example model strings; the active one is marked."""
    cfg = _load_config_or_exit(config)

    from docgen.modelcmd import run_model_list

    run_model_list(cfg)


@model_app.command("use")
def model_use(
    selection: str = typer.Argument(..., help="provider/model, e.g. anthropic/claude-sonnet-4-6 or deepseek/deepseek-chat."),
    config: Optional[Path] = ConfigOpt,
) -> None:
    """Set the active provider/model, persisted in docgen.yaml (comments preserved)."""
    from docgen.modelcmd import run_model_use

    run_model_use(selection, config)


@model_app.command("key")
def model_key(
    provider: str = typer.Argument(..., help="Provider to store an API key for (see `docgen model list`)."),
) -> None:
    """Store an API key via a hidden prompt: OS keyring, or a git-ignored .env fallback."""
    from docgen.modelcmd import run_model_key

    run_model_key(provider)


@model_app.command("status")
def model_status(config: Optional[Path] = ConfigOpt) -> None:
    """Active provider/model and where its API key resolves from (masked)."""
    cfg = _load_config_or_exit(config)

    from docgen.modelcmd import run_model_status

    run_model_status(cfg)


if __name__ == "__main__":
    app()
