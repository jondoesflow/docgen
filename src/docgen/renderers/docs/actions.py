"""Actions & Decisions Register — the follow-up document from a session.

Entirely deterministic: actions and parked items come from the transcript's own
registers and `[ACTION:]` / `[PARKED:]` markers, decisions from statements that
read as decisions. Nothing here needs the LLM tier, so this document is
complete offline and can be circulated the moment the transcript lands.
"""

from __future__ import annotations

from docgen.renderers.base import RenderContext, TranscriptDocRenderer
from docgen.renderers.docmodel import Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.common import dash
from docgen.renderers.docs.transcript_common import evidence_ref, quote
from docgen.snapshot.transcript import TranscriptSnapshot

SOURCE_LABELS = {
    "register": "Action register",
    "inline_marker": "Raised in session",
}


class ActionsRenderer(TranscriptDocRenderer):
    key = "actions"
    title = "Actions & Decisions Register"

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:  # noqa: ARG002
        doc = Document(title=f"{self.title} — {snapshot.display_title()}",
                       subtitle=self.subtitle(snapshot))

        doc.add(Section("Scope of this register").add(Paragraph(
            "Every row is taken directly from the transcript and cites the line it came from. "
            "Owners, dates and wording should be confirmed with the people named before this is "
            "circulated as the record of the session."
        )))

        doc.add(self._actions(snapshot))
        doc.add(self._by_owner(snapshot))
        doc.add(self._decisions(snapshot))
        doc.add(self._parked(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _actions(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Actions")
        if not snapshot.actions:
            section.add(Paragraph("No actions were recorded in this transcript."))
            section.add(Placeholder(hint="Add any actions agreed verbally that the transcript did not capture."))
            return section

        undated = [a for a in snapshot.actions if not a.due]
        unowned = [a for a in snapshot.actions if not (a.owner_key or a.owner_name)]
        if undated:
            section.add(Callout("warning", f"{len(undated)} action(s) have no due date."))
        if unowned:
            section.add(Callout("warning", f"{len(unowned)} action(s) have no identified owner."))

        section.add(Table(
            headers=["ID", "Owner", "Action", "Due", "Source", "Evidence"],
            rows=[[
                a.id,
                a.owner_name or a.owner_key or "⚠ Unassigned",
                a.description,
                a.due or "⚠ No date",
                SOURCE_LABELS.get(a.source, a.source),
                f"line {a.evidence.line}" if a.evidence.line else "—",
            ] for a in snapshot.actions],
        ))
        return section

    def _by_owner(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Actions by owner")
        if not snapshot.actions:
            section.add(Paragraph("No actions to distribute."))
            return section
        owners: dict[str, list] = {}
        for action in snapshot.actions:
            label = action.owner_name or action.owner_key or "Unassigned"
            owners.setdefault(label, []).append(action)
        section.add(Table(
            headers=["Owner", "Actions", "Earliest due", "IDs"],
            rows=[[
                owner,
                str(len(items)),
                next((a.due for a in items if a.due), "—"),
                ", ".join(a.id for a in items),
            ] for owner, items in owners.items()],
        ))
        return section

    def _decisions(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Decisions")
        if not snapshot.decisions:
            section.add(Paragraph("No decisions were detected in the transcript."))
            section.add(Placeholder(hint="Record anything agreed in the room that the transcript does "
                                         "not state explicitly."))
            return section
        section.add(Table(
            headers=["ID", "Decision (verbatim)", "Stated by", "Section", "Confirmed?"],
            rows=[[d.id, quote(d.statement), evidence_ref(d.evidence),
                   dash(d.evidence.section_title), "[Consultant]"]
                  for d in snapshot.decisions],
        ))
        section.add(Paragraph("Each row is a statement that reads as a decision. Mark it confirmed "
                              "only once the person named has agreed the wording."))
        return section

    def _parked(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Parked items and open decisions")
        if not snapshot.parked_items:
            section.add(Paragraph("Nothing was parked in this session."))
            return section
        section.add(Table(
            headers=["ID", "Parked item", "Raised in", "Evidence", "Owner", "Resolve by"],
            rows=[[p.id, p.description, dash(p.evidence.section_title),
                   f"line {p.evidence.line}" if p.evidence.line else "—",
                   "[Consultant]", "[Consultant]"]
                  for p in snapshot.parked_items],
        ))
        section.add(Paragraph("Parked items are unresolved by definition: each one needs an owner and "
                              "a date by which it must be closed, or it will resurface as a change "
                              "request later."))
        return section
