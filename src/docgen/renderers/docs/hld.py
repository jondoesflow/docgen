"""High-Level Design — deterministic skeleton (inventories, ERD, facts) with
narrative sections drafted by the LLM tier or left as consultant placeholders."""

from __future__ import annotations

from docgen.renderers.base import DocRenderer, RenderContext
from docgen.renderers.clusters import functional_clusters
from docgen.renderers.diagrams import build_erd
from docgen.renderers.docmodel import Document, Paragraph, Section, Table
from docgen.renderers.docs.common import dash, solution_facts
from docgen.snapshot.models import Snapshot


class HldRenderer(DocRenderer):
    key = "hld"
    title = "High-Level Design"

    def build(self, snapshot: Snapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.solution.display_name or snapshot.solution.unique_name}",
                       subtitle=self.subtitle(snapshot))
        clusters = functional_clusters(snapshot)

        overview = Section("Solution overview")
        overview.add(Table(headers=["Property", "Value"], rows=solution_facts(snapshot)))
        overview.add(ctx.narrative(
            "hld_overview",
            {
                "solution": snapshot.solution.model_dump(mode="json"),
                "entities": [{"logical_name": e.logical_name, "display_name": e.display_name,
                              "description": e.description} for e in snapshot.entities],
                "flows": [{"name": f.display_name or f.unique_name, "description": f.description}
                          for f in snapshot.cloud_flows],
                "clusters": [{"name": c.name, "entities": c.entities} for c in clusters],
            },
            hint="Describe what this solution does for the business: purpose, scope, primary users "
                 "and the business processes it supports.",
        ))
        doc.add(overview)

        if clusters:
            areas = Section("Functional areas")
            entities_by_name = {e.logical_name: e for e in snapshot.entities}
            for i, cluster in enumerate(clusters, start=1):
                members = [entities_by_name[n] for n in cluster.entities]
                area = Section(f"{cluster.name}")
                area.add(Table(
                    headers=["Table", "Description"],
                    rows=[[f"{e.display_name or e.logical_name} ({e.logical_name})",
                           e.description or "—"] for e in members],
                ))
                area.add(ctx.narrative(
                    "hld_cluster",
                    {"cluster": cluster.name,
                     "entities": [{"logical_name": e.logical_name, "display_name": e.display_name,
                                   "description": e.description,
                                   "relationships": [r.schema_name for r in e.relationships]}
                                  for e in members]},
                    hint=f"Summarise the {cluster.name} functional area: what it models and how the "
                         "tables work together in the business process.",
                ))
                areas.add(area)
            doc.add(areas)

        architecture = Section("Architecture")
        if len(snapshot.entities) > 1:
            architecture.add(build_erd("hld-erd-overview", snapshot.entities, include_attributes=False,
                                       caption="Solution data model overview"))
        facts = [
            f"{len(snapshot.entities)} tables across {len(clusters)} functional cluster(s)",
            f"{len(snapshot.cloud_flows)} cloud flow(s) using "
            f"{len({c for f in snapshot.cloud_flows for c in f.connectors_used})} connector(s)",
            f"{len(snapshot.plugin_steps)} plug-in step(s) in {len(snapshot.plugin_assemblies)} assembly(ies)",
            f"{len(snapshot.security_roles)} security role(s), "
            f"{len(snapshot.field_security_profiles)} field security profile(s)",
            f"{len(snapshot.environment_variables)} environment variable(s), "
            f"{len(snapshot.connection_references)} connection reference(s)",
            f"{len(snapshot.canvas_apps)} canvas app(s), {len(snapshot.web_resources)} web resource(s)",
        ]
        architecture.add(Table(headers=["Architecture facts"], rows=[[f] for f in facts]))
        architecture.add(ctx.narrative(
            "hld_architecture",
            {"facts": facts,
             "connectors": sorted({c for f in snapshot.cloud_flows for c in f.connectors_used}
                                  | {c.api_name for c in snapshot.connection_references if c.api_name})},
            hint="Describe the architecture: how model-driven components, automation and integrations "
                 "fit together, and any notable design decisions visible in the metadata.",
        ))
        doc.add(architecture)

        automation = Section("Automation")
        if snapshot.cloud_flows:
            for flow in snapshot.cloud_flows:
                flow_section = Section(flow.display_name or flow.unique_name)
                trigger = flow.trigger
                facts_line = " · ".join(filter(None, [
                    f"Trigger: {trigger.name} ({trigger.type})" if trigger else "Trigger: unknown",
                    f"Connectors: {', '.join(flow.connectors_used)}" if flow.connectors_used else None,
                    f"State: {dash(flow.state)}",
                    "Has error handling" if flow.has_error_scope else "No error handling scope",
                ]))
                flow_section.add(Paragraph(facts_line))
                flow_section.add(ctx.narrative(
                    "flow_description",
                    {"flow": {"name": flow.display_name or flow.unique_name,
                              "description": flow.description,
                              "trigger": trigger.model_dump(mode="json") if trigger else None,
                              "actions": [a.model_dump(mode="json") for a in flow.actions]}},
                    hint="Plain-English description of what this flow does, step by step, "
                         "for a non-technical reader.",
                ))
                automation.add(flow_section)
        else:
            automation.add(Paragraph("No cloud flows in this solution."))
        if snapshot.plugin_steps:
            automation.add(Section("Server-side logic").add(Table(
                headers=["Plug-in step", "Message", "Table", "Stage", "Mode"],
                rows=[[s.name, dash(s.message), dash(s.primary_entity), dash(s.stage), dash(s.mode)]
                      for s in snapshot.plugin_steps],
            )))
        doc.add(automation)

        security = Section("Security model summary")
        if snapshot.security_roles:
            security.add(Table(
                headers=["Role", "Privileges"],
                rows=[[r.name, str(len(r.privileges))] for r in snapshot.security_roles],
            ))
            security.add(Paragraph("Full privilege matrices are in the Security & Access Model document."))
        else:
            security.add(Paragraph("No security roles in this solution."))
        doc.add(security)
        return doc
