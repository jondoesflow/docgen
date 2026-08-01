"""Formatting helpers shared by the transcript document renderers."""

from __future__ import annotations

from docgen.renderers.docs.common import DASH, dash
from docgen.snapshot.transcript import (
    Evidence,
    SIDE_CLIENT,
    SIDE_CONSULTANCY,
    TranscriptSection,
    TranscriptSnapshot,
)

PRIORITY_LABELS = {
    "must": "Must",
    "should": "Should",
    "could": "Could",
    "wont": "Won't (this phase)",
    "unclassified": "Unclassified",
}
PRIORITY_ORDER = ("must", "should", "could", "wont", "unclassified")

KIND_LABELS = {
    "functional": "Functional",
    "non_functional": "Non-functional",
    "constraint": "Constraint / exclusion",
}

CATEGORY_LABELS = {
    "risk": "Risks",
    "assumption": "Assumptions",
    "issue": "Issues",
    "dependency": "Dependencies",
    "constraint": "Constraints",
}

SIDE_LABELS = {
    SIDE_CLIENT: "Client",
    SIDE_CONSULTANCY: "Consultancy",
    "unknown": "Unconfirmed",
}

FORMAT_LABELS = {
    "structured": "Structured workshop transcript",
    "teams_txt": "Microsoft Teams transcript (.txt export)",
    "vtt": "WebVTT transcript (.vtt)",
    "plain": "Plain 'Speaker: text' transcript",
}

SEEDED_NOTE = (
    "Entries below were extracted automatically from the transcript. Each one quotes the "
    "sentence it came from, who said it and the line it is on, so every statement can be "
    "checked against the recording. They are candidates for a consultant to confirm, merge "
    "and reword — not a signed-off catalogue."
)


def quote(text: str) -> str:
    """Verbatim text presented as a quotation, never edited."""
    return f"“{text.strip()}”" if text.strip() else DASH


def evidence_ref(evidence: Evidence) -> str:
    who = evidence.speaker_name or evidence.speaker_key or "unattributed"
    where = f"line {evidence.line}" if evidence.line else "line unknown"
    return f"{who}, {where}"


def meeting_facts(snapshot: TranscriptSnapshot) -> list[list[str]]:
    meeting = snapshot.meeting
    stats = snapshot.stats
    span = DASH
    if stats.first_timestamp and stats.last_timestamp:
        span = f"{stats.first_timestamp} – {stats.last_timestamp}"
    return [
        ["Meeting", dash(meeting.title)],
        ["Client", dash(meeting.client_organisation)],
        ["Consultancy", dash(meeting.consultancy)],
        ["Date", dash(meeting.date)],
        ["Scheduled time", dash(meeting.time)],
        ["Location", dash(meeting.location)],
        ["Facilitator", dash(meeting.facilitator)],
        ["Timestamps covered", span],
        ["Source file", dash(snapshot.source_file)],
        ["Source format", FORMAT_LABELS.get(meeting.source_format, meeting.source_format)],
        ["Snapshot generated", dash(snapshot.generated_at)],
        ["docgen version", dash(snapshot.docgen_version)],
    ]


def attendee_rows(snapshot: TranscriptSnapshot) -> list[list[str]]:
    total_words = sum(p.word_count for p in snapshot.participants) or 1
    rows: list[list[str]] = []
    for person in snapshot.participants:
        share = round(100 * person.word_count / total_words)
        rows.append([
            person.name or person.key,
            person.key,
            dash(person.role),
            dash(person.organisation),
            SIDE_LABELS.get(person.side, person.side),
            dash(person.attendance_note),
            (f"{person.utterance_count} turn{'' if person.utterance_count == 1 else 's'} · "
             f"{share}% of words") if person.utterance_count else "Did not speak",
        ])
    return rows


def discussion_sections(snapshot: TranscriptSnapshot) -> list[TranscriptSection]:
    """Sections that actually carry dialogue, in document order."""
    return [section for section in snapshot.sections if section.utterance_indexes]


def utterances_in(snapshot: TranscriptSnapshot, section: TranscriptSection):
    by_index = {u.index: u for u in snapshot.utterances}
    return [by_index[i] for i in section.utterance_indexes if i in by_index]


def section_speakers(snapshot: TranscriptSnapshot, section: TranscriptSection) -> list[str]:
    seen: list[str] = []
    for utterance in utterances_in(snapshot, section):
        label = utterance.speaker_name or utterance.speaker_key
        if label and label not in seen:
            seen.append(label)
    return seen


def counts_by(items, attribute: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = getattr(item, attribute)
        counts[value] = counts.get(value, 0) + 1
    return counts
