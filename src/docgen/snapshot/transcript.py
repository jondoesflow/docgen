"""Canonical snapshot schema for a parsed meeting transcript.

The transcript snapshot is to a `.txt`/`.vtt` transcript what `Snapshot` is to a
solution zip: the single source of truth every transcript renderer consumes.
Same conventions — keyed collections, canonical ordering in `snapshot.io`,
plain values, tolerant parsing that degrades to a warning rather than raising.

Everything in here is *observed*, never inferred prose: every requirement,
decision and RRAID seed carries the verbatim sentence it came from, the speaker
who said it and the source line number, so a consultant can always check the
tape. Judgement — priority confirmation, formal requirement wording, impact and
mitigation — stays with the consultant (or the optional LLM tier).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from docgen.snapshot.models import DocgenModel, ParseWarning  # noqa: F401 — ParseWarning re-exported

TRANSCRIPT_SCHEMA_VERSION = "1.0"
TRANSCRIPT_KIND = "transcript"

# Source format profiles the parser recognises.
FORMAT_STRUCTURED = "structured"  # facilitated-workshop layout: banners, initials, [ACTION:] markers
FORMAT_TEAMS_TXT = "teams_txt"  # Teams "Download transcript" .txt: "Name   0:12" then text
FORMAT_VTT = "vtt"  # WebVTT (.vtt), including Teams' <v Name> voice spans
FORMAT_PLAIN = "plain"  # fallback: "Name: text" lines, or unattributed paragraphs

ALL_FORMAT_PROFILES = (FORMAT_STRUCTURED, FORMAT_TEAMS_TXT, FORMAT_VTT, FORMAT_PLAIN)

# Sides a participant can be on. Derived from the attendee block where the
# transcript has one; "unknown" is a first-class value, not a failure.
SIDE_CLIENT = "client"
SIDE_CONSULTANCY = "consultancy"
SIDE_UNKNOWN = "unknown"

PRIORITIES = ("must", "should", "could", "wont", "unclassified")
REQUIREMENT_KINDS = ("functional", "non_functional", "constraint")
FINDING_CATEGORIES = ("risk", "assumption", "issue", "dependency", "constraint")


# ---------------------------------------------------------------------------
# Meeting metadata and people
# ---------------------------------------------------------------------------


class MeetingMeta(DocgenModel):
    """Header facts. Absent fields stay empty rather than being guessed."""

    title: str = ""
    subtitle: str = ""
    client_organisation: str | None = None
    consultancy: str | None = None
    date: str | None = None  # verbatim from the transcript header, not reformatted
    time: str | None = None
    location: str | None = None
    facilitator: str | None = None
    recording_note: str | None = None
    source_format: str = FORMAT_PLAIN


class Participant(DocgenModel):
    key: str  # key — initials in the structured profile, else a slug of the name
    name: str = ""
    role: str | None = None
    organisation: str | None = None
    side: str = SIDE_UNKNOWN
    attendance_note: str | None = None  # e.g. "joining remotely from Bristol"
    utterance_count: int = 0
    word_count: int = 0


class AgendaItem(DocgenModel):
    number: str  # key
    title: str = ""
    scheduled: str | None = None  # verbatim, e.g. "09:30 - 09:45"


# ---------------------------------------------------------------------------
# Transcript body
# ---------------------------------------------------------------------------


class Utterance(DocgenModel):
    index: int  # key — position in the transcript, 1-based
    speaker_key: str = ""  # "" for unattributed passages
    speaker_name: str = ""
    timestamp: str | None = None  # verbatim clock reading in force at this point
    section_id: str = ""
    text: str = ""
    line: int = 0  # 1-based source line, so every quote is checkable


class TranscriptSection(DocgenModel):
    id: str  # key — "3", "5.1", or a slug where the transcript does not number them
    title: str = ""
    level: int = 1
    parent_id: str | None = None
    line: int = 0
    start_timestamp: str | None = None
    utterance_indexes: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Extracted items — all evidence-carrying
# ---------------------------------------------------------------------------


class Evidence(DocgenModel):
    """Where a seeded item came from. Never empty for a seeded item."""

    quote: str = ""  # the verbatim sentence
    speaker_key: str = ""
    speaker_name: str = ""
    section_id: str = ""
    section_title: str = ""
    line: int = 0
    cue: str = ""  # the rule/cue phrase that matched

    def reference(self) -> str:
        who = self.speaker_name or self.speaker_key or "unattributed"
        return f"{who}, line {self.line}" if self.line else who


class ActionItem(DocgenModel):
    id: str  # key — A1..An from an action register, or ACT-001 for inline markers
    owner_key: str = ""
    owner_name: str = ""
    description: str = ""
    due: str | None = None
    source: str = ""  # register | inline_marker
    evidence: Evidence = Field(default_factory=Evidence)


class ParkedItem(DocgenModel):
    id: str  # key — P1..Pn, or PARK-001 for inline markers
    description: str = ""
    source: str = ""  # register | inline_marker
    evidence: Evidence = Field(default_factory=Evidence)


class DecisionItem(DocgenModel):
    id: str  # key — DEC-001
    statement: str = ""  # verbatim
    evidence: Evidence = Field(default_factory=Evidence)


class RequirementSeed(DocgenModel):
    id: str  # key — REQ-001
    statement: str = ""  # verbatim sentence, NOT a rewritten requirement
    area: str = ""  # section title it was raised in
    kind: str = "functional"  # functional | non_functional | constraint
    priority: str = "unclassified"  # must | should | could | wont | unclassified
    priority_cue: str = ""  # the phrase the priority was read from ("" = defaulted)
    evidence: Evidence = Field(default_factory=Evidence)


class DiscoveryFinding(DocgenModel):
    """A RRAID seed detected in the transcript."""

    id: str  # key — RSK-001 / ASM-001 / ISS-001 / DEP-001 / CON-001
    category: str  # risk | assumption | issue | dependency | constraint
    statement: str = ""  # verbatim
    evidence: Evidence = Field(default_factory=Evidence)


# ---------------------------------------------------------------------------
# Design-stage material
#
# The pre-build design documents are built from these. They are *observations
# about language*, not design decisions: a term the client said forty times is
# worth modelling, and docgen says so and shows the count. Which of them
# becomes a table, and what its columns are, stays with the consultant.
# ---------------------------------------------------------------------------


class CandidateObject(DocgenModel):
    """A business term the client used repeatedly — a candidate table."""

    name: str  # key — normalised (singular, lower case)
    surface_form: str = ""  # the most common form actually spoken
    mentions: int = 0
    speakers: list[str] = Field(default_factory=list)  # who used it
    attribute_terms: list[str] = Field(default_factory=list)  # co-occurring attribute-ish words
    evidence: Evidence = Field(default_factory=Evidence)


class ExternalSystem(DocgenModel):
    """A system, store or channel named in the session — a candidate interface."""

    name: str  # key
    mentions: int = 0
    evidence: Evidence = Field(default_factory=Evidence)


class LabelledStatement(DocgenModel):
    """A verbatim statement routed to a design document by its category.

    Categories are defined entirely in `transcript_cues.yaml::statement_groups`,
    so a new theme is a YAML change, not a code change.
    """

    id: str  # key
    category: str  # user_population, access_control, availability, ...
    label: str = ""  # human label for the category
    statement: str = ""  # verbatim
    evidence: Evidence = Field(default_factory=Evidence)


# ---------------------------------------------------------------------------
# Coverage / quality
# ---------------------------------------------------------------------------


class TranscriptStats(DocgenModel):
    utterance_count: int = 0
    word_count: int = 0
    speaker_count: int = 0
    unattributed_utterances: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    inaudible_markers: int = 0
    crosstalk_markers: int = 0
    section_count: int = 0
    lines_read: int = 0
    lines_unrecognised: int = 0


# ---------------------------------------------------------------------------
# Snapshot root
# ---------------------------------------------------------------------------


class TranscriptSnapshot(BaseModel):
    """Root document. `kind` is the discriminator that lets `render`/`all`
    tell a transcript snapshot from a solution snapshot on disk."""

    model_config = ConfigDict(extra="forbid")

    kind: str = TRANSCRIPT_KIND
    schema_version: str = TRANSCRIPT_SCHEMA_VERSION
    generated_at: str = ""  # ISO 8601; zeroed in golden-test comparisons
    docgen_version: str = ""
    source_file: str = ""
    meeting: MeetingMeta = Field(default_factory=MeetingMeta)
    participants: list[Participant] = Field(default_factory=list)
    agenda: list[AgendaItem] = Field(default_factory=list)
    sections: list[TranscriptSection] = Field(default_factory=list)
    utterances: list[Utterance] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)
    parked_items: list[ParkedItem] = Field(default_factory=list)
    decisions: list[DecisionItem] = Field(default_factory=list)
    requirements: list[RequirementSeed] = Field(default_factory=list)
    findings: list[DiscoveryFinding] = Field(default_factory=list)
    candidate_objects: list[CandidateObject] = Field(default_factory=list)
    external_systems: list[ExternalSystem] = Field(default_factory=list)
    statements: list[LabelledStatement] = Field(default_factory=list)
    stats: TranscriptStats = Field(default_factory=TranscriptStats)
    warnings: list[ParseWarning] = Field(default_factory=list)

    # -- convenience accessors used by renderers -----------------------------

    def display_title(self) -> str:
        return self.meeting.title or self.source_file or "Meeting"

    def participant(self, key: str) -> Participant | None:
        for person in self.participants:
            if person.key == key:
                return person
        return None

    def section(self, section_id: str) -> TranscriptSection | None:
        for section in self.sections:
            if section.id == section_id:
                return section
        return None

    def section_title(self, section_id: str) -> str:
        found = self.section(section_id)
        return found.title if found else ""

    def statements_in(self, *categories: str) -> list[LabelledStatement]:
        wanted = set(categories)
        return [s for s in self.statements if s.category in wanted]

    def requirements_of(self, *kinds: str) -> list[RequirementSeed]:
        wanted = set(kinds)
        return [r for r in self.requirements if r.kind in wanted]

    def requirement_areas(self) -> list[str]:
        """Functional areas in the order they were discussed."""
        areas: list[str] = []
        for requirement in self.requirements:
            if requirement.area and requirement.area not in areas:
                areas.append(requirement.area)
        return areas
