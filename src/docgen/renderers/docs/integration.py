"""Integration Design — auto-generated integration inventory (what talks to
what) plus structured template sections for consultant completion. When no
integrations are detected the document is a one-page statement saying so."""

from __future__ import annotations

from docgen.renderers.base import DocRenderer, RenderContext
from docgen.renderers.docmodel import Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.common import DASH, dash
from docgen.snapshot.models import Snapshot


def _connector_usage(snapshot: Snapshot) -> dict[str, list[str]]:
    usage: dict[str, list[str]] = {}
    for flow in snapshot.cloud_flows:
        for connector in flow.connectors_used:
            usage.setdefault(connector, []).append(f"flow: {flow.display_name or flow.unique_name}")
    for ref in snapshot.connection_references:
        if ref.api_name:
            usage.setdefault(ref.api_name, []).append(f"connection reference: {ref.logical_name}")
    for app in snapshot.canvas_apps:
        for connector in app.connections:
            usage.setdefault(connector, []).append(f"canvas app: {app.display_name or app.name}")
    return usage


def has_integrations(snapshot: Snapshot) -> bool:
    return bool(
        snapshot.connection_references
        or snapshot.custom_connectors
        or snapshot.plugin_steps
        or _connector_usage(snapshot)
    )


class IntegrationRenderer(DocRenderer):
    key = "integration"
    title = "Integration Design"

    def build(self, snapshot: Snapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.solution.display_name or snapshot.solution.unique_name}",
                       subtitle=self.subtitle(snapshot))

        if not has_integrations(snapshot):
            doc.add(Section("No integrations detected").add(Paragraph(
                "No connectors, connection references, custom connectors or plug-in steps were found "
                "in this solution's metadata. If integrations exist outside this solution (for example "
                "in a separate solution, Azure services, or ISV components), document them separately."
            )))
            return doc

        usage = _connector_usage(snapshot)
        inventory = Section("Integration inventory")
        inventory.add(Paragraph(
            "Derived from solution metadata: every connector, connection reference, custom connector "
            "and plug-in step — i.e. everything in this solution that talks to another system."
        ))
        if usage:
            inventory.add(Section("Connectors in use").add(Table(
                headers=["Connector (API name)", "Used by"],
                rows=[[api, "; ".join(sorted(set(users)))] for api, users in sorted(usage.items())],
            )))
        if snapshot.connection_references:
            inventory.add(Section("Connection references").add(Table(
                headers=["Logical name", "Display name", "Connector"],
                rows=[[c.logical_name, dash(c.display_name), dash(c.api_name)]
                      for c in snapshot.connection_references],
            )))
        if snapshot.custom_connectors:
            inventory.add(Section("Custom connectors").add(Table(
                headers=["Name", "Display name", "Description"],
                rows=[[c.name, dash(c.display_name), dash(c.description)]
                      for c in snapshot.custom_connectors],
            )))
        if snapshot.plugin_steps:
            inventory.add(Section("Plug-in steps (server-side integration points)").add(Table(
                headers=["Step", "Message", "Table", "Stage", "Mode"],
                rows=[[s.name, dash(s.message), dash(s.primary_entity), dash(s.stage), dash(s.mode)]
                      for s in snapshot.plugin_steps],
            )))
        doc.add(inventory)

        doc.add(Section("Integration overview").add(ctx.narrative(
            "integration_overview",
            {"connectors": sorted(usage),
             "custom_connectors": [c.name for c in snapshot.custom_connectors],
             "plugin_steps": [s.name for s in snapshot.plugin_steps],
             "flows": [{"name": f.display_name or f.unique_name, "connectors": f.connectors_used}
                       for f in snapshot.cloud_flows]},
            hint="Describe the integration landscape: which systems this solution exchanges data with, "
                 "in which direction, and via which mechanism.",
        )))

        template_sections = [
            ("Endpoints & environments",
             "Per integration: endpoint URLs per environment (dev/test/prod), source system owner and contact."),
            ("Authentication & authorisation",
             "Per integration: auth mechanism (service principal, OAuth app, API key in Key Vault...), "
             "account/principal used, secret rotation policy."),
            ("Error contracts & retry policies",
             "Per integration: failure modes, retry/backoff behaviour, dead-letter or compensation handling, "
             "alerting on repeated failure."),
            ("Volumetrics & throughput",
             "Per integration: expected volumes (records/day, peak rates), payload sizes, API limits and "
             "licensing throughput constraints."),
            ("Monitoring & support",
             "How each integration is monitored, where logs land, and the support/escalation path."),
        ]
        for heading, hint in template_sections:
            doc.add(Section(heading).add(Placeholder(hint=hint)))
        return doc
