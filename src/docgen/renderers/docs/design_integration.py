"""Integration Design — pre-build, from a discovery transcript.

After build this is the connector, connection-reference and plug-in inventory.
Before build it is the interface list: every system named in the room, every
requirement that implies data crossing a boundary, and a structured slot per
interface for the design that follows.
"""

from __future__ import annotations

from docgen.renderers.base import RenderContext
from docgen.renderers.docmodel import Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.transcript_common import evidence_ref, quote
from docgen.renderers.docs.transcript_design import (
    DesignDocRenderer,
    requirement_table,
    requirements_matching,
)
from docgen.snapshot.transcript import TranscriptSnapshot


class IntegrationDesignRenderer(DesignDocRenderer):
    key = "integration"
    title = "Integration Design"
    purpose = (
        "Where data crosses a boundary. Every system named in the session becomes a candidate "
        "interface here, with the sentence that named it — because the interfaces nobody "
        "mentioned are the ones that surface late and cost most."
    )

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:
        doc = self.shell(snapshot)
        doc.add(self._inventory(snapshot, ctx))
        doc.add(self._requirements(snapshot))
        doc.add(self._formats(snapshot))
        doc.add(self._per_interface(snapshot))
        doc.add(self._principles(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _inventory(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Candidate interface inventory")
        if not snapshot.external_systems:
            section.add(Callout("warning",
                                "No external systems were named in this session. A solution with "
                                "no interfaces is rare — check whether integration simply was not "
                                "covered rather than concluding there is none."))
            return section

        section.add(Paragraph(
            "Systems, stores and channels named in the session, most-mentioned first. Direction, "
            "mechanism, frequency and volume are design decisions, not transcript facts:"))
        section.add(Table(
            headers=["System", "Mentions", "First mentioned", "Direction", "Mechanism",
                     "Frequency", "In scope?"],
            rows=[[
                system.name,
                str(system.mentions),
                quote(system.evidence.quote),
                "[Consultant]", "[Consultant]", "[Consultant]", "[Consultant]",
            ] for system in snapshot.external_systems],
        ))
        section.add(ctx.narrative(
            "design_integration",
            {"systems": [{"name": s.name, "mentions": s.mentions, "context": s.evidence.quote}
                         for s in snapshot.external_systems],
             "requirements": [r.statement for r in requirements_matching(
                 snapshot, "integrat", "interface", "export", "import", "format", "submit", "feed")]},
            hint="Describe the integration landscape: which systems the solution must talk to, in "
                 "which direction, and which of them are systems of record. Flag any where the "
                 "session gave no detail at all.",
        ))
        return section

    def _requirements(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Integration requirements")
        matched = requirements_matching(
            snapshot, "integrat", "interface", "export", "import", "format", "submit", "feed",
            "portal", "rekey", "barcode", "scan", "instrument", "connect",
        )
        if matched:
            section.add(requirement_table(matched))
        else:
            section.add(Paragraph("No integration requirements were detected in this session."))
        return section

    def _formats(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Data formats and standards")
        formats = requirements_matching(snapshot, "format", "standard format", "data format",
                                        "pdf", "csv", "xml", "json", "schema", "specification")
        if formats:
            section.add(Paragraph("Statements about the shape of exchanged data. Each named format "
                                  "needs an example file and a specification before design:"))
            section.add(requirement_table(formats))
        else:
            section.add(Paragraph("No data formats were named in this session."))
        section.add(Placeholder(
            hint="Per format: owner, specification or example file, version, validation rules, and "
                 "what happens when a message fails validation."))
        return section

    def _per_interface(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Interface designs")
        if not snapshot.external_systems:
            section.add(Paragraph("No interfaces to design from this session."))
            return section
        section.add(Paragraph(
            "One block per interface confirmed as in scope. Delete the ones that turn out not to "
            "be interfaces at all — the inventory above is a list of things people mentioned, not "
            "a list of things that must be built."))
        for system in snapshot.external_systems[:12]:
            block = Section(system.name)
            block.add(Table(
                headers=["Property", "Value"],
                rows=[
                    ["Mentioned in session", f"{system.mentions} time(s), "
                                             f"{evidence_ref(system.evidence)}"],
                    ["Purpose", "[Consultant]"],
                    ["Direction", "[Consultant]"],
                    ["Mechanism", "[Consultant]"],
                    ["Trigger / frequency", "[Consultant]"],
                    ["Volume", "[Consultant]"],
                    ["Error handling", "[Consultant]"],
                    ["Owner (client side)", "[Consultant]"],
                ],
            ))
            section.add(block)
        return section

    def _principles(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Integration principles and constraints")
        constraints = [f for f in snapshot.findings if f.category == "constraint"]
        dependencies = [f for f in snapshot.findings if f.category == "dependency"]
        if constraints or dependencies:
            section.add(Table(
                headers=["Ref", "Statement (verbatim)", "Stated by", "Type"],
                rows=[[f.id, quote(f.statement), evidence_ref(f.evidence), f.category.title()]
                      for f in constraints + dependencies],
            ))
        else:
            section.add(Paragraph("No integration constraints were stated in this session."))
        section.add(Placeholder(
            hint="Agree the principles before designing individual interfaces: system of record "
                 "per data type, synchronous versus batch, retry and failure handling, and who "
                 "owns each interface once live."))
        return section
