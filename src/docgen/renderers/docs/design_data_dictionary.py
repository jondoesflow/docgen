"""Data Dictionary — pre-build, from a discovery transcript.

After build this document lists every table and column from the metadata.
Before build it lists the vocabulary: the business terms the client actually
uses, how often, and where each was first said — so the modelling conversation
starts from their language, and so the eventual table names can be defended.
"""

from __future__ import annotations

from docgen.renderers.base import RenderContext
from docgen.renderers.docmodel import Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.transcript_common import quote
from docgen.renderers.docs.transcript_design import (
    DesignDocRenderer,
    requirement_table,
    requirements_matching,
    statement_table,
)
from docgen.snapshot.transcript import TranscriptSnapshot

# Terms below this many mentions are noise in a vocabulary list; the parser's
# own floor is lower so that the snapshot keeps the long tail.
REPORTED_MENTIONS = 4


class DataDictionaryDesignRenderer(DesignDocRenderer):
    key = "data-dictionary"
    title = "Data Dictionary"
    purpose = (
        "The client's vocabulary, evidenced. Which of these terms become tables, what their "
        "columns are and what each one means is the modelling work this document exists to "
        "structure — and the definitions agreed here are what the built system should be named "
        "after."
    )

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:
        doc = self.shell(snapshot)
        doc.add(self._vocabulary(snapshot, ctx))
        doc.add(self._attributes(snapshot))
        doc.add(self._reference_data(snapshot))
        doc.add(self._retention(snapshot))
        doc.add(self._definitions(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _vocabulary(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Business vocabulary")
        reported = [o for o in snapshot.candidate_objects if o.mentions >= REPORTED_MENTIONS]
        if not reported:
            section.add(Callout("warning", "No repeated business terms were detected. Either the "
                                           "session did not get into detail, or the transcript is "
                                           "too short to count vocabulary reliably."))
            return section

        section.add(Paragraph(
            f"{len(reported)} term(s) used {REPORTED_MENTIONS} or more times, most-used first. "
            "This is a frequency count of what was said, not a proposed schema: nothing here is a "
            "table until a human says it is. The last three columns are for that decision."))
        section.add(Table(
            headers=["Term", "Mentions", "Used by", "First said", "Becomes", "Name", "Definition"],
            rows=[[
                candidate.surface_form,
                str(candidate.mentions),
                ", ".join(candidate.speakers[:3]) or "—",
                quote(candidate.evidence.quote),
                "[Table / Column / Neither]",
                "[Consultant]",
                "[Consultant]",
            ] for candidate in reported],
        ))
        section.add(ctx.narrative(
            "design_vocabulary",
            {"terms": [{"term": t.surface_form, "mentions": t.mentions, "example": t.evidence.quote}
                       for t in reported[:40]]},
            hint="Group these terms: which are the same concept under different names, which are "
                 "entities, which are attributes of another entity, and which are process states "
                 "rather than data at all.",
        ))
        return section

    def _attributes(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Attribute terms heard")
        rows = []
        for candidate in snapshot.candidate_objects:
            for term in candidate.attribute_terms:
                rows.append([f"{candidate.surface_form} {term}", candidate.surface_form, term,
                             quote(candidate.evidence.quote)])
        if rows:
            section.add(Paragraph("Phrases where a business term was immediately followed by an "
                                  "attribute-shaped word. Candidate columns, nothing more:"))
            section.add(Table(headers=["Phrase", "Term", "Attribute word", "Context"], rows=rows))
        else:
            section.add(Paragraph("No attribute-shaped phrases were detected in this session."))
        return section

    def _reference_data(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Reference data and controlled lists")
        lists = requirements_matching(
            snapshot, "rate card", "price list", "screening value", "list price", "options",
            "types", "categories", "competency", "method", "template", "threshold", "standard",
        )
        if lists:
            section.add(Paragraph("Statements implying a controlled list. Each needs an owner, a "
                                  "change process and a decision on whether the business maintains "
                                  "it without IT:"))
            section.add(requirement_table(lists))
        else:
            section.add(Paragraph("No controlled lists were identified in this session."))
        section.add(Placeholder(
            hint="One row per reference list: name, values (or where they come from), who maintains "
                 "it, how often it changes, and whether history has to be kept when it does."))
        return section

    def _retention(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Retention, audit and data ownership")
        statements = snapshot.statements_in("retention")
        if statements:
            section.add(statement_table(statements))
        else:
            section.add(Paragraph("Retention and audit were not discussed in this session — "
                                  "confirm before designing anything that deletes."))
        section.add(Placeholder(
            hint="Per entity: retention period, legal basis, whether records can be deleted or only "
                 "superseded, what must be audited, and who owns the data."))
        return section

    def _definitions(self, snapshot: TranscriptSnapshot) -> Section:  # noqa: ARG002
        section = Section("Agreed definitions")
        section.add(Paragraph(
            "The dictionary proper. Complete one block per entity once the vocabulary above has "
            "been agreed with the client; after build, this section is generated from the "
            "solution metadata instead, and the two should say the same thing."))
        section.add(Table(
            headers=["Entity", "Business definition", "Owner", "Key attributes", "Requirement IDs"],
            rows=[["[Consultant]", "[Consultant]", "[Consultant]", "[Consultant]", "[Consultant]"]],
        ))
        section.add(Placeholder(
            hint="A definition is only useful if two people in the business would recognise it. "
                 "Write them in the client's words, not the platform's."))
        return section
