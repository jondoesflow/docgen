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
        typer.secho(f"  {len(s.warnings)} parse warning(s) - see {warnings_path}", fg=typer.colors.YELLOW)
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
) -> list[Path]:
    from docgen.renderers import get_renderer
    from docgen.snapshot.io import load_snapshot

    snapshot = load_snapshot(snapshot_path)
    return render_documents(snapshot, doc_keys, formats, out_dir, cfg, no_llm=no_llm)


def render_documents(
    snapshot,
    doc_keys: list[str],
    formats: list[str],
    out_dir: Path,
    cfg: DocgenConfig,
    *,
    no_llm: bool,
) -> list[Path]:
    from docgen.renderers import get_renderer
    from docgen.renderers.base import RenderContext, offline_narrative
    from docgen.renderers.diagrams import DiagramService
    from docgen.renderers.docx import write_docx
    from docgen.renderers.markdown import write_markdown
    from docgen.rules_io import load_rules

    out_dir.mkdir(parents=True, exist_ok=True)
    diagrams = DiagramService(out_dir)
    narrative = offline_narrative
    if not no_llm and cfg.llm.enabled:
        from docgen.llm import make_narrative_provider

        narrative = make_narrative_provider(snapshot, cfg, out_dir)
    ctx = RenderContext(config=cfg, out_dir=out_dir, narrative_provider=narrative, rules=load_rules(cfg))

    written: list[Path] = []
    for key in doc_keys:
        renderer = get_renderer(key)
        if renderer is None:
            typer.secho(f"  {key}: renderer not implemented yet — skipped", fg=typer.colors.YELLOW)
            continue
        if not renderer.applies(snapshot):
            typer.echo(f"  {key}: not applicable to this solution — skipped")
            continue
        document = renderer.build(snapshot, ctx)
        for fmt in formats:
            if fmt == "md":
                written.append(write_markdown(document, out_dir / f"{key}.md"))
            elif fmt == "docx":
                written.append(write_docx(document, out_dir / f"{key}.docx", diagrams,
                                          template_path=cfg.docx_template))
        typer.echo(f"  {key}: {renderer.title} -> {', '.join(formats)}")
    return written


def run_diff(old_path: Path, new_path: Path, formats: list[str], out_dir: Path, cfg: DocgenConfig) -> None:
    typer.secho("`docgen diff` is not implemented yet (milestone 5).", fg=typer.colors.YELLOW, err=True)
    raise typer.Exit(code=3)


def run_check(snapshot_path: Path, out_dir: Path, cfg: DocgenConfig) -> None:
    """Hygiene report only — fast, always offline."""
    from docgen.hygiene.checks import SEVERITY_ORDER, run_all_checks
    from docgen.rules_io import load_rules
    from docgen.snapshot.io import load_snapshot

    snapshot = load_snapshot(snapshot_path)
    rules = load_rules(cfg)
    findings = run_all_checks(snapshot, rules)
    render_documents(snapshot, ["hygiene"], cfg.formats, out_dir, cfg, no_llm=True)

    if findings:
        by_severity: dict[str, int] = {}
        for finding in findings:
            by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
        counts = ", ".join(f"{by_severity[s]} {s}"
                           for s in sorted(by_severity, key=lambda s: SEVERITY_ORDER.get(s, 9)))
        typer.secho(f"  {len(findings)} hygiene finding(s): {counts}", fg=typer.colors.YELLOW)
    else:
        typer.echo("  no hygiene findings")


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
