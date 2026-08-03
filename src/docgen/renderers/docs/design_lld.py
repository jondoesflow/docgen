"""Low-Level Design — pre-build, from a discovery transcript.

The as-built LLD is generated from metadata. This one is the LLD's skeleton:
per capability area, the requirements that drive it, the business objects the
client actually talks about, the process steps described, and a structured slot
for every detailed design decision that still has to be made.
"""

from __future__ import annotations

from docgen.renderers.base import RenderContext
from docgen.renderers.docmodel import Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.transcript_common import quote
from docgen.renderers.docs.transcript_design import (
    DesignDocRenderer,
    requirement_table,
    statement_table,
)
from docgen.snapshot.transcript import TranscriptSnapshot

# Candidate objects shown in the design skeleton. The full list is in the
# Data Dictionary; the LLD only needs the terms that dominate the conversation.
TOP_OBJECTS = 25


class LldDesignRenderer(DesignDocRenderer):
    key = "lld"
    title = "Low-Level Design"
    purpose = (
        "The detailed design skeleton: the requirements each area must satisfy, the business "
        "objects and process steps described in the session, and a slot for every design decision "
        "still to be made. Fill it in and it becomes the build specification."
    )

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:
        doc = self.shell(snapshot)
        doc.add(self._data_model(snapshot, ctx))
        doc.add(self._processes(snapshot))
        doc.add(self._areas(snapshot, ctx))
        doc.add(self._automation(snapshot))
        doc.add(self._interfaces(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _data_model(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Candidate data model")
        objects = snapshot.candidate_objects[:TOP_OBJECTS]
        if not objects:
            section.add(Paragraph("No repeated business terms were detected in this transcript."))
        else:
            section.add(Paragraph(
                "Terms the client used repeatedly. This is a word count, not a data model: it "
                "reports what the business talks about so the modelling conversation starts from "
                "their language rather than ours. Decide which become tables."))
            section.add(Table(
                headers=["Term", "Mentions", "Used by", "Attribute words heard", "Becomes a table?"],
                rows=[[o.surface_form, str(o.mentions), ", ".join(o.speakers[:3]) or "—",
                       ", ".join(o.attribute_terms) or "—", "[Consultant]"] for o in objects],
            ))
            section.add(ctx.narrative(
                "design_data_model",
                {"terms": [{"term": o.surface_form, "mentions": o.mentions,
                            "example": o.evidence.quote} for o in objects]},
                hint="Propose the core entities and the relationships between them, using the "
                     "client's own terms. Say which terms are the same thing under different names, "
                     "and which are attributes rather than entities.",
            ))
        section.add(Section("Entity definitions").add(Placeholder(
            hint="One block per entity: purpose, ownership, key attributes with types, "
                 "relationships, and the requirement IDs it satisfies. The Data Dictionary is "
                 "the detailed version of this.")))
        section.add(Section("Entity relationship diagram").add(Placeholder(
            hint="Draw the ERD once the entities are agreed. After build, this section is "
                 "generated automatically from the solution metadata.")))
        return section

    def _processes(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Process design")
        steps = snapshot.statements_in("process_step")
        if steps:
            section.add(Section("Current-state steps described in the session").add(
                statement_table(steps)))
        else:
            section.add(Paragraph("No current-state process steps were captured in this session."))
        section.add(Section("Target process").add(Placeholder(
            hint="Model the to-be process end to end: the steps, who performs each, the system "
                 "state before and after, the exception paths, and the requirement IDs each step "
                 "satisfies.")))
        return section

    def _areas(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Detailed design by capability area")
        areas = snapshot.requirement_areas()
        if not areas:
            section.add(Paragraph("No capability areas could be derived from this transcript."))
            return section

        objects_by_area: dict[str, list] = {}
        for candidate in snapshot.candidate_objects[:TOP_OBJECTS]:
            objects_by_area.setdefault(candidate.evidence.section_title, []).append(candidate)

        for area in areas:
            in_area = [r for r in snapshot.requirements if r.area == area]
            block = Section(area)
            block.add(requirement_table(in_area, area_column=False))
            terms = objects_by_area.get(area, [])
            if terms:
                block.add(Paragraph("Business terms first used in this area: "
                                    + ", ".join(f"{t.surface_form} ({t.mentions})" for t in terms)))
            block.add(ctx.narrative(
                "design_area_detail",
                {"area": area,
                 "requirements": [{"id": r.id, "verbatim": r.statement, "priority": r.priority}
                                  for r in in_area],
                 "terms": [t.surface_form for t in terms]},
                hint=f"Set out how “{area}” will work: the screens or forms involved, the data it "
                     "reads and writes, the rules it enforces, and the validation. Flag anything "
                     "the transcript leaves too vague to specify.",
            ))
            block.add(Placeholder(
                hint="Forms, views, field-level rules, validation and error handling for this area."))
            section.add(block)
        return section

    def _automation(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Automation and business logic")
        triggers = [r for r in snapshot.requirements
                    if any(word in r.statement.lower() for word in
                           ("alert", "notif", "warn", "escalat", "automatic", "tell me",
                            "reminder", "approaching", "flag"))]
        if triggers:
            section.add(Paragraph("Requirements that imply automation — each needs a trigger, "
                                  "a condition and an action defining:"))
            section.add(requirement_table(triggers))
        else:
            section.add(Paragraph("No automation requirements were detected in this session."))
        section.add(Placeholder(
            hint="For each: trigger (event or schedule), condition, action, who is notified, what "
                 "happens on failure, and whether it is synchronous or background."))
        return section

    def _interfaces(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Interfaces")
        if snapshot.external_systems:
            section.add(Table(
                headers=["System named", "Mentions", "First mentioned", "Section"],
                rows=[[s.name, str(s.mentions), quote(s.evidence.quote),
                       s.evidence.section_title or "—"] for s in snapshot.external_systems],
            ))
            section.add(Paragraph("Interface design is in the Integration Design document."))
        else:
            section.add(Callout("info", "No external systems were named in this session — confirm "
                                        "that the solution really is standalone before designing "
                                        "on that basis."))
        return section
