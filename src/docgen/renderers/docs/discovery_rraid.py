"""RRAID Log — pre-build, from a discovery transcript.

Risks, assumptions, issues, dependencies and constraints seeded from what was
actually said in the session. Same document key as the solution RRAID log, so
the same Word template styles both and the log carries forward from discovery
into delivery.

Seeds are detected deterministically and always state their evidence (the
verbatim sentence, the speaker and the line), while impact, likelihood, owner
and mitigation stay with the consultant. Parked items and undated actions are
carried as open items in their own right — an unresolved decision is a delivery
risk whether or not anybody called it one.
"""

from __future__ import annotations

from docgen.renderers.base import RenderContext
from docgen.renderers.docmodel import Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.common import dash
from docgen.renderers.docs.transcript_common import SEEDED_NOTE, evidence_ref, quote
from docgen.renderers.docs.transcript_design import DesignDocRenderer
from docgen.snapshot.transcript import DiscoveryFinding, TranscriptSnapshot

# (category, heading, seeded column header, judgement columns, empty-state line)
CATEGORY_LAYOUT = (
    ("risk", "Risks", "Risk (seeded)", ["Impact", "Likelihood", "Mitigation", "Owner"],
     "No risks were detected in the transcript. That is a finding in itself for a discovery "
     "session — check whether risk was discussed at all."),
    ("assumption", "Assumptions", "Assumption (seeded)", ["Validated?", "Owner"],
     "No assumptions were detected in the transcript."),
    ("issue", "Issues", "Issue (seeded)", ["Impact", "Resolution", "Owner"],
     "No current-state issues were detected in the transcript."),
    ("dependency", "Dependencies", "Dependency (seeded)", ["Depends on", "Needed by", "Owner"],
     "No dependencies were detected in the transcript."),
    ("constraint", "Constraints", "Constraint (seeded)", ["Type", "Confirmed?"],
     "No constraints were detected in the transcript."),
)


class DiscoveryRraidRenderer(DesignDocRenderer):
    key = "rraid"
    title = "RRAID Log"
    purpose = (
        "Risks, assumptions, issues, dependencies and constraints raised in the session. This log "
        "carries forward into delivery — after build the same document key is regenerated from "
        "solution metadata, and entries that were open at discovery should be closed by then."
    )

    def _seed_summary(self, ctx: RenderContext, finding: DiscoveryFinding) -> str:
        prose = ctx.narrative_provider("discovery_seed", {
            "category": finding.category,
            "statement": finding.statement,
            "said_by": finding.evidence.speaker_name,
            "section": finding.evidence.section_title,
        })
        return prose or quote(finding.statement)

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:
        doc = self.shell(snapshot)

        doc.add(Section("How to read this log").add(
            Paragraph(SEEDED_NOTE),
            Paragraph("Impact, likelihood, mitigation and ownership are deliberately empty: a "
                      "transcript can show that somebody raised a concern, but not how serious it is "
                      "or who should carry it. The sections marked for human judgement exist because "
                      "the most serious risks on an engagement are usually the ones nobody said out "
                      "loud in the workshop."),
        ))

        for category, heading, seed_header, judgement, empty in CATEGORY_LAYOUT:
            doc.add(self._category(snapshot, ctx, category, heading, seed_header, judgement, empty))

        doc.add(self._from_registers(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _category(
        self,
        snapshot: TranscriptSnapshot,
        ctx: RenderContext,
        category: str,
        heading: str,
        seed_header: str,
        judgement: list[str],
        empty: str,
    ) -> Section:
        section = Section(heading)
        seeds = [f for f in snapshot.findings if f.category == category]
        if seeds:
            section.add(Callout("risk" if category == "risk" else "info",
                                f"{len(seeds)} {heading.lower().rstrip('s')}(s) seeded from the transcript."))
            section.add(Table(
                headers=["ID", seed_header, "Raised by", "Section", *judgement],
                rows=[[
                    seed.id,
                    self._seed_summary(ctx, seed),
                    evidence_ref(seed.evidence),
                    dash(seed.evidence.section_title),
                    *["[Consultant]" for _ in judgement],
                ] for seed in seeds],
            ))
        else:
            section.add(Paragraph(empty))
        section.add(Section(f"Additional {heading.lower()} (human judgement)").add(Placeholder(
            hint=f"{heading} that nobody raised in the session: commercial, contractual, resourcing, "
                 "regulatory and delivery factors a transcript cannot see.")))
        return section

    def _from_registers(self, snapshot: TranscriptSnapshot) -> Section:
        """Parked items and undated actions are open questions with a delivery cost."""
        section = Section("Open items carried from the session")
        rows: list[list[str]] = []
        for item in snapshot.parked_items:
            rows.append([item.id, "Parked item", item.description,
                         dash(item.evidence.section_title), "[Consultant]", "[Consultant]"])
        for action in snapshot.actions:
            if action.due:
                continue
            rows.append([action.id, "Action with no date", action.description,
                         dash(action.evidence.section_title), action.owner_name or "⚠ Unassigned",
                         "[Consultant]"])
        for action in snapshot.actions:
            if action.owner_key or action.owner_name:
                continue
            rows.append([action.id, "Action with no owner", action.description,
                         dash(action.evidence.section_title), "⚠ Unassigned", "[Consultant]"])

        if not rows:
            section.add(Paragraph("Every action has an owner and a date, and nothing was parked."))
            return section
        section.add(Table(
            headers=["Ref", "Type", "Open item", "Raised in", "Owner", "Impact if unresolved"],
            rows=rows,
        ))
        section.add(Paragraph("Each of these is an unresolved decision. Left open, they become "
                              "assumptions by default — and assumptions become change requests."))
        return section
