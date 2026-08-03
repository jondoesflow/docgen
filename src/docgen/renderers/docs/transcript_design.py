"""Shared scaffolding for the pre-build design documents.

The same document keys — `hld`, `lld`, `data-dictionary`, `security`,
`deployment`, `licensing`, `integration`, `rraid`, `hygiene` — are produced
from a transcript *before* the build and from the solution export *after* it.
Same key, same Word template, two points in the document's life:

    workshop transcript ─▶ design intent   ("what we agreed to build")
    solution export     ─▶ as-built        ("what actually got built")

Regenerating from the export later is what proves the two still agree.

The honesty contract is unchanged and matters more here, because a discovery
transcript contains no schema at all. So the design documents:

* state deterministically only what somebody actually said, quoted, attributed
  and line-referenced;
* present derived material (candidate objects, named systems) as **counts of
  what was said**, never as decisions — "the client said 'sample' 30 times" is
  an observation, "there is a Sample table" would be an invention;
* leave every real design decision as a `[Consultant to complete]` placeholder
  or an explicitly *proposed* LLM draft.
"""

from __future__ import annotations

from docgen.renderers.base import TranscriptDocRenderer
from docgen.renderers.docmodel import Document, Paragraph, Section, Table
from docgen.renderers.docs.transcript_common import (
    PRIORITY_LABELS,
    PRIORITY_ORDER,
    evidence_ref,
    quote,
)
from docgen.snapshot.transcript import LabelledStatement, RequirementSeed, TranscriptSnapshot

DESIGN_STAGE_NOTE = (
    "This is the pre-build version of this document: design intent captured from a discovery "
    "session, not a record of a built system. Every deterministic row quotes the sentence it "
    "came from, who said it and the line it is on. Sections marked "
    "[Consultant to complete] are design decisions that no transcript can make."
)

REGENERATE_NOTE = (
    "Once the solution exists, run docgen against the exported solution zip with the same "
    "document key. That produces the as-built version of this document from the actual "
    "metadata — and the difference between the two is the difference between what was "
    "agreed and what was delivered."
)


class DesignDocRenderer(TranscriptDocRenderer):
    """A transcript renderer whose solution counterpart shares its document key."""

    #: Copy for the standing header on every design document.
    purpose: str = ""

    def shell(self, snapshot: TranscriptSnapshot) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.display_title()}",
                       subtitle=self.subtitle(snapshot))
        header = Section("About this document")
        if self.purpose:
            header.add(Paragraph(self.purpose))
        header.add(Paragraph(DESIGN_STAGE_NOTE), Paragraph(REGENERATE_NOTE))
        doc.add(header)
        return doc

    def subtitle(self, snapshot: TranscriptSnapshot) -> str:
        meeting = snapshot.meeting
        parts = [meeting.client_organisation, meeting.date]
        facts = " · ".join(p for p in parts if p)
        lead = f"{facts} — " if facts else ""
        return f"{lead}design intent, drafted by docgen from {snapshot.source_file}"


# ---------------------------------------------------------------------------
# Shared table builders
# ---------------------------------------------------------------------------


def requirement_table(requirements: list[RequirementSeed], *, area_column: bool = True) -> Table:
    headers = ["ID"] + (["Area"] if area_column else []) + ["Requirement (verbatim)", "Priority", "Raised by"]
    rows = []
    for requirement in sorted(requirements, key=lambda r: (PRIORITY_ORDER.index(r.priority), r.id)):
        row = [requirement.id]
        if area_column:
            row.append(requirement.area or "—")
        row += [
            quote(requirement.statement),
            PRIORITY_LABELS.get(requirement.priority, requirement.priority),
            evidence_ref(requirement.evidence),
        ]
        rows.append(row)
    return Table(headers=headers, rows=rows)


def statement_table(statements: list[LabelledStatement]) -> Table:
    return Table(
        headers=["Ref", "Stated in the session", "Said by", "Section"],
        rows=[[s.id, quote(s.statement), evidence_ref(s.evidence), s.evidence.section_title or "—"]
              for s in statements],
    )


def requirements_matching(snapshot: TranscriptSnapshot, *patterns: str) -> list[RequirementSeed]:
    """Requirements whose text or area mentions any of these terms."""
    lowered = [p.lower() for p in patterns]
    matched = []
    for requirement in snapshot.requirements:
        haystack = f"{requirement.statement} {requirement.area}".lower()
        if any(term in haystack for term in lowered):
            matched.append(requirement)
    return matched
