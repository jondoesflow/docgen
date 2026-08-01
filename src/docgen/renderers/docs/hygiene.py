"""Hygiene report — configurable checks over the snapshot: missing descriptions,
unmanaged layers, flows without error handling, unused option sets, naming
violations, deprecations, dangling references."""

from __future__ import annotations

from docgen.hygiene.checks import SEVERITY_ORDER, run_all_checks
from docgen.renderers.base import DocRenderer, RenderContext
from docgen.renderers.docmodel import Callout, Document, Paragraph, Section, Table
from docgen.snapshot.models import Snapshot


class HygieneRenderer(DocRenderer):
    key = "hygiene"
    title = "Solution Hygiene Report"

    def build(self, snapshot: Snapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.solution.display_name or snapshot.solution.unique_name}",
                       subtitle=self.subtitle(snapshot))
        findings = run_all_checks(snapshot, ctx.rules)

        summary = Section("Summary")
        by_severity: dict[str, int] = {}
        for finding in findings:
            by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
        if findings:
            counts = ", ".join(f"{by_severity[s]} {s}" for s in sorted(by_severity, key=lambda s: SEVERITY_ORDER.get(s, 9)))
            summary.add(Paragraph(f"{len(findings)} finding(s): {counts}."))
        else:
            summary.add(Paragraph("No hygiene findings — clean solution against the current rules."))
        if snapshot.warnings:
            summary.add(Callout("info", f"The parser also raised {len(snapshot.warnings)} warning(s) — "
                                        "see parse-warnings.md for components docgen could not fully read."))
        doc.add(summary)

        by_category: dict[str, list] = {}
        for finding in findings:
            by_category.setdefault(finding.category, []).append(finding)

        titles = {
            "descriptions": "Missing descriptions",
            "unmanaged": "Unmanaged layers",
            "flows": "Flows without error handling",
            "option_sets": "Unused choice sets",
            "naming": "Naming convention violations",
            "deprecation": "Deprecated / discouraged features",
            "references": "Missing dependencies",
        }
        for category in sorted(by_category, key=lambda c: list(titles).index(c) if c in titles else 99):
            group = by_category[category]
            section = Section(f"{titles.get(category, category.title())} ({len(group)})")
            section.add(Table(
                headers=["Rule", "Severity", "Component", "Finding", "Evidence"],
                rows=[[f.rule_id, f.severity, f.component, f.message, f.evidence] for f in group],
            ))
            doc.add(section)
        return doc
