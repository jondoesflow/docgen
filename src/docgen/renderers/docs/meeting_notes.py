"""Meeting Notes — structured minutes rebuilt from the transcript snapshot.

Everything factual (who attended, what was covered, who said what, what was
agreed, what was actioned, what was parked) is deterministic. The summaries are
the only judgement calls, and they are drafted by the LLM tier or left as
`[Consultant to complete]` placeholders. Re-transcribe, re-parse, re-render and
the notes are true again.
"""

from __future__ import annotations

from docgen.renderers.base import RenderContext, TranscriptDocRenderer
from docgen.renderers.docmodel import BulletList, Callout, Document, Paragraph, Section, Table
from docgen.renderers.docs.common import dash
from docgen.renderers.docs.transcript_common import (
    CATEGORY_LABELS,
    attendee_rows,
    discussion_sections,
    evidence_ref,
    meeting_facts,
    quote,
    section_speakers,
    utterances_in,
)
from docgen.snapshot.transcript import TranscriptSnapshot

# How many verbatim exchanges to reproduce per section. The full transcript is
# the source of record; the notes carry the load-bearing quotes, not all of them.
MAX_QUOTES_PER_SECTION = 6


class MeetingNotesRenderer(TranscriptDocRenderer):
    key = "meeting-notes"
    title = "Meeting Notes"

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.display_title()}",
                       subtitle=self.subtitle(snapshot))

        doc.add(Section("Meeting details").add(
            Table(headers=["Property", "Value"], rows=meeting_facts(snapshot))))

        doc.add(Section("Attendees").add(
            Table(
                headers=["Name", "Ref", "Role", "Organisation", "Side", "Attendance", "Contribution"],
                rows=attendee_rows(snapshot),
            ),
            Paragraph("Contribution is a share of words spoken — a coverage indicator for the "
                      "session, not a measure of value."),
        ))

        if snapshot.agenda:
            doc.add(Section("Agenda").add(Table(
                headers=["#", "Item", "Scheduled"],
                rows=[[item.number, item.title, dash(item.scheduled)] for item in snapshot.agenda],
            )))

        doc.add(self._summary(snapshot, ctx))
        doc.add(self._discussion(snapshot, ctx))
        doc.add(self._decisions(snapshot))
        doc.add(self._actions(snapshot))
        doc.add(self._parked(snapshot))
        doc.add(self._quality(snapshot))
        return doc

    # -- sections ------------------------------------------------------------

    def _summary(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        section = Section("Summary")
        stats = snapshot.stats
        section.add(Table(headers=["Extracted from this session", "Count"], rows=[
            ["Sections discussed", str(len(discussion_sections(snapshot)))],
            ["Speaking participants", str(stats.speaker_count)],
            ["Turns captured", str(stats.utterance_count)],
            ["Words captured", f"{stats.word_count:,}"],
            ["Requirement candidates", str(len(snapshot.requirements))],
            ["Decisions noted", str(len(snapshot.decisions))],
            ["Actions", str(len(snapshot.actions))],
            ["Parked items", str(len(snapshot.parked_items))],
            ["Risks / issues / dependencies seeded", str(len(snapshot.findings))],
        ]))
        section.add(ctx.narrative(
            "meeting_summary",
            {
                "meeting": snapshot.meeting.model_dump(mode="json"),
                "participants": [{"name": p.name, "role": p.role, "organisation": p.organisation}
                                 for p in snapshot.participants],
                "sections": [{"id": s.id, "title": s.title} for s in discussion_sections(snapshot)],
                "requirements": [{"statement": r.statement, "area": r.area, "priority": r.priority}
                                 for r in snapshot.requirements[:40]],
                "decisions": [d.statement for d in snapshot.decisions[:20]],
            },
            hint="Two or three paragraphs: why the session was held, what ground it covered, and the "
                 "two or three things that most change the shape of the engagement.",
        ))
        return section

    def _discussion(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Section:
        discussion = Section("Discussion")
        sections = discussion_sections(snapshot)
        if not sections:
            discussion.add(Paragraph("No dialogue was recognised in the transcript."))
            return discussion

        for source in sections:
            block = Section(f"{source.id}. {source.title}" if not source.id.startswith("s") else source.title)
            turns = utterances_in(snapshot, source)
            facts = " · ".join(filter(None, [
                f"Starts {source.start_timestamp}" if source.start_timestamp else None,
                f"{len(turns)} turn(s)",
                f"Speakers: {', '.join(section_speakers(snapshot, source))}" if turns else None,
            ]))
            block.add(Paragraph(facts))
            block.add(ctx.narrative(
                "section_summary",
                {
                    "section": source.title,
                    "turns": [{"speaker": t.speaker_name or t.speaker_key, "text": t.text} for t in turns],
                },
                hint=f"Summarise what was established in “{source.title}”: the points made, the "
                     "positions taken and anything left open.",
            ))

            in_section = [r for r in snapshot.requirements if r.evidence.section_id == source.id]
            if in_section:
                block.add(Section("Points raised (verbatim)").add(Table(
                    headers=["Raised by", "Point"],
                    rows=[[r.evidence.speaker_name or r.evidence.speaker_key or "—", quote(r.statement)]
                          for r in in_section[:MAX_QUOTES_PER_SECTION]],
                    caption=(f"{len(in_section)} point(s) extracted from this section; "
                             f"showing the first {min(len(in_section), MAX_QUOTES_PER_SECTION)}. "
                             "The full set is in the Requirements Catalogue."),
                )))
            discussion.add(block)
        return discussion

    def _decisions(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Decisions")
        if not snapshot.decisions:
            section.add(Paragraph("No decisions were detected in the transcript. Confirm with the "
                                  "facilitator whether anything was agreed verbally."))
            return section
        section.add(Table(
            headers=["ID", "Decision (verbatim)", "Stated by", "Section"],
            rows=[[d.id, quote(d.statement), evidence_ref(d.evidence), dash(d.evidence.section_title)]
                  for d in snapshot.decisions],
        ))
        section.add(Paragraph("These are statements that read as decisions in the transcript. "
                              "Confirm each one before treating it as agreed."))
        return section

    def _actions(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Actions")
        if not snapshot.actions:
            section.add(Paragraph("No actions were recorded in the transcript."))
            return section
        section.add(Table(
            headers=["ID", "Owner", "Action", "Due", "Source"],
            rows=[[a.id, a.owner_name or a.owner_key or "—", a.description, dash(a.due),
                   "Action register" if a.source == "register" else "In-session marker"]
                  for a in snapshot.actions],
        ))
        section.add(Paragraph("The full register, including owners with no named due date, is in the "
                              "Actions & Decisions Register."))
        return section

    def _parked(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Parked items")
        if not snapshot.parked_items:
            section.add(Paragraph("Nothing was parked in this session."))
            return section
        section.add(Table(
            headers=["ID", "Parked item", "Raised in"],
            rows=[[p.id, p.description, dash(p.evidence.section_title)] for p in snapshot.parked_items],
        ))
        return section

    def _quality(self, snapshot: TranscriptSnapshot) -> Section:
        """What the transcript could not tell us — stated, never hidden."""
        section = Section("Transcript quality and coverage")
        stats = snapshot.stats
        notes = [
            f"{stats.lines_read:,} line(s) read from {snapshot.source_file}.",
            f"{stats.utterance_count} turn(s) attributed to {stats.speaker_count} speaker(s).",
        ]
        if stats.unattributed_utterances:
            notes.append(f"{stats.unattributed_utterances} passage(s) could not be attributed to a speaker.")
        if stats.inaudible_markers:
            notes.append(f"{stats.inaudible_markers} [inaudible] marker(s) — content is missing at those points.")
        if stats.crosstalk_markers:
            notes.append(f"{stats.crosstalk_markers} [crosstalk] marker(s) — attribution there is unreliable.")
        if stats.lines_unrecognised:
            notes.append(f"{stats.lines_unrecognised} line(s) matched no known construct and contributed "
                         "nothing to these notes.")
        by_category: dict[str, int] = {}
        for finding in snapshot.findings:
            by_category[finding.category] = by_category.get(finding.category, 0) + 1
        if by_category:
            notes.append("RRAID seeds by category: " + ", ".join(
                f"{by_category[c]} {CATEGORY_LABELS.get(c, c).lower()}" for c in sorted(by_category)))
        section.add(BulletList(notes))

        if snapshot.warnings:
            section.add(Callout("warning", f"{len(snapshot.warnings)} parse warning(s) — see below."))
            section.add(Table(
                headers=["Code", "Context", "Warning"],
                rows=[[w.code, dash(w.context), w.message] for w in snapshot.warnings],
            ))
        else:
            section.add(Paragraph("No parse warnings: every line of the transcript was recognised."))
        return section
