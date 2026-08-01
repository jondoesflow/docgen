"""Licensing impact summary — premium connectors/features detected, flagged for
commercial review. Rules-driven from rules/licensing.yaml."""

from __future__ import annotations

from docgen.hygiene.checks import detect_licensing
from docgen.renderers.base import DocRenderer, RenderContext
from docgen.renderers.docmodel import BulletList, Callout, Document, Paragraph, Section, Table
from docgen.snapshot.models import Snapshot


class LicensingRenderer(DocRenderer):
    key = "licensing"
    title = "Licensing Impact Summary"

    def build(self, snapshot: Snapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.solution.display_name or snapshot.solution.unique_name}",
                       subtitle=self.subtitle(snapshot))
        hits, signals = detect_licensing(snapshot, ctx.rules.get("licensing", {}))

        summary = Section("Summary")
        if hits or signals:
            summary.add(Callout(
                "warning",
                f"{len(hits)} premium connector(s) and {len(signals)} additional premium signal(s) detected. "
                "Licensing entitlements should be confirmed with the customer's commercial team before "
                "deployment — connector premium status and license terms change over time.",
            ))
        else:
            summary.add(Paragraph(
                "No premium connector usage detected against the current licensing rules. "
                "Confirm the rules file is up to date before treating this as a clean bill."
            ))
        doc.add(summary)

        if hits:
            doc.add(Section("Premium connectors detected").add(Table(
                headers=["Connector", "API name", "Used by", "Licensing note"],
                rows=[[h.label, h.connector, "; ".join(h.used_by), h.note] for h in hits],
            )))
        if signals:
            doc.add(Section("Other premium signals").add(BulletList(signals)))

        standard = licensing_standard_usage(snapshot, ctx.rules.get("licensing", {}))
        if standard:
            doc.add(Section("Standard connectors in use").add(
                Table(headers=["API name"], rows=[[s] for s in standard])))
        return doc


def licensing_standard_usage(snapshot: Snapshot, licensing_rules: dict) -> list[str]:
    standard = set(licensing_rules.get("standard_connectors") or [])
    used = set()
    for flow in snapshot.cloud_flows:
        used.update(flow.connectors_used)
    for ref in snapshot.connection_references:
        if ref.api_name:
            used.add(ref.api_name)
    for app in snapshot.canvas_apps:
        used.update(app.connections)
    return sorted(used & standard)
