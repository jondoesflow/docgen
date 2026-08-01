"""Discovery Hygiene Report — pre-build, from a discovery transcript.

The solution hygiene report asks "is this build clean?". Its pre-build
counterpart asks the same question of the discovery itself: is this good enough
to design and estimate from? Gaps are reported as findings with the same rule
id / severity / evidence shape, so both versions read alike.
"""

from __future__ import annotations

from dataclasses import dataclass

from docgen.renderers.base import RenderContext
from docgen.renderers.docmodel import BulletList, Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.renderers.docs.common import dash
from docgen.renderers.docs.transcript_design import DesignDocRenderer
from docgen.snapshot.transcript import TranscriptSnapshot

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

# Themes a discovery should have covered. Missing ones are reported as gaps —
# a question nobody asked is the cheapest defect there is to fix.
EXPECTED_COVERAGE = (
    ("DISC-101", "user_population", "User populations and volumes"),
    ("DISC-102", "access_control", "Access control and confidentiality"),
    ("DISC-103", "availability", "Availability, performance and recovery"),
    ("DISC-104", "retention", "Retention, audit and record-keeping"),
    ("DISC-105", "data_migration", "Data migration"),
    ("DISC-106", "environment", "Environments, sites and infrastructure"),
    ("DISC-107", "support_model", "Support, training and change"),
    ("DISC-108", "scope_out", "Explicit exclusions"),
)


@dataclass
class DiscoveryFindingRow:
    rule_id: str
    severity: str
    category: str
    subject: str
    message: str
    evidence: str


class HygieneDesignRenderer(DesignDocRenderer):
    key = "hygiene"
    title = "Discovery Hygiene Report"
    purpose = (
        "Whether this discovery is solid enough to design and estimate from. Every finding is a "
        "gap in the material, not a fault in the client — and each one is cheaper to close now "
        "than after a number has been committed to."
    )

    def build(self, snapshot: TranscriptSnapshot, ctx: RenderContext) -> Document:  # noqa: ARG002
        doc = self.shell(snapshot)
        findings = self._findings(snapshot)

        summary = Section("Summary")
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        if findings:
            breakdown = ", ".join(f"{counts[s]} {s}"
                                  for s in sorted(counts, key=lambda s: SEVERITY_ORDER.get(s, 9)))
            summary.add(Callout("warning", f"{len(findings)} finding(s): {breakdown}."))
        else:
            summary.add(Callout("info", "No findings. This discovery covers every theme docgen "
                                        "checks for, and every action has an owner and a date."))
        summary.add(Table(headers=["Measure", "Value"], rows=[
            ["Turns captured", str(snapshot.stats.utterance_count)],
            ["Words captured", f"{snapshot.stats.word_count:,}"],
            ["Speakers", str(snapshot.stats.speaker_count)],
            ["Sections with dialogue",
             str(sum(1 for s in snapshot.sections if s.utterance_indexes))],
            ["Requirement candidates", str(len(snapshot.requirements))],
            ["of which Must", str(sum(1 for r in snapshot.requirements if r.priority == "must"))],
            ["of which unprioritised",
             str(sum(1 for r in snapshot.requirements if r.priority == "unclassified"))],
            ["Decisions", str(len(snapshot.decisions))],
            ["Actions", str(len(snapshot.actions))],
            ["Parked items", str(len(snapshot.parked_items))],
            ["Business terms detected", str(len(snapshot.candidate_objects))],
            ["External systems named", str(len(snapshot.external_systems))],
        ]))
        doc.add(summary)

        detail = Section("Findings")
        if findings:
            detail.add(Table(
                headers=["Rule", "Severity", "Area", "Subject", "Finding", "Evidence"],
                rows=[[f.rule_id, f.severity, f.category, f.subject, f.message, f.evidence]
                      for f in sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9),
                                                               f.rule_id))],
            ))
        else:
            detail.add(Paragraph("Nothing to report."))
        doc.add(detail)

        doc.add(self._quality(snapshot))
        doc.add(Section("Before the estimate goes out").add(Placeholder(
            hint="Close the error-severity findings above, or state explicitly in the proposal "
                 "which assumptions the number rests on because they were not closed.")))
        return doc

    # -- findings ------------------------------------------------------------

    def _findings(self, snapshot: TranscriptSnapshot) -> list[DiscoveryFindingRow]:
        findings: list[DiscoveryFindingRow] = []

        # coverage gaps
        for rule_id, category, label in EXPECTED_COVERAGE:
            if not snapshot.statements_in(category):
                findings.append(DiscoveryFindingRow(
                    rule_id, "warning", "coverage", label,
                    "Nothing was said about this. Confirm it was genuinely out of scope for the "
                    "session rather than missed.",
                    f"no statement matched the “{label}” cue group in transcript_cues.yaml",
                ))

        # prioritisation
        unprioritised = [r for r in snapshot.requirements if r.priority == "unclassified"]
        if unprioritised:
            findings.append(DiscoveryFindingRow(
                "DISC-201", "warning", "requirements", f"{len(unprioritised)} requirement(s)",
                "No priority was signalled, so these cannot be sequenced or traded.",
                ", ".join(r.id for r in unprioritised[:12]),
            ))
        for area in snapshot.requirement_areas():
            in_area = [r for r in snapshot.requirements if r.area == area]
            if not any(r.priority == "must" for r in in_area):
                findings.append(DiscoveryFindingRow(
                    "DISC-202", "info", "requirements", area,
                    "No Must requirement in this area — check whether it is genuinely all "
                    "optional, or simply was not pressed.",
                    f"{len(in_area)} requirement(s), none classified Must",
                ))

        # sections that produced nothing
        for section in snapshot.sections:
            if section.utterance_indexes and not any(
                r.evidence.section_id == section.id for r in snapshot.requirements
            ):
                findings.append(DiscoveryFindingRow(
                    "DISC-203", "info", "coverage", section.title,
                    "Discussed, but no requirement came out of it.",
                    f"{len(section.utterance_indexes)} turn(s), 0 requirements",
                ))

        # actions and parked items
        for action in snapshot.actions:
            if not action.due:
                findings.append(DiscoveryFindingRow(
                    "DISC-301", "error", "follow-up", action.id,
                    "Action has no due date, so nothing makes it happen.",
                    f"line {action.evidence.line}",
                ))
            if not (action.owner_key or action.owner_name):
                findings.append(DiscoveryFindingRow(
                    "DISC-302", "error", "follow-up", action.id,
                    "Action has no owner.",
                    f"line {action.evidence.line}",
                ))
        if snapshot.parked_items:
            findings.append(DiscoveryFindingRow(
                "DISC-303", "warning", "follow-up", f"{len(snapshot.parked_items)} parked item(s)",
                "Unresolved decisions. Each needs an owner and a date, or it becomes an "
                "assumption by default.",
                ", ".join(p.id for p in snapshot.parked_items),
            ))

        # attribution and coverage of the record itself
        if not any(p.role for p in snapshot.participants):
            findings.append(DiscoveryFindingRow(
                "DISC-401", "warning", "record", "Attendees",
                "No roles are recorded for any attendee, so it is not possible to tell whose "
                "requirement is whose.",
                f"{len(snapshot.participants)} participant(s), no roles",
            ))
        if snapshot.stats.unattributed_utterances:
            findings.append(DiscoveryFindingRow(
                "DISC-402", "warning", "record", "Attribution",
                "Some passages could not be attributed to a speaker.",
                f"{snapshot.stats.unattributed_utterances} turn(s)",
            ))
        if snapshot.stats.inaudible_markers:
            findings.append(DiscoveryFindingRow(
                "DISC-403", "info", "record", "Audio quality",
                "Content is missing where the transcript is marked inaudible.",
                f"{snapshot.stats.inaudible_markers} [inaudible] marker(s)",
            ))
        silent = [p for p in snapshot.participants if p.utterance_count == 0]
        if silent:
            findings.append(DiscoveryFindingRow(
                "DISC-404", "info", "record", ", ".join(p.name or p.key for p in silent),
                "Listed as attending but never spoke — their area may be uncovered.",
                f"{len(silent)} attendee(s) with no recorded turn",
            ))
        return findings

    def _quality(self, snapshot: TranscriptSnapshot) -> Section:
        section = Section("Source record")
        stats = snapshot.stats
        section.add(BulletList([
            f"{stats.lines_read:,} line(s) read from {snapshot.source_file} "
            f"({snapshot.meeting.source_format} format).",
            f"{stats.utterance_count} turn(s) attributed to {stats.speaker_count} speaker(s).",
            f"{stats.inaudible_markers} [inaudible] and {stats.crosstalk_markers} [crosstalk] marker(s).",
            f"{stats.lines_unrecognised} line(s) matched no known construct.",
        ]))
        if snapshot.warnings:
            section.add(Table(
                headers=["Code", "Context", "Warning"],
                rows=[[w.code, dash(w.context), w.message] for w in snapshot.warnings],
            ))
        else:
            section.add(Paragraph("No parse warnings: every line of the transcript was recognised."))
        return section
