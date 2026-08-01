"""High-Level Design — pre-build, from a discovery transcript.

The as-built HLD (renderers/docs/hld.py) describes a solution that exists. This
one describes the solution that was agreed to: drivers, scope, capability areas
and constraints, every line of it traceable to something somebody said.
"""

from __future__ import annotations

from docgen.renderers.base import RenderContext
from docgen.renderers.docmodel import Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.transcript_common import PRIORITY_LABELS, evidence_ref, quote
from docgen.renderers.docs.transcript_design import (
    DesignDocRenderer,
    requirement_table,
    requirements_matching,
    statement_table,
)
from docgen.snapshot.transcript import TranscriptSnapshot


class HldDesignRenderer(DesignDocRenderer):
    key = "hld"
    title = "High-Level Design"
    purpose = (
        "The shape of the proposed solution: why it is being done, what is in and out of scope, "
        "the capability areas it must cover, and the constraints it has to live within."
    )

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:
        doc = self.shell(snapshot)
        doc.add(self._context(snapshot, ctx))
        doc.add(self._objectives(snapshot))
        doc.add(self._scope(snapshot, ctx))
        doc.add(self._capabilities(snapshot, ctx))
        doc.add(self._architecture(snapshot, ctx))
        doc.add(self._constraints(snapshot))
        doc.add(self._phasing(snapshot))
        doc.add(self._open(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _context(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Business context and drivers")
        drivers = [f for f in snapshot.findings if f.category == "issue"]
        section.add(ctx.narrative(
            "design_context",
            {
                "meeting": snapshot.meeting.model_dump(mode="json"),
                "drivers": [{"statement": f.statement, "said_by": f.evidence.speaker_name}
                            for f in drivers[:25]],
                "areas": snapshot.requirement_areas(),
            },
            hint="Two or three paragraphs on the client's business, why they are changing now, "
                 "and what it is costing them not to.",
        ))
        if drivers:
            section.add(Section("Current-state pain, as stated in the session").add(Table(
                headers=["Ref", "Stated problem (verbatim)", "Said by", "Section"],
                rows=[[f.id, quote(f.statement), evidence_ref(f.evidence),
                       f.evidence.section_title or "—"] for f in drivers],
                caption="These are the drivers the business case has to answer.",
            )))
        return section

    def _objectives(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Objectives and success measures")
        # Deliberately narrow: "per cent" on its own catches every statistic in the
        # session, and an availability figure is a service level, not an objective.
        measures = requirements_matching(
            snapshot, "measure", "target", "conversion", "on-time", "success",
            "reduction in", "increase in", "down to", "board approved",
        )
        if measures:
            section.add(requirement_table(measures))
        else:
            section.add(Paragraph("No numeric success measures were stated in this session."))
        section.add(Placeholder(
            hint="Restate these as the measures the programme will be judged on: baseline, target, "
                 "owner and the date each is measured. Anything without a baseline is not a measure."))
        return section

    def _scope(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Scope")
        areas = snapshot.requirement_areas()
        if areas:
            rows = []
            for area in areas:
                in_area = [r for r in snapshot.requirements if r.area == area]
                musts = sum(1 for r in in_area if r.priority == "must")
                rows.append([area, str(len(in_area)), str(musts),
                             ", ".join(sorted({r.kind.replace("_", "-") for r in in_area}))])
            section.add(Section("In scope — capability areas raised").add(Table(
                headers=["Capability area", "Requirements", "of which Must", "Types"], rows=rows,
                caption="Derived from the sections of the workshop in which requirements were raised.",
            )))
        out_of_scope = snapshot.statements_in("scope_out")
        constraints = [r for r in snapshot.requirements if r.kind == "constraint"]
        exclusions = Section("Out of scope and deferred")
        if out_of_scope:
            exclusions.add(statement_table(out_of_scope))
        if constraints:
            exclusions.add(requirement_table(constraints))
        if not out_of_scope and not constraints:
            exclusions.add(Callout("warning", "Nothing was explicitly excluded in this session. "
                                              "An unbounded scope is a commercial risk — agree "
                                              "exclusions before the estimate."))
        exclusions.add(Placeholder(hint="Confirm the exclusion list with the sponsor and state, for "
                                        "each item, whether it is out of scope permanently or deferred "
                                        "to a later phase."))
        section.add(exclusions)
        section.add(ctx.narrative(
            "design_scope",
            {"areas": areas,
             "out_of_scope": [s.statement for s in out_of_scope],
             "constraints": [r.statement for r in constraints]},
            hint="Summarise the scope boundary in prose: what the solution covers, what it "
                 "deliberately does not, and where the boundary is still soft.",
        ))
        return section

    def _capabilities(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Capability areas")
        areas = snapshot.requirement_areas()
        if not areas:
            section.add(Paragraph("No capability areas could be derived: the transcript has no "
                                  "section structure and no requirements were detected."))
            return section
        for area in areas:
            in_area = [r for r in snapshot.requirements if r.area == area]
            block = Section(area)
            counts = ", ".join(
                f"{sum(1 for r in in_area if r.priority == p)} {PRIORITY_LABELS[p].lower()}"
                for p in ("must", "should", "could", "wont", "unclassified")
                if any(r.priority == p for r in in_area)
            )
            block.add(Paragraph(f"{len(in_area)} requirement(s) — {counts}"))
            block.add(ctx.narrative(
                "design_capability",
                {"area": area,
                 "requirements": [{"id": r.id, "verbatim": r.statement, "priority": r.priority}
                                  for r in in_area]},
                hint=f"Describe the capability the solution needs in “{area}” and how it hangs "
                     "together as a process. Do not name products or tables.",
            ))
            block.add(requirement_table(in_area, area_column=False))
            section.add(block)
        return section

    def _architecture(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Proposed solution architecture")
        systems = snapshot.external_systems
        if systems:
            section.add(Section("Systems and stores named in the session").add(Table(
                headers=["Named", "Mentions", "First mentioned"],
                rows=[[s.name, str(s.mentions), quote(s.evidence.quote)] for s in systems[:20]],
                caption="Candidate integration points — see the Integration Design document.",
            )))
        section.add(ctx.narrative(
            "design_architecture",
            {"systems": [s.name for s in systems],
             "non_functional": [r.statement for r in snapshot.requirements_of("non_functional")]},
            hint="Describe the proposed architecture at a conceptual level: the components, where "
                 "data lives, how the parts communicate, and which non-functional requirements "
                 "drive those choices.",
        ))
        section.add(Section("Architecture decisions").add(Placeholder(
            hint="One row per significant decision: the decision, the options considered, why this "
                 "one, and what it costs. Platform choice, hosting, offline strategy, "
                 "integration pattern and reporting approach at minimum.")))
        return section

    def _constraints(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Design constraints")
        constraints = [f for f in snapshot.findings if f.category == "constraint"]
        musts = [r for r in snapshot.requirements_of("non_functional") if r.priority == "must"]
        if constraints:
            section.add(Table(
                headers=["Ref", "Constraint (verbatim)", "Stated by", "Section"],
                rows=[[f.id, quote(f.statement), evidence_ref(f.evidence),
                       f.evidence.section_title or "—"] for f in constraints],
            ))
        if musts:
            section.add(Section("Non-negotiable non-functional requirements").add(
                requirement_table(musts)))
        if not constraints and not musts:
            section.add(Paragraph("No hard constraints were stated in this session."))
        return section

    def _phasing(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Phasing and release strategy")
        phasing = requirements_matching(snapshot, "phase", "first", "day one", "by march",
                                        "financial year", "roadmap", "live")
        if phasing:
            section.add(requirement_table(phasing))
        else:
            section.add(Paragraph("Phasing was not discussed in this session."))
        section.add(Placeholder(
            hint="Set out the phases: what goes live when, to which sites and users, and what each "
                 "phase must prove before the next starts."))
        return section

    def _open(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Open decisions")
        if snapshot.parked_items:
            section.add(Table(
                headers=["ID", "Open decision", "Raised in", "Needed by"],
                rows=[[p.id, p.description, p.evidence.section_title or "—", "[Consultant]"]
                      for p in snapshot.parked_items],
            ))
            section.add(Paragraph("Each of these changes the design if it resolves the other way. "
                                  "None of them should still be open at build start."))
        else:
            section.add(Paragraph("Nothing was left open in this session."))
        return section
