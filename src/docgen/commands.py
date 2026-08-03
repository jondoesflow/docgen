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


def run_parse_transcript(transcript_path: Path, out_dir: Path, cfg: DocgenConfig) -> Path:
    """Parse a meeting transcript, write transcript-snapshot.json + warnings."""
    from docgen.rules_io import load_rules
    from docgen.snapshot.io import save_transcript_snapshot
    from docgen.transcripts import parse_transcript

    cues = load_rules(cfg).get("transcript_cues", {})
    snapshot = parse_transcript(transcript_path, cues)
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = out_dir / "transcript-snapshot.json"
    save_transcript_snapshot(snapshot, snapshot_path)
    warnings_path = out_dir / "parse-warnings.md"
    warnings_path.write_text(transcript_warnings_markdown(snapshot), encoding="utf-8", newline="\n")

    s = snapshot
    typer.echo(f"Parsed {s.meeting.title or transcript_path.name} ({s.meeting.source_format} format)")
    typer.echo(
        f"  participants: {len(s.participants)}  sections: {len(s.sections)}  "
        f"turns: {s.stats.utterance_count}  words: {s.stats.word_count:,}"
    )
    typer.echo(
        f"  requirements: {len(s.requirements)}  decisions: {len(s.decisions)}  "
        f"actions: {len(s.actions)}  parked: {len(s.parked_items)}  RRAID seeds: {len(s.findings)}"
    )
    typer.echo(f"  snapshot: {snapshot_path}")
    if s.warnings:
        typer.secho(f"  {len(s.warnings)} parse warning(s) - see {warnings_path}", fg=typer.colors.YELLOW)
    else:
        typer.echo("  no parse warnings")
    return snapshot_path


def transcript_warnings_markdown(snapshot) -> str:
    stats = snapshot.stats
    lines = [f"# Parse warnings — {snapshot.meeting.title or snapshot.source_file}", "",
             f"Source: `{snapshot.source_file}` · format: `{snapshot.meeting.source_format}` · "
             f"{stats.lines_read:,} line(s) read, {stats.utterance_count} turn(s) attributed.", ""]
    if not snapshot.warnings:
        lines += ["No parse warnings. Every line of the transcript was recognised.", ""]
        return "\n".join(lines)
    lines += [
        f"{len(snapshot.warnings)} warning(s). Dialogue is never dropped — these record where the "
        "transcript was ambiguous or incomplete, so the documents can be read with that in mind.",
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
    from docgen.doc_templates import resolve_template
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
        template, template_note = resolve_template(key, renderer.title, cfg)
        for fmt in formats:
            if fmt == "md":
                written.append(write_markdown(document, out_dir / f"{key}.md"))
            elif fmt == "docx":
                written.append(write_docx(document, out_dir / f"{key}.docx", diagrams,
                                          template_path=template,
                                          context=solution_template_context(snapshot, key, renderer.title)))
        suffix = f" [{template_note}]" if template_note else ""
        typer.echo(f"  {key}: {renderer.title} -> {', '.join(formats)}{suffix}")

    report_llm_usage(narrative, cfg)
    return written


def solution_template_context(snapshot, key: str, title: str) -> dict:
    """Fields a branded template can reference as jinja placeholders."""
    s = snapshot.solution
    return {
        "doc_key": key,
        "doc_title": title,
        "solution_name": s.display_name or s.unique_name,
        "solution_unique_name": s.unique_name,
        "version": s.version,
        "managed": "Managed" if s.managed else "Unmanaged",
        "publisher": s.publisher.display_name or s.publisher.unique_name,
        "source_file": snapshot.source_file,
        "generated_at": snapshot.generated_at,
        "docgen_version": snapshot.docgen_version,
    }


def run_render_transcript(
    snapshot_path: Path,
    doc_keys: list[str],
    formats: list[str],
    out_dir: Path,
    cfg: DocgenConfig,
    *,
    no_llm: bool,
) -> list[Path]:
    from docgen.snapshot.io import load_transcript_snapshot

    snapshot = load_transcript_snapshot(snapshot_path)
    return render_transcript_documents(snapshot, doc_keys, formats, out_dir, cfg, no_llm=no_llm)


def render_transcript_documents(
    snapshot,
    doc_keys: list[str],
    formats: list[str],
    out_dir: Path,
    cfg: DocgenConfig,
    *,
    no_llm: bool,
) -> list[Path]:
    from docgen.doc_templates import resolve_template
    from docgen.renderers import get_transcript_renderer
    from docgen.renderers.base import RenderContext, offline_narrative
    from docgen.renderers.diagrams import DiagramService
    from docgen.renderers.docx import write_docx
    from docgen.renderers.markdown import write_markdown
    from docgen.rules_io import load_rules

    out_dir.mkdir(parents=True, exist_ok=True)
    diagrams = DiagramService(out_dir)
    narrative = offline_narrative
    if not no_llm and cfg.llm.enabled:
        from docgen.llm import make_transcript_narrative_provider

        narrative = make_transcript_narrative_provider(snapshot, cfg, out_dir)
    ctx = RenderContext(config=cfg, out_dir=out_dir, narrative_provider=narrative, rules=load_rules(cfg))

    written: list[Path] = []
    for key in doc_keys:
        renderer = get_transcript_renderer(key)
        if renderer is None:
            typer.secho(f"  {key}: renderer not implemented yet — skipped", fg=typer.colors.YELLOW)
            continue
        if not renderer.applies(snapshot):
            typer.echo(f"  {key}: not applicable to this transcript — skipped")
            continue
        document = renderer.build(snapshot, ctx)
        template, template_note = resolve_template(key, renderer.title, cfg)
        for fmt in formats:
            if fmt == "md":
                written.append(write_markdown(document, out_dir / f"{key}.md"))
            elif fmt == "docx":
                written.append(write_docx(document, out_dir / f"{key}.docx", diagrams,
                                          template_path=template,
                                          context=transcript_template_context(snapshot, key, renderer.title)))
        suffix = f" [{template_note}]" if template_note else ""
        typer.echo(f"  {key}: {renderer.title} -> {', '.join(formats)}{suffix}")

    report_llm_usage(narrative, cfg)
    return written


def transcript_template_context(snapshot, key: str, title: str) -> dict:
    """Fields a branded template can reference as jinja placeholders."""
    meeting = snapshot.meeting
    return {
        "doc_key": key,
        "doc_title": title,
        "meeting_title": meeting.title,
        "client": meeting.client_organisation or "",
        "consultancy": meeting.consultancy or "",
        "meeting_date": meeting.date or "",
        "meeting_time": meeting.time or "",
        "location": meeting.location or "",
        "facilitator": meeting.facilitator or "",
        "source_file": snapshot.source_file,
        "generated_at": snapshot.generated_at,
        "docgen_version": snapshot.docgen_version,
    }


def report_llm_usage(narrative, cfg: DocgenConfig) -> None:
    """Print token usage + estimated API cost for this run (if any)."""
    client = getattr(narrative, "client", None)
    calls = getattr(client, "calls", 0)
    if not client or not calls:
        return
    from docgen.llm.pricing import usage_summary_line

    spec = getattr(client, "spec", None)
    provider = getattr(spec, "key", cfg.llm.provider)
    typer.secho(
        "  " + usage_summary_line(
            getattr(client, "model", cfg.llm.model),
            calls,
            getattr(client, "total_input_tokens", 0),
            getattr(client, "total_output_tokens", 0),
            provider=provider,
        ),
        fg=typer.colors.CYAN,
    )
    console = f"the {spec.display_name} billing console" if spec else "the provider's billing console"
    typer.echo(f"  (estimate from published API prices; {console} is authoritative)")


def run_diff(old_path: Path, new_path: Path, formats: list[str], out_dir: Path, cfg: DocgenConfig) -> None:
    """Release notes + changed-component report from two snapshots."""
    import json

    from docgen.diffing.engine import diff_snapshots
    from docgen.doc_templates import resolve_template
    from docgen.renderers.diagrams import DiagramService
    from docgen.renderers.docs.release_notes import build_release_notes
    from docgen.renderers.docx import write_docx
    from docgen.renderers.markdown import write_markdown
    from docgen.snapshot.io import load_snapshot

    old_snapshot = load_snapshot(old_path)
    new_snapshot = load_snapshot(new_path)
    changeset = diff_snapshots(old_snapshot, new_snapshot)
    document = build_release_notes(changeset)

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "changed-components.json"
    report_path.write_text(json.dumps(changeset.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8", newline="\n")
    diagrams = DiagramService(out_dir)
    template, template_note = resolve_template("release-notes", "Release Notes", cfg)
    for fmt in formats:
        if fmt == "md":
            write_markdown(document, out_dir / "release-notes.md")
        elif fmt == "docx":
            write_docx(document, out_dir / "release-notes.docx", diagrams, template_path=template,
                       context={"doc_key": "release-notes", "doc_title": "Release Notes",
                                "old_version": changeset.old_version, "version": changeset.new_version})
    if template_note:
        typer.echo(f"  release notes rendered with {template_note}")

    breaking = len(changeset.breaking_changes)
    typer.echo(f"  {len(changeset.changes)} changed component(s), "
               f"v{changeset.old_version} -> v{changeset.new_version}")
    if breaking:
        typer.secho(f"  {breaking} breaking-change candidate(s) - review release-notes", fg=typer.colors.RED)
    typer.echo(f"  release notes: {out_dir / 'release-notes.md'}")
    typer.echo(f"  changed-component report: {report_path}")


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


def run_check_transcript(snapshot_path: Path, out_dir: Path, cfg: DocgenConfig) -> None:
    """Discovery hygiene report only — is this session good enough to design from?"""
    from docgen.snapshot.io import load_transcript_snapshot

    snapshot = load_transcript_snapshot(snapshot_path)
    render_transcript_documents(snapshot, ["hygiene"], cfg.formats, out_dir, cfg, no_llm=True)

    gaps = [
        (len([r for r in snapshot.requirements if r.priority == "unclassified"]), "unprioritised requirement(s)"),
        (len([a for a in snapshot.actions if not a.due]), "action(s) with no due date"),
        (len([a for a in snapshot.actions if not (a.owner_key or a.owner_name)]), "action(s) with no owner"),
        (len(snapshot.parked_items), "parked item(s)"),
    ]
    open_items = [f"{count} {label}" for count, label in gaps if count]
    if open_items:
        typer.secho("  discovery gaps: " + ", ".join(open_items), fg=typer.colors.YELLOW)
    else:
        typer.echo("  no discovery gaps")


def run_learn_check(out_dir: Path, cfg: DocgenConfig) -> None:
    """--check-learn: verify deprecation-rule Learn references are still reachable."""
    from docgen.learn_check import check_rule_urls, write_report
    from docgen.rules_io import load_rules

    typer.echo("== learn check ==")
    results = check_rule_urls(load_rules(cfg).get("deprecations", {}))
    report = write_report(results, out_dir)
    unreachable = sum(1 for r in results if r.status == "unreachable")
    if unreachable:
        typer.secho(f"  {unreachable} Learn reference(s) unreachable - see {report}", fg=typer.colors.YELLOW)
    else:
        typer.echo(f"  {len(results)} deprecation rule reference(s) checked - see {report}")


def run_all(
    solution_zip: Path,
    doc_keys: list[str],
    formats: list[str],
    out_dir: Path,
    cfg: DocgenConfig,
    *,
    no_llm: bool,
    check_learn: bool = False,
) -> None:
    """parse + check + render everything in one step."""
    typer.echo("== parse ==")
    snapshot_path = run_parse(solution_zip, out_dir)
    typer.echo("== check ==")
    run_check(snapshot_path, out_dir, cfg)
    typer.echo("== render ==")
    run_render(snapshot_path, doc_keys, formats, out_dir, cfg, no_llm=no_llm)
    if check_learn:
        run_learn_check(out_dir, cfg)
    typer.echo(f"Done. Output folder: {out_dir}")


def run_all_transcript(
    transcript_path: Path,
    doc_keys: list[str],
    formats: list[str],
    out_dir: Path,
    cfg: DocgenConfig,
    *,
    no_llm: bool,
) -> None:
    """parse + check + render, mirroring `run_all` for a solution."""
    typer.echo("== parse ==")
    snapshot_path = run_parse_transcript(transcript_path, out_dir, cfg)
    typer.echo("== check ==")
    run_check_transcript(snapshot_path, out_dir, cfg)
    typer.echo("== render ==")
    run_render_transcript(snapshot_path, doc_keys, formats, out_dir, cfg, no_llm=no_llm)
    typer.echo(f"Done. Output folder: {out_dir}")
