"""Low-Level Design document — fully deterministic.

Complete data model (ERD per functional cluster, attribute/relationship
detail), forms & views inventory, flow breakdowns, plugin step register and
the full component inventory.
"""

from __future__ import annotations

from docgen.renderers.base import DocRenderer, RenderContext
from docgen.renderers.clusters import functional_clusters
from docgen.renderers.diagrams import build_erd
from docgen.renderers.docmodel import Document, Paragraph, Section, Table
from docgen.renderers.docs.common import (
    DASH,
    attribute_type,
    dash,
    description_cell,
    entity_label,
    requirement,
    solution_facts,
)
from docgen.snapshot.models import Entity, Snapshot


def _entity_section(entity: Entity) -> Section:
    section = Section(entity_label(entity))
    facts = [
        f"Ownership: {dash(entity.ownership_type)}",
        f"Custom: {'yes' if entity.is_custom else 'no'}",
        f"Primary name: {dash(entity.primary_name_attribute)}",
    ]
    section.add(Paragraph(entity.description or "No description recorded for this table."))
    section.add(Paragraph(" · ".join(facts)))

    if entity.attributes:
        section.add(
            Section("Columns").add(
                Table(
                    headers=["Logical name", "Display name", "Type", "Requirement", "Description"],
                    rows=[
                        [a.logical_name, dash(a.display_name), attribute_type(a), requirement(a),
                         description_cell(a.description)]
                        for a in entity.attributes
                    ],
                )
            )
        )
    if entity.relationships:
        section.add(
            Section("Relationships").add(
                Table(
                    headers=["Schema name", "Type", "From (one/first)", "To (many/second)", "Lookup column", "Cascade delete"],
                    rows=[
                        [r.schema_name, "N:N" if r.type == "many_to_many" else "1:N",
                         r.referenced_entity, r.referencing_entity,
                         dash(r.referencing_attribute), dash(r.cascade_delete)]
                        for r in entity.relationships
                    ],
                )
            )
        )
    if entity.forms:
        section.add(
            Section("Forms").add(
                Table(headers=["Name", "Type"], rows=[[f.name, dash(f.form_type)] for f in entity.forms])
            )
        )
    if entity.views:
        section.add(
            Section("Views").add(
                Table(
                    headers=["Name", "Type", "Default", "Columns"],
                    rows=[[v.name, dash(v.view_type), "yes" if v.is_default else "", ", ".join(v.columns) or DASH]
                          for v in entity.views],
                )
            )
        )
    if entity.business_rules:
        section.add(
            Section("Business rules").add(
                Table(
                    headers=["Name", "Scope", "State"],
                    rows=[[b.name, dash(b.scope), dash(b.state)] for b in entity.business_rules],
                )
            )
        )
    return section


class LldRenderer(DocRenderer):
    key = "lld"
    title = "Low-Level Design"

    def build(self, snapshot: Snapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.solution.display_name or snapshot.solution.unique_name}",
                       subtitle=self.subtitle(snapshot))

        doc.add(Section("Solution overview").add(Table(headers=["Property", "Value"], rows=solution_facts(snapshot))))

        clusters = functional_clusters(snapshot)
        if clusters:
            erd_section = Section("Data model")
            entities_by_name = {e.logical_name: e for e in snapshot.entities}
            if len(snapshot.entities) > 1:
                overview = build_erd("erd-overview", snapshot.entities, include_attributes=False,
                                     caption="Solution overview — all tables and relationships")
                erd_section.add(overview)
            for i, cluster in enumerate(clusters, start=1):
                members = [entities_by_name[n] for n in cluster.entities]
                cluster_section = Section(f"Functional cluster: {cluster.name}")
                cluster_section.add(Paragraph(
                    f"Tables: {', '.join(cluster.entities)}"))
                cluster_section.add(build_erd(f"erd-cluster-{i}", members, caption=f"ERD — {cluster.name} cluster"))
                erd_section.add(cluster_section)
            doc.add(erd_section)

        if snapshot.entities:
            tables_section = Section("Tables")
            for entity in snapshot.entities:
                tables_section.add(_entity_section(entity))
            doc.add(tables_section)

        if snapshot.global_option_sets:
            doc.add(
                Section("Global choice sets").add(
                    Table(
                        headers=["Name", "Display name", "Values"],
                        rows=[
                            [o.name, dash(o.display_name),
                             "; ".join(f"{opt.value} = {opt.label}" for opt in o.options) or DASH]
                            for o in snapshot.global_option_sets
                        ],
                    )
                )
            )

        flows_section = Section("Cloud flows")
        if snapshot.cloud_flows:
            for flow in snapshot.cloud_flows:
                fs = Section(flow.display_name or flow.unique_name)
                trigger = flow.trigger
                trigger_text = (
                    f"Trigger: {trigger.name} ({trigger.type}"
                    + (f", connector {trigger.connector}" if trigger and trigger.connector else "")
                    + ")"
                ) if trigger else "Trigger: unknown"
                facts = [trigger_text, f"State: {dash(flow.state)}",
                         f"Error-handling scope: {'yes' if flow.has_error_scope else 'no'}"]
                if flow.connectors_used:
                    facts.append(f"Connectors: {', '.join(flow.connectors_used)}")
                fs.add(Paragraph(" · ".join(facts)))
                if flow.description:
                    fs.add(Paragraph(flow.description))
                if flow.actions:
                    fs.add(Table(
                        headers=["Action", "Type", "Connector", "Operation", "Runs after"],
                        rows=[[a.path, a.type, dash(a.connector), dash(a.operation_id),
                               ", ".join(a.run_after_statuses) or "start"] for a in flow.actions],
                    ))
                flows_section.add(fs)
        else:
            flows_section.add(Paragraph("No cloud flows in this solution."))
        doc.add(flows_section)

        plugin_section = Section("Plug-in step register")
        if snapshot.plugin_steps:
            plugin_section.add(Table(
                headers=["Step", "Message", "Table", "Stage", "Mode", "Rank", "Filtering columns", "Assembly"],
                rows=[[s.name, dash(s.message), dash(s.primary_entity), dash(s.stage), dash(s.mode),
                       dash(s.rank), ", ".join(s.filtering_attributes) or DASH, dash(s.assembly_name)]
                      for s in snapshot.plugin_steps],
            ))
        else:
            plugin_section.add(Paragraph("No plug-in steps in this solution."))
        doc.add(plugin_section)

        inventory = Section("Component inventory")
        inventory.add(Table(
            headers=["Component type", "Count"],
            rows=[
                ["Tables", str(len(snapshot.entities))],
                ["Global choice sets", str(len(snapshot.global_option_sets))],
                ["Security roles", str(len(snapshot.security_roles))],
                ["Field security profiles", str(len(snapshot.field_security_profiles))],
                ["Cloud flows", str(len(snapshot.cloud_flows))],
                ["Connection references", str(len(snapshot.connection_references))],
                ["Environment variables", str(len(snapshot.environment_variables))],
                ["Plug-in assemblies", str(len(snapshot.plugin_assemblies))],
                ["Plug-in steps", str(len(snapshot.plugin_steps))],
                ["Web resources", str(len(snapshot.web_resources))],
                ["Custom connectors", str(len(snapshot.custom_connectors))],
                ["Canvas apps", str(len(snapshot.canvas_apps))],
                ["Other components", str(len(snapshot.other_components))],
            ],
        ))
        if snapshot.web_resources:
            inventory.add(Section("Web resources").add(Table(
                headers=["Name", "Display name", "Type"],
                rows=[[w.name, dash(w.display_name), dash(w.type)] for w in snapshot.web_resources],
            )))
        if snapshot.canvas_apps:
            inventory.add(Section("Canvas apps").add(Table(
                headers=["Name", "Display name", "Connections"],
                rows=[[a.name, dash(a.display_name), ", ".join(a.connections) or DASH]
                      for a in snapshot.canvas_apps],
            )))
        if snapshot.custom_connectors:
            inventory.add(Section("Custom connectors").add(Table(
                headers=["Name", "Display name", "Description"],
                rows=[[c.name, dash(c.display_name), description_cell(c.description)]
                      for c in snapshot.custom_connectors],
            )))
        if snapshot.other_components:
            inventory.add(Section("Other components (generic inventory)").add(Table(
                headers=["Name / id", "Type"],
                rows=[[g.schema_name_or_id, g.type_label or f"type {g.component_type}"]
                      for g in snapshot.other_components],
            )))
        doc.add(inventory)
        return doc
