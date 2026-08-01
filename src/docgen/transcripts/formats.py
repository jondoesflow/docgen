"""Transcript format detection and structural parsing.

Three real-world shapes are recognised, plus a fallback:

* ``structured`` — a facilitated-workshop transcript: banner-ruled sections,
  an attendee block, an agenda, speaker initials, ``[ACTION:]``/``[PARKED:]``
  markers and end-of-document action/parked registers.
* ``teams_txt`` — the plain-text file Teams produces from
  *Download transcript*: ``Name   0:12`` on its own line, then the words.
* ``vtt`` — WebVTT, including the ``<v Name>`` voice spans Teams emits.
* ``plain`` — anything else: ``Name: text`` lines, or, failing that, blank-line
  separated paragraphs captured unattributed.

Every parser here is tolerant in the same way the solution parsers are: a line
that cannot be classified is counted (and surfaced in the transcript-quality
section) rather than raising. Nothing is silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from docgen.snapshot.models import ParseWarning
from docgen.snapshot.transcript import (
    FORMAT_PLAIN,
    FORMAT_STRUCTURED,
    FORMAT_TEAMS_TXT,
    FORMAT_VTT,
    SIDE_CLIENT,
    SIDE_CONSULTANCY,
    SIDE_UNKNOWN,
)

# ---------------------------------------------------------------------------
# Line-shape patterns
# ---------------------------------------------------------------------------

RULE_EQUALS = re.compile(r"^={8,}\s*$")
RULE_DASHES = re.compile(r"^-{8,}\s*$")
INLINE_HEADING = re.compile(r"^-{2,3}\s*(?P<title>.+?)\s*-{2,3}\s*$")
TIMESTAMP_LINE = re.compile(r"^\[(?P<start>\d{1,2}:\d{2}(?::\d{2})?)(?:\s*[-–]\s*(?P<end>\d{1,2}:\d{2}(?::\d{2})?))?\]\s*$")
MARKER_START = re.compile(r"^\[(?P<kind>ACTION|PARKED|DECISION|AGREED)\s*:\s*(?P<text>.*)$", re.IGNORECASE)
SPEAKER_LINE = re.compile(r"^(?P<speaker>[A-Z][A-Za-z0-9][A-Za-z0-9 .'’-]{0,38}):(?:\s+(?P<text>.*))?$")
HEADER_KEY = re.compile(r"^(?P<key>Date|Time|Location|Facilitator|Recording|Meeting|Session|Subject|Organiser|Organizer|Attendees|Duration|Client|Project)\s*:\s*(?P<value>.*)$", re.IGNORECASE)
ATTENDEE_GROUP = re.compile(r"^(?P<side>CLIENT|CONSULTANCY|CONSULTANT|SUPPLIER|PARTNER|VENDOR|OTHER)\b\s*[-–:]?\s*(?P<org>.*)$")
ATTENDEE_LINE = re.compile(r"^\s{2,}(?P<name>[A-Z][^(]{1,60}?)\s*\((?P<initials>[A-Za-z0-9]{1,5})\)\s*(?P<role>.*)$")
AGENDA_LINE = re.compile(r"^\s*(?P<number>\d{1,2})[.)]\s+(?P<title>.+?)(?:\s{2,}(?P<time>\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}))?\s*$")
ACTION_ROW = re.compile(r"^\s*(?P<id>[A-Z]\d{1,3})\s+(?P<owner>[A-Z]{1,5})\s+(?P<rest>\S.*?)\s*$")
PARKED_ROW = re.compile(r"^\s*(?P<id>P\d{1,3})\s+(?P<rest>\S.*?)\s*$")
DUE_SUFFIX = re.compile(r"(?:^|(?<=[.\s]))(?P<due>(?:By|Due|Deadline)\b[^.]*)$", re.IGNORECASE)

# Teams .txt: "Alex Fenwick   0:12" (or the reversed "0:12  Alex Fenwick")
TEAMS_NAME_FIRST = re.compile(r"^(?P<name>\S.{0,58}?)[ \t]{1,}(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\s*$")
TEAMS_TIME_FIRST = re.compile(r"^(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)[ \t]+(?P<name>\S.{0,58}?)\s*$")

VTT_TIMING = re.compile(r"-->")
VTT_VOICE = re.compile(r"<v\s+(?P<name>[^>]+)>(?P<text>.*?)(?:</v>)?\s*$", re.IGNORECASE)
VTT_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
VTT_CLOCK = re.compile(r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})[.,]\d{3}")

INAUDIBLE = re.compile(r"\[inaudible[^\]]*\]", re.IGNORECASE)
CROSSTALK = re.compile(r"\[cross\s?talk[^\]]*\]", re.IGNORECASE)

_SIDE_WORDS = {
    "CLIENT": SIDE_CLIENT,
    "CONSULTANCY": SIDE_CONSULTANCY,
    "CONSULTANT": SIDE_CONSULTANCY,
    "SUPPLIER": SIDE_CONSULTANCY,
    "PARTNER": SIDE_CONSULTANCY,
    "VENDOR": SIDE_CONSULTANCY,
    "OTHER": SIDE_UNKNOWN,
}

# Headings inside the structured profile that introduce a register rather than
# discussion. Matched case-insensitively against the humanised heading.
REGISTER_HEADINGS = {
    "attendees": "attendees",
    "attendance": "attendees",
    "participants": "attendees",
    "agenda": "agenda",
    "actions": "actions",
    "action items": "actions",
    "action log": "actions",
    "parked items": "parked",
    "parked": "parked",
    "parking lot": "parked",
}

_SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or",
                "the", "to", "vs", "with"}
_ACRONYMS = {"AI", "API", "BA", "CRM", "DR", "EU", "ERP", "GDPR", "HR", "ICT", "IT", "KPI",
             "MI", "NFR", "QA", "RPO", "RRAID", "RTO", "SLA", "SME", "UAT", "UK", "US", "VAT"}


def humanise_heading(text: str) -> str:
    """Make a SHOUTED banner heading readable without inventing anything.

    Headings that already contain lower-case letters are returned untouched —
    only all-caps headings are re-cased, and known acronyms are preserved.
    """
    stripped = text.strip()
    if not stripped or any(ch.islower() for ch in stripped):
        return stripped
    words = stripped.split()
    out: list[str] = []
    for i, word in enumerate(words):
        core = word.strip(".,:;()[]/&-")
        if core.upper() in _ACRONYMS:
            out.append(word)
        elif i > 0 and core.lower() in _SMALL_WORDS:
            out.append(word.lower())
        else:
            out.append(word.capitalize())
    return " ".join(out)


def normalise_clock(value: str) -> str:
    """`00:09:31.000` → `09:31`; short readings are returned unchanged."""
    match = VTT_CLOCK.search(value)
    if not match:
        return value.strip()
    hours, minutes, seconds = match.group("h"), match.group("m"), match.group("s")
    if hours == "00":
        return f"{int(minutes)}:{seconds}"
    return f"{int(hours)}:{minutes}:{seconds}"


# ---------------------------------------------------------------------------
# Intermediate structures produced by the profile parsers
# ---------------------------------------------------------------------------


@dataclass
class RawUtterance:
    speaker_label: str
    text: str
    line: int
    timestamp: str | None = None
    section_id: str = ""


@dataclass
class RawMarker:
    kind: str  # action | parked | decision
    text: str
    line: int
    section_id: str = ""


@dataclass
class RawAttendee:
    name: str
    initials: str
    role: str = ""
    organisation: str = ""
    side: str = SIDE_UNKNOWN


@dataclass
class RawSection:
    id: str
    title: str
    level: int = 1
    parent_id: str | None = None
    line: int = 0
    start_timestamp: str | None = None


@dataclass
class RawAgendaItem:
    number: str
    title: str
    scheduled: str | None = None


@dataclass
class RawActionRow:
    id: str
    owner: str
    description: str
    due: str | None
    line: int


@dataclass
class RawParkedRow:
    id: str
    description: str
    line: int


@dataclass
class RawTranscript:
    profile: str = FORMAT_PLAIN
    title_lines: list[str] = field(default_factory=list)
    header: dict[str, str] = field(default_factory=dict)
    attendees: list[RawAttendee] = field(default_factory=list)
    agenda: list[RawAgendaItem] = field(default_factory=list)
    sections: list[RawSection] = field(default_factory=list)
    utterances: list[RawUtterance] = field(default_factory=list)
    markers: list[RawMarker] = field(default_factory=list)
    action_rows: list[RawActionRow] = field(default_factory=list)
    parked_rows: list[RawParkedRow] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    lines_total: int = 0
    lines_unrecognised: int = 0


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect_format(text: str) -> str:
    lines = text.splitlines()
    head = "\n".join(lines[:5]).lstrip("﻿").strip()
    if head.upper().startswith("WEBVTT"):
        return FORMAT_VTT
    if sum(1 for line in lines if VTT_TIMING.search(line)) >= 3 and any(
        VTT_CLOCK.search(line) for line in lines
    ):
        return FORMAT_VTT

    banner_rules = sum(1 for line in lines if RULE_EQUALS.match(line) or RULE_DASHES.match(line))
    initials_speakers = sum(1 for line in lines if re.match(r"^[A-Z]{2,4}:\s", line))
    if banner_rules >= 2 and initials_speakers >= 3:
        return FORMAT_STRUCTURED

    teams_headers = sum(
        1 for line in lines if TEAMS_NAME_FIRST.match(line) or TEAMS_TIME_FIRST.match(line)
    )
    if teams_headers >= 3:
        return FORMAT_TEAMS_TXT

    if banner_rules >= 2 and sum(1 for line in lines if SPEAKER_LINE.match(line)) >= 3:
        return FORMAT_STRUCTURED
    return FORMAT_PLAIN


# ---------------------------------------------------------------------------
# Structured (facilitated workshop) profile
# ---------------------------------------------------------------------------


def _split_due(rest: str) -> tuple[str, str | None]:
    match = DUE_SUFFIX.search(rest)
    if not match:
        return rest.strip().rstrip("."), None
    description = rest[: match.start("due")].strip().rstrip(".")
    return description, match.group("due").strip().rstrip(".")


class _StructuredParser:
    """Line-driven state machine over the banner-ruled workshop layout."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.raw = RawTranscript(profile=FORMAT_STRUCTURED, lines_total=len(lines))
        self.mode = "header"  # header | attendees | agenda | discussion | actions | parked
        self.section_id = ""
        self.section_counter = 0
        self.timestamp: str | None = None
        self.current_side = SIDE_UNKNOWN
        self.current_org = ""
        self.pending: RawUtterance | None = None
        self.pending_marker: tuple[str, list[str], int] | None = None
        self.seen_first_banner = False

    # -- utterance accumulation ---------------------------------------------

    def _flush(self) -> None:
        if self.pending is not None and self.pending.text.strip():
            self.pending.text = re.sub(r"\s+", " ", self.pending.text).strip()
            self.raw.utterances.append(self.pending)
        self.pending = None

    def _flush_marker(self) -> None:
        if self.pending_marker is None:
            return
        kind, parts, line = self.pending_marker
        text = re.sub(r"\s+", " ", " ".join(parts)).strip().rstrip("]").strip()
        if text:
            self.raw.markers.append(RawMarker(kind=kind, text=text, line=line, section_id=self.section_id))
        self.pending_marker = None

    def _flush_all(self) -> None:
        self._flush()
        self._flush_marker()

    # -- headings ------------------------------------------------------------

    def _start_section(self, title: str, line_no: int, level: int = 1) -> None:
        self._flush_all()
        humanised = humanise_heading(title)
        register = REGISTER_HEADINGS.get(humanised.lower())
        if register == "attendees":
            self.mode = "attendees"
            return
        if register == "agenda":
            self.mode = "agenda"
            return
        if register == "actions":
            self.mode = "actions"
            return
        if register == "parked":
            self.mode = "parked"
            return

        self.mode = "discussion"
        numbered = re.match(r"^(?P<num>\d+(?:\.\d+)*)[.)]?\s+(?P<rest>.+)$", humanised)
        if numbered:
            section_id = numbered.group("num")
            title_text = numbered.group("rest").strip()
            level = section_id.count(".") + 1
        else:
            self.section_counter += 1
            section_id = f"s{self.section_counter}"
            title_text = humanised
        parent = section_id.rsplit(".", 1)[0] if "." in section_id else None
        self.raw.sections.append(
            RawSection(id=section_id, title=title_text, level=level, parent_id=parent,
                       line=line_no, start_timestamp=None)
        )
        self.section_id = section_id

    def _banner_heading(self, index: int) -> tuple[str, int] | None:
        """A rule line, 1-3 content lines, then another rule line."""
        opener = self.lines[index]
        if not (RULE_EQUALS.match(opener) or RULE_DASHES.match(opener)):
            return None
        content: list[str] = []
        cursor = index + 1
        while cursor < len(self.lines) and len(content) <= 3:
            line = self.lines[cursor]
            if RULE_EQUALS.match(line) or RULE_DASHES.match(line):
                if not content:
                    return None
                return (" — ".join(content), cursor)
            if not line.strip():
                return None
            content.append(line.strip())
            cursor += 1
        return None

    # -- main loop -----------------------------------------------------------

    def parse(self) -> RawTranscript:
        skip_until = -1
        for index, line in enumerate(self.lines):
            line_no = index + 1
            if index <= skip_until:
                continue

            banner = self._banner_heading(index)
            if banner is not None:
                heading, closing = banner
                skip_until = closing
                if not self.seen_first_banner and self.mode == "header":
                    # The opening block is the document title, not a section.
                    self.seen_first_banner = True
                    self.raw.title_lines = [part.strip() for part in heading.split(" — ") if part.strip()]
                    continue
                self._start_section(heading, line_no)
                continue

            stripped = line.strip()

            inline = INLINE_HEADING.match(stripped) if stripped else None
            if inline and not TIMESTAMP_LINE.match(stripped):
                self._start_section(inline.group("title"), line_no, level=2)
                continue

            if not stripped:
                self._flush_all()
                continue

            timestamp = TIMESTAMP_LINE.match(stripped)
            if timestamp:
                self._flush_all()
                self.timestamp = timestamp.group("start")
                if self.raw.sections and self.raw.sections[-1].start_timestamp is None:
                    self.raw.sections[-1].start_timestamp = self.timestamp
                continue

            if self.pending_marker is not None:
                self.pending_marker[1].append(stripped)
                if stripped.endswith("]"):
                    self._flush_marker()
                continue

            marker = MARKER_START.match(stripped)
            if marker:
                self._flush()
                kind = marker.group("kind").lower()
                kind = "decision" if kind in {"decision", "agreed"} else kind
                self.pending_marker = (kind, [marker.group("text")], line_no)
                if stripped.endswith("]"):
                    self._flush_marker()
                continue

            if self.mode == "header":
                header = HEADER_KEY.match(stripped)
                if header:
                    self.raw.header[header.group("key").strip().title()] = header.group("value").strip()
                else:
                    self.raw.lines_unrecognised += 1
                continue

            if self.mode == "attendees":
                self._read_attendee(line, line_no)
                continue

            if self.mode == "agenda":
                agenda = AGENDA_LINE.match(line)
                if agenda:
                    self.raw.agenda.append(RawAgendaItem(
                        number=agenda.group("number"),
                        title=agenda.group("title").strip(),
                        scheduled=(agenda.group("time") or "").strip() or None,
                    ))
                else:
                    self.raw.lines_unrecognised += 1
                continue

            if self.mode == "actions":
                row = ACTION_ROW.match(line)
                if row:
                    description, due = _split_due(row.group("rest"))
                    self.raw.action_rows.append(RawActionRow(
                        id=row.group("id"), owner=row.group("owner"),
                        description=description, due=due, line=line_no,
                    ))
                else:
                    self.raw.lines_unrecognised += 1
                continue

            if self.mode == "parked":
                row = PARKED_ROW.match(line)
                if row:
                    self.raw.parked_rows.append(RawParkedRow(
                        id=row.group("id"), description=row.group("rest").strip(), line=line_no,
                    ))
                else:
                    self.raw.lines_unrecognised += 1
                continue

            # discussion
            speaker = SPEAKER_LINE.match(stripped)
            if speaker:
                self._flush()
                self.pending = RawUtterance(
                    speaker_label=speaker.group("speaker").strip(),
                    text=(speaker.group("text") or "").strip(),
                    line=line_no,
                    timestamp=self.timestamp,
                    section_id=self.section_id,
                )
                continue
            if self.pending is not None:
                self.pending.text = f"{self.pending.text} {stripped}".strip()
                continue
            self.raw.lines_unrecognised += 1

        self._flush_all()
        return self.raw

    def _read_attendee(self, line: str, line_no: int) -> None:  # noqa: ARG002 - line_no kept for symmetry
        stripped = line.strip()
        group = ATTENDEE_GROUP.match(stripped)
        if group and not line.startswith("  "):
            self.current_side = _SIDE_WORDS.get(group.group("side").upper(), SIDE_UNKNOWN)
            org = group.group("org").strip().strip("-–:").strip()
            self.current_org = re.sub(r'\s*\("[^"]*"\)\s*$', "", org).strip()
            return
        attendee = ATTENDEE_LINE.match(line)
        if attendee:
            self.raw.attendees.append(RawAttendee(
                name=attendee.group("name").strip(),
                initials=attendee.group("initials").strip(),
                role=attendee.group("role").strip(),
                organisation=self.current_org,
                side=self.current_side,
            ))
            return
        self.raw.lines_unrecognised += 1


def parse_structured(lines: list[str]) -> RawTranscript:
    return _StructuredParser(lines).parse()


# ---------------------------------------------------------------------------
# Teams .txt export
# ---------------------------------------------------------------------------


def parse_teams_txt(lines: list[str]) -> RawTranscript:
    raw = RawTranscript(profile=FORMAT_TEAMS_TXT, lines_total=len(lines))
    speaker: str | None = None
    timestamp: str | None = None
    buffer: list[str] = []
    start_line = 0

    def flush() -> None:
        nonlocal buffer, start_line
        text = re.sub(r"\s+", " ", " ".join(buffer)).strip()
        buffer = []
        if not text or speaker is None:
            return
        raw.utterances.append(RawUtterance(
            speaker_label=speaker, text=text, line=start_line, timestamp=timestamp, section_id="1",
        ))

    for index, line in enumerate(lines):
        line_no = index + 1
        stripped = line.strip()
        if not stripped:
            continue
        header = TEAMS_NAME_FIRST.match(line.rstrip()) or TEAMS_TIME_FIRST.match(line.rstrip())
        if header:
            name = header.group("name").strip()
            # A bare duration line ("1:02:11") is not a speaker.
            if name and not re.fullmatch(r"[\d:.]+", name):
                flush()
                speaker = name
                timestamp = normalise_clock(header.group("ts"))
                start_line = line_no
                continue
        marker = MARKER_START.match(stripped)
        if marker:
            kind = marker.group("kind").lower()
            raw.markers.append(RawMarker(
                kind="decision" if kind in {"decision", "agreed"} else kind,
                text=marker.group("text").strip().rstrip("]").strip(),
                line=line_no, section_id="1",
            ))
            continue
        if speaker is None:
            inline = SPEAKER_LINE.match(stripped)
            if inline:
                speaker = inline.group("speaker").strip()
                start_line = line_no
                buffer.append((inline.group("text") or "").strip())
                continue
            raw.lines_unrecognised += 1
            continue
        if not buffer:
            start_line = line_no
        buffer.append(stripped)
    flush()

    _merge_consecutive(raw)
    return raw


# ---------------------------------------------------------------------------
# WebVTT
# ---------------------------------------------------------------------------


def parse_vtt(lines: list[str]) -> RawTranscript:
    raw = RawTranscript(profile=FORMAT_VTT, lines_total=len(lines))
    timestamp: str | None = None
    pending_payload: list[tuple[str, str, int]] = []  # (speaker, text, line)
    in_cue = False

    def flush_cue() -> None:
        nonlocal pending_payload
        for speaker, text, line_no in pending_payload:
            cleaned = re.sub(r"\s+", " ", VTT_TAG.sub("", text)).strip()
            if cleaned:
                raw.utterances.append(RawUtterance(
                    speaker_label=speaker, text=cleaned, line=line_no,
                    timestamp=timestamp, section_id="1",
                ))
        pending_payload = []

    for index, line in enumerate(lines):
        line_no = index + 1
        stripped = line.strip()
        if not stripped:
            flush_cue()
            in_cue = False
            continue
        if stripped.upper().startswith("WEBVTT") or stripped.startswith("NOTE"):
            continue
        if VTT_TIMING.search(stripped):
            flush_cue()
            timestamp = normalise_clock(stripped.split("-->")[0].strip())
            in_cue = True
            continue
        if not in_cue:
            # cue identifier (Teams emits a GUID) — carries no content
            continue
        voice = VTT_VOICE.match(stripped)
        if voice:
            pending_payload.append((voice.group("name").strip(), voice.group("text"), line_no))
            continue
        inline = SPEAKER_LINE.match(VTT_TAG.sub("", stripped))
        if inline:
            pending_payload.append((inline.group("speaker").strip(), inline.group("text") or "", line_no))
            continue
        if pending_payload:
            speaker, text, first_line = pending_payload[-1]
            pending_payload[-1] = (speaker, f"{text} {stripped}", first_line)
        else:
            pending_payload.append(("", stripped, line_no))
    flush_cue()

    _merge_consecutive(raw)
    return raw


# ---------------------------------------------------------------------------
# Plain fallback
# ---------------------------------------------------------------------------


def parse_plain(lines: list[str]) -> RawTranscript:
    raw = RawTranscript(profile=FORMAT_PLAIN, lines_total=len(lines))
    pending: RawUtterance | None = None

    def flush() -> None:
        nonlocal pending
        if pending is not None and pending.text.strip():
            pending.text = re.sub(r"\s+", " ", pending.text).strip()
            raw.utterances.append(pending)
        pending = None

    for index, line in enumerate(lines):
        line_no = index + 1
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        marker = MARKER_START.match(stripped)
        if marker:
            flush()
            kind = marker.group("kind").lower()
            raw.markers.append(RawMarker(
                kind="decision" if kind in {"decision", "agreed"} else kind,
                text=marker.group("text").strip().rstrip("]").strip(),
                line=line_no, section_id="1",
            ))
            continue
        speaker = SPEAKER_LINE.match(stripped)
        if speaker:
            flush()
            pending = RawUtterance(
                speaker_label=speaker.group("speaker").strip(),
                text=(speaker.group("text") or "").strip(),
                line=line_no, section_id="1",
            )
            continue
        if pending is not None:
            pending.text = f"{pending.text} {stripped}".strip()
            continue
        pending = RawUtterance(speaker_label="", text=stripped, line=line_no, section_id="1")
    flush()
    return raw


# ---------------------------------------------------------------------------
# Shared post-processing
# ---------------------------------------------------------------------------


def _merge_consecutive(raw: RawTranscript) -> None:
    """Teams and VTT split a single turn across many cues — rejoin them."""
    merged: list[RawUtterance] = []
    for utterance in raw.utterances:
        if merged and merged[-1].speaker_label == utterance.speaker_label:
            previous = merged[-1]
            joiner = "" if previous.text.endswith(("-", "–")) else " "
            previous.text = f"{previous.text}{joiner}{utterance.text}".strip()
            continue
        merged.append(utterance)
    raw.utterances = merged


PROFILE_PARSERS = {
    FORMAT_STRUCTURED: parse_structured,
    FORMAT_TEAMS_TXT: parse_teams_txt,
    FORMAT_VTT: parse_vtt,
    FORMAT_PLAIN: parse_plain,
}


def parse_lines(text: str, profile: str | None = None) -> RawTranscript:
    """Structural parse of transcript text using the detected (or given) profile."""
    chosen = profile or detect_format(text)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿").split("\n")
    parser = PROFILE_PARSERS.get(chosen, parse_plain)
    raw = parser(lines)
    raw.profile = chosen
    return raw
