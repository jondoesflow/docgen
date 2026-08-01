"""Command implementations behind the CLI. Milestone stubs are replaced as parsers
and renderers land; keeping them here keeps cli.py purely about argument handling."""

from __future__ import annotations

from pathlib import Path

import typer

from docgen.config import DocgenConfig


def run_parse(solution_zip: Path, out_dir: Path) -> Path:
    """Parse the zip, write snapshot.json + parse-warnings.md, return snapshot path."""
    from docgen.parsers import parse_solution
    from docgen.snapshot.io import save_snapshot

    snapshot = parse_solution(solution_zip)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = out_dir / "snapshot.json"
    save_snapshot(snapshot, snapshot_path)
    warnings_path = out_dir / "parse-warnings.md"
    warnings_path.write_text(warnings_markdown(snapshot), encoding="utf-8", newline="\n")

    s = snapshot
    typer.echo(
        f"Parsed {s.solution.unique_name or solution_zip.name} v{s.solution.version} "
        f"({'managed' if s.solution.managed else 'unmanaged'})"
    )
    typer.echo(
        f"  entities: {len(s.entities)}  option sets: {len(s.global_option_sets)}  "
        f"roles: {len(s.security_roles)}  flows: {len(s.cloud_flows)}  "
        f"other components: {len(s.other_components)}"
    )
    typer.echo(f"  snapshot: {snapshot_path}")
    if s.warnings:
        typer.secho(f"  {len(s.warnings)} parse warning(s) — see {warnings_path}", fg=typer.colors.YELLOW)
    else:
        typer.echo("  no parse warnings")
    return snapshot_path


def warnings_markdown(snapshot) -> str:
    lines = [f"# Parse warnings — {snapshot.solution.unique_name} v{snapshot.solution.version}", ""]
    if not snapshot.warnings:
        lines += ["No parse warnings. Every component in the solution was recognised.", ""]
        return "\n".join(lines)
    lines += [
        f"{len(snapshot.warnings)} warning(s). Components listed here were captured as generic "
        "inventory entries where possible; nothing was silently dropped.",
        "",
    ]
    by_code: dict[str, list] = {}
    for w in snapshot.warnings:
        by_code.setdefault(w.code, []).append(w)
    for code in sorted(by_code):
        lines.append(f"## {code} ({len(by_code[code])})")
        lines.append("")
        for w in by_code[code]:
            location = f"`{w.context}` — " if w.context else ""
            lines.append(f"- {location}{w.message}")
        lines.append("")
    return "\n".join(lines)


def run_render(
    snapshot_path: Path,
    doc_keys: list[str],
    formats: list[str],
    out_dir: Path,
    cfg: DocgenConfig,
    *,
    no_llm: bool,
) -> None:
    typer.secho("`docgen render` is not implemented yet (milestone 3).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)


def run_diff(old_path: Path, new_path: Path, formats: list[str], out_dir: Path, cfg: DocgenConfig) -> None:
    typer.secho("`docgen diff` is not implemented yet (milestone 5).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)


def run_check(snapshot_path: Path, out_dir: Path, cfg: DocgenConfig) -> None:
    typer.secho("`docgen check` is not implemented yet (milestone 4).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)


def run_all(
    solution_zip: Path,
    doc_keys: list[str],
    formats: list[str],
    out_dir: Path,
    cfg: DocgenConfig,
    *,
    no_llm: bool,
) -> None:
    typer.secho("`docgen all` is not implemented yet (milestone 6).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)
