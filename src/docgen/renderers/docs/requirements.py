"""Requirements Catalogue — candidates extracted from the transcript, each one
carrying the sentence it came from, who said it and the line it is on.

The deterministic tier never rewrites a requirement: it surfaces the verbatim
statement, the area it was raised in and the priority word that was actually
used. Turning that into a formal "the system shall…" statement is judgement, so
it is either drafted by the LLM tier or left as a placeholder next to the
evidence. That keeps the catalogue arguable in a workshop playback: every row
can be traced back to a sentence somebody said.
"""

from __future__ import annotations

from docgen.renderers.base import RenderContext, TranscriptDocRenderer
from docgen.renderers.docmodel import Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.common import dash
from docgen.renderers.docs.transcript_common import (
    KIND_LABELS,
    PRIORITY_LABELS,
    PRIORITY_ORDER,
    SEEDED_NOTE,
    counts_by,
    evidence_ref,
    quote,
)
from docgen.snapshot.transcript import RequirementSeed, TranscriptSnapshot


class RequirementsRenderer(TranscriptDocRenderer):
    key = "requirements"
    title = "Requirements Catalogue"

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.display_title()}",
                       subtitle=self.subtitle(snapshot))

        doc.add(Section("How to read this catalogue").add(
            Paragraph(SEEDED_NOTE),
            Paragraph("Priority is read from the words used in the room — “non-negotiable” and "
                      "“has to” read as Must, “ideally” and “I'd like” as Could — and is shown "
                      "alongside the phrase it was read from. Where nobody signalled a priority, "
                      "the row is Unclassified and needs one."),
        ))

        if not snapshot.requirements:
            doc.add(Section("Requirements").add(
                Callout("warning", "No requirement candidates were detected in this transcript."),
                Paragraph("This usually means the transcript is a status or update meeting rather than "
                          "a requirements session, or that the cue phrases in transcript_cues.yaml need "
                          "tuning for how this client speaks."),
            ))
            return doc

        doc.add(self._summary(snapshot))
        for kind in ("functional", "non_functional", "constraint"):
            rows = [r for r in snapshot.requirements if r.kind == kind]
            if rows:
                doc.add(self._catalogue(kind, rows, ctx))
        doc.add(self._by_area(snapshot, ctx))
        doc.add(self._gaps(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _summary(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Summary")
        by_kind = counts_by(snapshot.requirements, "kind")
        by_priority = counts_by(snapshot.requirements, "priority")

        section.add(Table(
            headers=["Type", *[PRIORITY_LABELS[p] for p in PRIORITY_ORDER], "Total"],
            rows=[
                [KIND_LABELS.get(kind, kind)]
                + [str(sum(1 for r in snapshot.requirements if r.kind == kind and r.priority == p))
                   for p in PRIORITY_ORDER]
                + [str(by_kind.get(kind, 0))]
                for kind in ("functional", "non_functional", "constraint")
                if by_kind.get(kind)
            ] + [
                ["All"] + [str(by_priority.get(p, 0)) for p in PRIORITY_ORDER]
                + [str(len(snapshot.requirements))]
            ],
            caption="Requirement candidates by type and signalled priority.",
        ))

        unclassified = by_priority.get("unclassified", 0)
        if unclassified:
            section.add(Callout(
                "warning",
                f"{unclassified} candidate(s) carry no priority signal. Prioritise them with the "
                "client before the fit-gap.",
            ))

        areas = counts_by(snapshot.requirements, "area")
        if areas:
            section.add(Table(
                headers=["Functional area", "Candidates"],
                rows=[[area or "—", str(count)] for area, count in areas.items()],
            ))
        return section

    def _catalogue(self, kind: str, rows: list[RequirementSeed], ctx: RenderContext) -> Section:
        section = Section(KIND_LABELS.get(kind, kind) + " requirements")
        ordered = sorted(rows, key=lambda r: (PRIORITY_ORDER.index(r.priority), r.id))
        section.add(Table(
            headers=["ID", "Area", "Stated requirement (verbatim)", "Priority",
                     "Priority read from", "Raised by"],
            rows=[[
                r.id,
                r.area or "—",
                quote(r.statement),
                PRIORITY_LABELS.get(r.priority, r.priority),
                r.priority_cue or "— (no signal)",
                evidence_ref(r.evidence),
            ] for r in ordered],
        ))
        formal = Section("Formal statements")
        formal.add(ctx.narrative(
            "requirement_statements",
            {"kind": KIND_LABELS.get(kind, kind),
             "requirements": [{"id": r.id, "area": r.area, "priority": r.priority,
                               "verbatim": r.statement} for r in ordered]},
            hint=f"Rewrite each {KIND_LABELS.get(kind, kind).lower()} candidate above as a numbered, "
                 "testable requirement (“The system shall…”), keeping the ID so it stays traceable "
                 "to the transcript.",
        ))
        section.add(formal)
        return section

    def _by_area(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Notes by functional area")
        areas: list[str] = []
        for requirement in snapshot.requirements:
            if requirement.area and requirement.area not in areas:
                areas.append(requirement.area)
        if not areas:
            section.add(Paragraph("The transcript has no section structure, so requirements could not "
                                  "be grouped by area."))
            return section
        for area in areas:
            in_area = [r for r in snapshot.requirements if r.area == area]
            block = Section(area)
            block.add(Paragraph(
                f"{len(in_area)} candidate(s) · "
                + ", ".join(f"{sum(1 for r in in_area if r.priority == p)} {PRIORITY_LABELS[p].lower()}"
                            for p in PRIORITY_ORDER if any(r.priority == p for r in in_area))
            ))
            block.add(ctx.narrative(
                "requirement_area",
                {"area": area,
                 "requirements": [{"verbatim": r.statement, "priority": r.priority,
                                   "raised_by": r.evidence.speaker_name} for r in in_area]},
                hint=f"Summarise what the client needs in “{area}”, and flag where the statements "
                     "conflict or are too vague to build from.",
            ))
            section.add(block)
        return section

    def _gaps(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Open questions and gaps")
        if snapshot.parked_items:
            section.add(Paragraph("Parked in the session — each blocks or reshapes part of this catalogue:"))
            section.add(Table(
                headers=["ID", "Parked item", "Raised in"],
                rows=[[p.id, p.description, dash(p.evidence.section_title)] for p in snapshot.parked_items],
            ))
        unclassified = [r for r in snapshot.requirements if r.priority == "unclassified"]
        if unclassified:
            section.add(Table(
                headers=["ID", "Needs a priority", "Raised by"],
                rows=[[r.id, quote(r.statement), evidence_ref(r.evidence)] for r in unclassified],
            ))
        section.add(Placeholder(
            hint="Requirements the transcript cannot show: anything nobody raised, areas of the "
                 "business not represented in the room, and requirements inherited from contracts, "
                 "regulation or existing systems."))
        return section
