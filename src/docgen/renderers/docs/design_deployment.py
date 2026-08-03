"""Deployment Configuration Register — pre-build, from a discovery transcript.

After build this is the environment variables, connection references and
post-deployment checklist read from the solution. Before build it is what the
session established about environments, sites, availability, recovery, support
and migration — the constraints the deployment approach has to satisfy.
"""

from __future__ import annotations

from docgen.renderers.base import RenderContext
from docgen.renderers.docmodel import Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.transcript_design import (
    DesignDocRenderer,
    requirement_table,
    requirements_matching,
    statement_table,
)
from docgen.snapshot.transcript import TranscriptSnapshot


class DeploymentDesignRenderer(DesignDocRenderer):
    key = "deployment"
    title = "Deployment Configuration Register"
    purpose = (
        "How this gets built, released and run: environments, availability expectations, "
        "recovery targets, the support model and what has to be migrated. Configuration values "
        "cannot exist yet — the requirements they must meet already do."
    )

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:
        doc = self.shell(snapshot)
        doc.add(self._environments(snapshot))
        doc.add(self._availability(snapshot, ctx))
        doc.add(self._support(snapshot))
        doc.add(self._migration(snapshot, ctx))
        doc.add(self._configuration(snapshot))
        doc.add(self._checklist(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _environments(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Environments, sites and organisational structure")
        statements = snapshot.statements_in("environment")
        if statements:
            section.add(statement_table(statements))
        else:
            section.add(Paragraph("Sites and organisational structure were not discussed in this "
                                  "session."))
        section.add(Section("Environment strategy").add(
            Table(
                headers=["Environment", "Purpose", "Who has access", "Refreshed from", "Owner"],
                rows=[["[Consultant]", "", "", "", ""]],
            ),
            Placeholder(hint="Development, test, UAT, training and production: how many, who "
                             "provisions them, how code and data move between them, and who "
                             "approves a release into each."),
        ))
        return section

    def _availability(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Availability, performance and recovery")
        statements = snapshot.statements_in("availability")
        if statements:
            section.add(statement_table(statements))
        else:
            section.add(Callout("warning", "No availability or recovery expectations were stated. "
                                           "These set the hosting cost, so establish them before "
                                           "the estimate."))
        section.add(ctx.narrative(
            "design_availability",
            {"statements": [s.statement for s in statements]},
            hint="State the service levels the solution has to meet — hours of operation, "
                 "availability target, maintenance window, recovery point and recovery time — and "
                 "what each one implies for the hosting and backup approach.",
        ))
        section.add(Placeholder(
            hint="Confirm each target with the sponsor. An availability figure nobody has agreed "
                 "to pay for is not a requirement."))
        return section

    def _support(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Support, training and change")
        statements = snapshot.statements_in("support_model")
        if statements:
            section.add(statement_table(statements))
        else:
            section.add(Paragraph("The support model was not discussed in this session."))
        section.add(Placeholder(
            hint="Who runs this day to day, what the client's own team can absorb, what a partner "
                 "covers, and the training and change effort each user population needs. This is "
                 "routinely under-scoped — say so if it is."))
        return section

    def _migration(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Data migration")
        statements = snapshot.statements_in("data_migration")
        if statements:
            section.add(statement_table(statements))
            section.add(ctx.narrative(
                "design_migration",
                {"statements": [s.statement for s in statements],
                 "systems": [s.name for s in snapshot.external_systems]},
                hint="Summarise the migration position: what has to come across, from which "
                     "sources, how far back, what is archived rather than migrated, and where the "
                     "scope is still genuinely unknown.",
            ))
        else:
            section.add(Paragraph("Data migration was not discussed in this session."))
        section.add(Table(
            headers=["Source", "Data", "Volume", "Years", "Approach", "Owner"],
            rows=[["[Consultant]", "", "", "", "", ""]],
        ))
        section.add(Placeholder(
            hint="Migration is the most common cause of overrun on this kind of programme. Scope "
                 "it as its own workstream with its own discovery, or say explicitly that it has "
                 "not been scoped."))
        return section

    def _configuration(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Configuration to be defined at build")
        integration = requirements_matching(snapshot, "integrat", "interface", "export", "portal",
                                            "format", "submit", "feed")
        section.add(Paragraph(
            "Environment variables, connection references and secrets do not exist yet. This "
            "section is generated from the solution metadata after build; until then it records "
            "what will need per-environment configuration."))
        if integration:
            section.add(Section("Requirements implying per-environment configuration").add(
                requirement_table(integration)))
        section.add(Table(
            headers=["Setting", "Type", "Why it varies by environment", "Secret?", "Owner"],
            rows=[["[Consultant]", "", "", "", ""]],
        ))
        return section

    def _checklist(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Go-live checklist")
        phasing = requirements_matching(snapshot, "phase", "go live", "live", "by march",
                                        "first phase", "demonstrable")
        if phasing:
            section.add(Section("Go-live expectations stated in the session").add(
                requirement_table(phasing)))
        section.add(Placeholder(
            hint="Cutover plan, rollback plan, data validation, user provisioning, training "
                 "completion, hypercare arrangements and the go/no-go criteria with named owners."))
        return section
