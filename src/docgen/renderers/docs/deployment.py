"""Deployment configuration register — environment variables, connection
references, and detected post-deployment considerations. Fully deterministic."""

from __future__ import annotations

from docgen.renderers.base import DocRenderer, RenderContext
from docgen.renderers.docmodel import BulletList, Callout, Document, Paragraph, Section, Table
from docgen.renderers.docs.common import DASH, dash
from docgen.snapshot.models import Snapshot


class DeploymentRenderer(DocRenderer):
    key = "deployment"
    title = "Deployment Configuration Register"

    def build(self, snapshot: Snapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.solution.display_name or snapshot.solution.unique_name}",
                       subtitle=self.subtitle(snapshot))

        env_section = Section("Environment variables")
        if snapshot.environment_variables:
            env_section.add(Table(
                headers=["Schema name", "Display name", "Type", "Default value", "Current value", "Description"],
                rows=[[v.schema_name, dash(v.display_name), v.type or DASH,
                       "(secret)" if v.is_secret and v.default_value else dash(v.default_value),
                       "(secret)" if v.is_secret and v.current_value else dash(v.current_value),
                       dash(v.description)]
                      for v in snapshot.environment_variables],
            ))
        else:
            env_section.add(Paragraph("No environment variables in this solution."))
        doc.add(env_section)

        cr_section = Section("Connection references")
        if snapshot.connection_references:
            cr_section.add(Table(
                headers=["Logical name", "Display name", "Connector"],
                rows=[[c.logical_name, dash(c.display_name), dash(c.api_name)]
                      for c in snapshot.connection_references],
            ))
        else:
            cr_section.add(Paragraph("No connection references in this solution."))
        doc.add(cr_section)

        considerations: list[str] = []
        for v in snapshot.environment_variables:
            if v.current_value is None and v.default_value is None:
                considerations.append(
                    f"Environment variable `{v.schema_name}` has no default and no value — "
                    "it must be set in the target environment before the solution is used."
                )
            if v.is_secret:
                considerations.append(
                    f"Environment variable `{v.schema_name}` is a secret — configure the Azure Key Vault "
                    "reference (or secret value) per environment; secrets are never carried by the solution."
                )
        if snapshot.connection_references:
            considerations.append(
                f"{len(snapshot.connection_references)} connection reference(s) must be bound to connections "
                "in the target environment on first import."
            )
        draft_flows = [f for f in snapshot.cloud_flows if (f.state or "").lower() == "draft"]
        for flow in draft_flows:
            considerations.append(
                f"Flow `{flow.display_name or flow.unique_name}` is exported in Draft state — "
                "it will not run until switched on after deployment."
            )
        if snapshot.plugin_assemblies:
            considerations.append(
                f"{len(snapshot.plugin_assemblies)} plug-in assembly(ies) deploy with the solution; "
                "verify SDK step states after import."
            )
        if not snapshot.solution.managed:
            considerations.append(
                "The solution is unmanaged — deploy managed builds to test/production environments."
            )

        cons_section = Section("Post-deployment considerations")
        if considerations:
            cons_section.add(Callout("info", "Derived automatically from solution metadata; "
                                             "review and extend with environment-specific steps."))
            cons_section.add(BulletList(considerations))
        else:
            cons_section.add(Paragraph("No post-deployment configuration detected."))
        doc.add(cons_section)
        return doc
