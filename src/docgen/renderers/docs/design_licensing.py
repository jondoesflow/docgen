"""Licensing Impact Summary — pre-build, from a discovery transcript.

After build this detects premium connectors and features in the metadata.
Before build it surfaces the things that drive licence cost — how many users of
what kind, external portal access, mobile and offline working, integration and
reporting — while the commercial position can still be shaped by design.
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

# Cost drivers to check off explicitly, and the terms that hint at each. Absence
# of a hint is reported as "not discussed", never as "not required".
COST_DRIVERS = (
    ("Internal named users", ("staff", "users", "access", "read-only", "licence", "license")),
    ("External / customer portal users", ("portal", "self-serve", "customer", "external", "login")),
    ("Mobile and offline working", ("mobile", "offline", "tablet", "ruggedised", "field")),
    ("Integration with other systems", ("integrat", "interface", "export", "format", "submit", "feed")),
    ("Reporting and analytics", ("report", "dashboard", "analytics", "self-service", "margin", "pipeline")),
    ("Document generation and storage", ("certificate", "pdf", "template", "document", "storage", "terabyte")),
    ("Managed service / hosting", ("managed service", "hosting", "support", "partner")),
)


class LicensingDesignRenderer(DesignDocRenderer):
    key = "licensing"
    title = "Licensing Impact Summary"
    purpose = (
        "What is going to cost money to license, established while the design can still change. "
        "Nothing here is a price: it is the set of questions a commercial review has to answer, "
        "each backed by what was said in the room."
    )

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:
        doc = self.shell(snapshot)
        doc.add(self._drivers(snapshot))
        doc.add(self._populations(snapshot))
        doc.add(self._signals(snapshot, ctx))
        doc.add(self._systems(snapshot))
        doc.add(self._review(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _drivers(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Cost drivers — discussed or not")
        haystack = " ".join(
            f"{r.statement} {r.area}" for r in snapshot.requirements
        ).lower() + " " + " ".join(s.statement for s in snapshot.statements).lower()
        rows = []
        for driver, terms in COST_DRIVERS:
            hits = [term for term in terms if term in haystack]
            rows.append([
                driver,
                "Discussed" if hits else "⚠ Not discussed",
                ", ".join(hits) if hits else "—",
                "[Consultant]",
            ])
        section.add(Paragraph(
            "A checklist of what usually drives licence cost on this kind of programme, against "
            "what the session actually covered. “Not discussed” means the transcript is silent — "
            "not that the requirement is absent."))
        section.add(Table(
            headers=["Cost driver", "Covered in session?", "Terms heard", "Commercial position"],
            rows=rows,
        ))
        missing = sum(1 for row in rows if row[1].startswith("⚠"))
        if missing:
            section.add(Callout("warning", f"{missing} cost driver(s) were never discussed. Close "
                                           "these off before committing to a price."))
        return section

    def _populations(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("User numbers")
        statements = snapshot.statements_in("user_population")
        if statements:
            section.add(Paragraph("Every number stated about users. Licence cost is usually a "
                                  "direct function of these, so they need confirming rather than "
                                  "estimating:"))
            section.add(statement_table(statements))
        else:
            section.add(Callout("warning", "No user numbers were stated in this session — a "
                                           "licence estimate is not possible without them."))
        section.add(Table(
            headers=["Population", "Count", "Licence type", "Internal / external", "Confirmed?"],
            rows=[["[Consultant]", "", "", "", ""]],
        ))
        return section

    def _signals(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Statements with a commercial implication")
        statements = snapshot.statements_in("licensing_signal")
        if statements:
            section.add(statement_table(statements))
        else:
            section.add(Paragraph("No specific licensing signals were detected in this session."))
        section.add(ctx.narrative(
            "design_licensing",
            {"signals": [s.statement for s in statements],
             "populations": [s.statement for s in snapshot.statements_in("user_population")]},
            hint="Explain where the commercial exposure sits and which design choices would move "
                 "it. Do not quote prices or name specific licence SKUs — the point is which "
                 "decisions have a cost attached.",
        ))
        return section

    def _systems(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Third-party systems and interfaces")
        if snapshot.external_systems:
            section.add(Paragraph("Each of these may carry its own licence, connector or API cost, "
                                  "and may need a licence on the client's side too:"))
            section.add(Table(
                headers=["System named", "Mentions", "Licence / connector cost", "Owner"],
                rows=[[s.name, str(s.mentions), "[Consultant]", "[Consultant]"]
                      for s in snapshot.external_systems],
            ))
        else:
            section.add(Paragraph("No external systems were named in this session."))
        return section

    def _review(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Commercial review")
        budget = requirements_matching(snapshot, "budget", "capital", "running cost", "board",
                                       "afford", "envelope", "estimate")
        if budget:
            section.add(Section("Budget and commercial statements").add(requirement_table(budget)))
        section.add(Placeholder(
            hint="Take the confirmed user numbers and design choices to a licensing specialist "
                 "before the estimate goes out. Record the date, who reviewed it, and the "
                 "assumptions the figure depends on — licence models change."))
        return section
