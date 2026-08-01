"""Transcript parsing: a meeting transcript file → `TranscriptSnapshot`.

This is the transcript half of the snapshot-first principle. `parse_transcript`
is the only code that reads the `.txt`/`.vtt`/`.md` file; every transcript
renderer consumes the snapshot only. Re-record, re-parse, re-render and the
meeting documentation is true again.

Structure comes from `formats.py` (which shape of transcript is this, and where
are the turns, sections and registers); meaning-bearing items come from
`extract.py` (which sentences are requirements, decisions or RRAID seeds, and
what evidence backs each one).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from rapidfuzz import fuzz

from docgen import __version__
from docgen.snapshot.models import ParseWarning
from docgen.snapshot.transcript import (
    AgendaItem,
    MeetingMeta,
    Participant,
    TranscriptSection,
    TranscriptSnapshot,
    TranscriptStats,
    Utterance,
    SIDE_CLIENT,
    SIDE_CONSULTANCY,
    SIDE_UNKNOWN,
)
from docgen.transcripts import formats
from docgen.transcripts.extract import (
    CueRules,
    build_actions,
    build_marker_decisions,
    build_parked,
    extract_candidate_objects,
    extract_external_systems,
    extract_items,
    extract_statements,
)

TRANSCRIPT_SUFFIXES = (".txt", ".vtt", ".md", ".text", ".transcript")

_NAME_MATCH_SCORE = 88


class TranscriptReadError(ValueError):
    pass


def looks_like_transcript(path: Path) -> bool:
    return Path(path).suffix.lower() in TRANSCRIPT_SUFFIXES


def _slug(value: str) -> str:
    normalised = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(ch for ch in normalised if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")
    return slug or "speaker"


def _initials(name: str) -> str:
    parts = [p for p in re.split(r"[\s.-]+", name) if p and p[0].isalpha()]
    return "".join(p[0].upper() for p in parts[:3]) or name[:2].upper()


def read_text(path: Path) -> str:
    """Read a transcript with the encodings Teams and Windows actually produce."""
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise TranscriptReadError(f"Could not decode {path} as text (tried UTF-8, UTF-16, CP1252, Latin-1).")


# ---------------------------------------------------------------------------
# Participant resolution
# ---------------------------------------------------------------------------


class _Roster:
    """Maps the speaker labels found in the body onto attendee-block people,
    creating entries for anyone who speaks but was never listed."""

    def __init__(self, attendees: list[formats.RawAttendee]) -> None:
        self.people: list[Participant] = []
        self._by_key: dict[str, Participant] = {}
        for attendee in attendees:
            key = attendee.initials.upper() if attendee.initials else _slug(attendee.name)
            if key in self._by_key:
                continue
            person = Participant(
                key=key,
                name=attendee.name,
                role=attendee.role or None,
                organisation=attendee.organisation or None,
                side=attendee.side,
            )
            self._extract_attendance_note(person)
            self.people.append(person)
            self._by_key[key] = person
        self.had_attendee_block = bool(attendees)
        self.unlisted: set[str] = set()

    @staticmethod
    def _extract_attendance_note(person: Participant) -> None:
        if not person.role:
            return
        match = re.search(r"\((?P<note>[^)]*(?:remote|dial|phone|teams|video)[^)]*)\)", person.role, re.IGNORECASE)
        if match:
            person.attendance_note = match.group("note").strip()
            person.role = person.role[: match.start()].strip().rstrip("-–,").strip() or None

    def resolve(self, label: str) -> tuple[str, str]:
        """Returns (key, display name). Never fails — an unknown speaker is added."""
        cleaned = (label or "").strip()
        if not cleaned:
            return "", ""
        upper = cleaned.upper()
        if upper in self._by_key:
            person = self._by_key[upper]
            return person.key, person.name or person.key

        for person in self.people:
            if person.name and person.name.lower() == cleaned.lower():
                return person.key, person.name
        # Teams sometimes renders "Fenwick, Alex" or drops a middle name.
        best: tuple[int, Participant | None] = (0, None)
        for person in self.people:
            if not person.name:
                continue
            score = max(
                fuzz.token_set_ratio(person.name.lower(), cleaned.lower()),
                fuzz.ratio(person.name.lower(), cleaned.lower()),
            )
            if score > best[0]:
                best = (score, person)
        if best[1] is not None and best[0] >= _NAME_MATCH_SCORE:
            return best[1].key, best[1].name

        # "AF"/"TB" are references to a person; "Kaya"/"Alex Fenwick" are the person.
        is_initials = cleaned.isalnum() and cleaned.isupper() and len(cleaned) <= 5
        key = upper if is_initials else _slug(cleaned)
        if key not in self._by_key:
            person = Participant(key=key, name="" if is_initials else cleaned, side=SIDE_UNKNOWN)
            self.people.append(person)
            self._by_key[key] = person
            self.unlisted.add(cleaned)
        person = self._by_key[key]
        return person.key, person.name or person.key


# ---------------------------------------------------------------------------
# Meeting metadata
# ---------------------------------------------------------------------------


def _build_meeting(raw: formats.RawTranscript, source_name: str, roster: _Roster) -> MeetingMeta:
    header = {key.lower(): value for key, value in raw.header.items()}
    titles = [formats.humanise_heading(line) for line in raw.title_lines]

    organisation = next((p.organisation for p in roster.people
                         if p.side == SIDE_CLIENT and p.organisation), None)
    consultancy = next((p.organisation for p in roster.people
                        if p.side == SIDE_CONSULTANCY and p.organisation), None)

    if len(titles) >= 2:
        organisation = organisation or titles[0]
        title = " — ".join(titles[1:])
    elif titles:
        title = titles[0]
    else:
        title = header.get("meeting") or header.get("session") or header.get("subject") or ""
        if not title:
            # Nothing in the file names the meeting — fall back to the file name
            # itself rather than inventing a title.
            stem = re.sub(r"[_-]+", " ", Path(source_name).stem).strip()
            title = formats.humanise_heading(stem)
            title = title[:1].upper() + title[1:] if title else ""

    return MeetingMeta(
        title=title,
        subtitle=header.get("session", ""),
        client_organisation=organisation or header.get("client") or None,
        consultancy=consultancy or None,
        date=header.get("date") or None,
        time=header.get("time") or header.get("duration") or None,
        location=header.get("location") or None,
        facilitator=header.get("facilitator") or header.get("organiser") or header.get("organizer") or None,
        recording_note=header.get("recording") or None,
        source_format=raw.profile,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def parse_transcript(path: Path, cue_rules: dict | None = None, profile: str | None = None) -> TranscriptSnapshot:
    """Parse a meeting transcript into a canonical `TranscriptSnapshot`."""
    path = Path(path)
    text = read_text(path)
    raw = formats.parse_lines(text, profile)
    warnings: list[ParseWarning] = list(raw.warnings)

    roster = _Roster(raw.attendees)

    # -- sections --------------------------------------------------------
    sections = [
        TranscriptSection(id=s.id, title=s.title, level=s.level, parent_id=s.parent_id,
                          line=s.line, start_timestamp=s.start_timestamp)
        for s in raw.sections
    ]
    if not sections:
        sections = [TranscriptSection(id="1", title="Discussion", level=1, line=1)]
        if raw.utterances:
            warnings.append(ParseWarning(
                code="no_section_structure",
                context=f"{path.name} ({raw.profile})",
                message="The transcript has no section headings, so the whole conversation is "
                        "reported as a single section. Add headings to the transcript, or expect "
                        "requirements to be grouped under one area.",
            ))
    known_sections = {section.id for section in sections}
    section_titles = {section.id: section.title for section in sections}

    # -- utterances ------------------------------------------------------
    utterances: list[Utterance] = []
    for index, item in enumerate(raw.utterances, start=1):
        key, name = roster.resolve(item.speaker_label)
        section_id = item.section_id if item.section_id in known_sections else sections[0].id
        utterances.append(Utterance(
            index=index, speaker_key=key, speaker_name=name, timestamp=item.timestamp,
            section_id=section_id, text=item.text, line=item.line,
        ))

    for utterance in utterances:
        person = next((p for p in roster.people if p.key == utterance.speaker_key), None)
        if person is not None:
            person.utterance_count += 1
            person.word_count += len(utterance.text.split())
        section = next((s for s in sections if s.id == utterance.section_id), None)
        if section is not None:
            section.utterance_indexes.append(utterance.index)

    # Only meaningful where the transcript actually declared who was in the room —
    # a Teams export never does, so every speaker would be "unlisted".
    if roster.unlisted and roster.had_attendee_block:
        warnings.append(ParseWarning(
            code="unlisted_speaker",
            context=path.name,
            message="Spoke but was not in the attendee list: " + ", ".join(sorted(roster.unlisted))
                    + ". Confirm the attendee list before issuing the notes.",
        ))
    elif roster.unlisted:
        warnings.append(ParseWarning(
            code="no_attendee_list",
            context=f"{path.name} ({raw.profile})",
            message=f"The transcript declares no attendee list, so roles, organisations and sides "
                    f"are unknown for all {len(roster.unlisted)} speaker(s). Complete the attendee "
                    "table in the meeting notes before issuing them.",
        ))
    if not raw.utterances:
        warnings.append(ParseWarning(
            code="no_dialogue",
            context=f"{path.name} ({raw.profile})",
            message="No attributed dialogue was recognised. Check the transcript format — docgen "
                    "reads structured workshop notes, Teams .txt exports, WebVTT and 'Name: text' lines.",
        ))

    # -- extracted items -------------------------------------------------
    rules = CueRules.from_rules(cue_rules)
    requirements, decisions, findings = extract_items(utterances, section_titles, rules)
    actions = build_actions(raw.action_rows, raw.markers, section_titles, roster.resolve)
    parked = build_parked(raw.parked_rows, raw.markers, section_titles)
    decisions += build_marker_decisions(raw.markers, section_titles, len(decisions))
    candidate_objects = extract_candidate_objects(utterances, section_titles, rules)
    external_systems = extract_external_systems(utterances, section_titles, rules)
    statements = extract_statements(utterances, section_titles, rules)

    # -- stats -----------------------------------------------------------
    timestamps = [u.timestamp for u in utterances if u.timestamp]
    stats = TranscriptStats(
        utterance_count=len(utterances),
        word_count=sum(len(u.text.split()) for u in utterances),
        speaker_count=len({u.speaker_key for u in utterances if u.speaker_key}),
        unattributed_utterances=sum(1 for u in utterances if not u.speaker_key),
        first_timestamp=timestamps[0] if timestamps else None,
        last_timestamp=timestamps[-1] if timestamps else None,
        inaudible_markers=len(formats.INAUDIBLE.findall(text)),
        crosstalk_markers=len(formats.CROSSTALK.findall(text)),
        section_count=len(sections),
        lines_read=raw.lines_total,
        lines_unrecognised=raw.lines_unrecognised,
    )
    if raw.lines_unrecognised:
        warnings.append(ParseWarning(
            code="unrecognised_line",
            context=f"{path.name} ({raw.profile})",
            message=f"{raw.lines_unrecognised} line(s) did not match any known construct and carry no "
                    "content in the documents. Nothing was dropped from the dialogue itself.",
        ))

    return TranscriptSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        docgen_version=__version__,
        source_file=path.name,
        meeting=_build_meeting(raw, path.name, roster),
        participants=roster.people,
        agenda=[AgendaItem(number=item.number, title=item.title, scheduled=item.scheduled)
                for item in raw.agenda],
        sections=sections,
        utterances=utterances,
        actions=actions,
        parked_items=parked,
        decisions=decisions,
        requirements=requirements,
        findings=findings,
        candidate_objects=candidate_objects,
        external_systems=external_systems,
        statements=statements,
        stats=stats,
        warnings=warnings,
    )
