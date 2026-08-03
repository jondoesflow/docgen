"""Transcript parsing: format detection, structure, extraction and tolerance.

Fixtures are committed text files (unlike the solution zips, which are built),
because the thing under test *is* the text layout.
"""

from pathlib import Path

import pytest

from docgen.rules_io import load_rules
from docgen.config import DocgenConfig
from docgen.snapshot.io import (
    SnapshotVersionError,
    dump_transcript_snapshot,
    load_transcript_snapshot,
    save_transcript_snapshot,
    snapshot_kind,
)
from docgen.snapshot.transcript import (
    FORMAT_PLAIN,
    FORMAT_STRUCTURED,
    FORMAT_TEAMS_TXT,
    FORMAT_VTT,
    SIDE_CLIENT,
    SIDE_CONSULTANCY,
)
from docgen.transcripts import parse_transcript
from docgen.transcripts.extract import CueRules, split_sentences
from docgen.transcripts.formats import detect_format, humanise_heading, normalise_clock

TRANSCRIPTS = Path(__file__).parent / "fixtures" / "transcripts"


@pytest.fixture(scope="module")
def cues():
    return load_rules(DocgenConfig()).get("transcript_cues", {})


@pytest.fixture(scope="module")
def workshop(cues):
    return parse_transcript(TRANSCRIPTS / "workshop.txt", cues)


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,expected", [
    ("workshop.txt", FORMAT_STRUCTURED),
    ("teams_export.txt", FORMAT_TEAMS_TXT),
    ("teams_meeting.vtt", FORMAT_VTT),
    ("plain_notes.txt", FORMAT_PLAIN),
])
def test_format_detection(name, expected):
    assert detect_format((TRANSCRIPTS / name).read_text(encoding="utf-8")) == expected


def test_humanise_heading_leaves_mixed_case_alone():
    assert humanise_heading("Results, approval and certificates") == "Results, approval and certificates"


def test_humanise_heading_recases_shouted_headings_and_keeps_acronyms():
    assert humanise_heading("NON-FUNCTIONAL, SECURITY AND IT") == "Non-functional, Security and IT"


def test_normalise_clock():
    assert normalise_clock("00:09:31.000") == "9:31"
    assert normalise_clock("01:09:31.500") == "1:09:31"
    assert normalise_clock("0:12") == "0:12"


# ---------------------------------------------------------------------------
# Structured profile
# ---------------------------------------------------------------------------


def test_meeting_metadata(workshop):
    meeting = workshop.meeting
    assert meeting.title == "Discovery Workshop 1 of 2 - Service Operations"
    assert meeting.client_organisation == "Northgate Utilities plc"
    assert meeting.consultancy == "Halloway Partners"
    assert meeting.date == "Wednesday 6 May 2026"
    assert meeting.location.startswith("Northgate House, Leeds")
    assert meeting.source_format == FORMAT_STRUCTURED


def test_attendees_carry_role_side_and_remote_note(workshop):
    by_key = {p.key: p for p in workshop.participants}
    assert set(by_key) == {"RE", "KP", "IV"}
    assert by_key["RE"].name == "Rowan Ellisdale"
    assert by_key["RE"].role == "Operations Director - project sponsor"
    assert by_key["RE"].side == SIDE_CLIENT
    assert by_key["IV"].side == SIDE_CONSULTANCY
    assert by_key["IV"].organisation == "Halloway Partners"
    assert by_key["KP"].attendance_note == "joining remotely from Hull"
    assert all(p.utterance_count > 0 for p in workshop.participants)


def test_agenda_captured(workshop):
    assert [item.number for item in workshop.agenda] == ["1", "2", "3"]
    assert workshop.agenda[0].scheduled == "10:00 - 10:20"


def test_sections_numbered_and_nested(workshop):
    ids = [section.id for section in workshop.sections]
    assert ids[:3] == ["1", "2", "2.1"]
    subsection = workshop.section("2.1")
    assert subsection.title == "Job Scheduling"
    assert subsection.level == 2 and subsection.parent_id == "2"


def test_utterances_attributed_with_timestamps_and_lines(workshop):
    first = workshop.utterances[0]
    assert first.speaker_key == "IV" and first.speaker_name == "Idris Vance"
    assert first.timestamp == "10:02"
    assert first.section_id == "1"
    assert first.line > 0
    # every turn is attributed in this transcript
    assert workshop.stats.unattributed_utterances == 0


def test_multi_line_turns_are_joined(workshop):
    rowan = next(u for u in workshop.utterances if u.speaker_key == "RE")
    assert "ninety thousand domestic connections" in rowan.text
    assert "\n" not in rowan.text


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def test_requirements_carry_verbatim_evidence(workshop):
    statements = [r.statement for r in workshop.requirements]
    assert any("move work between engineers by dragging it" in s for s in statements)
    for requirement in workshop.requirements:
        assert requirement.evidence.quote == requirement.statement
        assert requirement.evidence.line > 0
        assert requirement.evidence.speaker_name


def test_priority_read_from_the_words_used(workshop):
    by_priority = {}
    for requirement in workshop.requirements:
        by_priority.setdefault(requirement.priority, []).append(requirement.statement)
    assert any("non-negotiable" in s for s in by_priority.get("must", []))
    assert any("phase two" in s for s in by_priority.get("wont", []))
    assert any("Ideally" in s for s in by_priority.get("could", []))
    # a priority is never asserted without the phrase it was read from
    for requirement in workshop.requirements:
        if requirement.priority != "unclassified":
            assert requirement.priority_cue


def test_non_functional_classification(workshop):
    offline = next(r for r in workshop.requirements if "offline capture is mandatory" in r.statement)
    assert offline.kind == "non_functional"


def test_actions_from_register_with_owner_and_due(workshop):
    by_id = {a.id: a for a in workshop.actions}
    assert set(by_id) == {"A1", "A2", "A3"}
    assert by_id["A1"].owner_key == "KP" and by_id["A1"].owner_name == "Kaya Petrov"
    assert by_id["A1"].due == "By 12 May"
    assert by_id["A3"].due is None  # no date in the register — surfaced, not invented


def test_inline_action_marker_supplies_the_line_it_was_raised_on(workshop):
    a1 = next(a for a in workshop.actions if a.id == "A1")
    # the [ACTION:] marker sits in section 1, well before the end-of-document register
    assert "[ACTION:] marker" in a1.evidence.cue
    assert a1.evidence.section_id == "1"


def test_parked_items_deduplicated_between_marker_and_register(workshop):
    assert [p.id for p in workshop.parked_items] == ["P1", "P2"]
    p1 = workshop.parked_items[0]
    assert p1.evidence.section_id == "2.2"  # provenance from the inline marker


def test_rraid_seeds_categorised_with_evidence(workshop):
    categories = {f.category for f in workshop.findings}
    assert {"risk", "issue", "constraint"} <= categories
    assert any("disaster" in f.statement for f in workshop.findings if f.category == "risk")
    for finding in workshop.findings:
        assert finding.evidence.quote and finding.evidence.line > 0


def test_split_sentences_drops_stage_directions():
    parts = split_sentences("[pause] I'd say the forecast view is a must. The warning is a want.")
    assert parts == ["I'd say the forecast view is a must.", "The warning is a want."]


def test_questions_are_never_requirements(cues):
    rules = CueRules.from_rules(cues)
    assert rules.requirement_cues  # rules actually loaded
    snapshot = parse_transcript(TRANSCRIPTS / "workshop.txt", cues)
    assert all(not r.statement.endswith("?") for r in snapshot.requirements)


# ---------------------------------------------------------------------------
# Other profiles
# ---------------------------------------------------------------------------


def test_teams_txt_export(cues):
    snapshot = parse_transcript(TRANSCRIPTS / "teams_export.txt", cues)
    assert snapshot.meeting.source_format == FORMAT_TEAMS_TXT
    assert {p.name for p in snapshot.participants} == {"Rowan Ellisdale", "Kaya Petrov", "Idris Vance"}
    assert snapshot.utterances[0].timestamp == "0:04"
    assert any("offline capture" in r.statement for r in snapshot.requirements)
    # no attendee block: docgen says so rather than pretending the roles are known
    assert any(w.code == "no_attendee_list" for w in snapshot.warnings)
    assert any(w.code == "no_section_structure" for w in snapshot.warnings)


def test_vtt_merges_consecutive_cues_from_one_speaker(cues):
    snapshot = parse_transcript(TRANSCRIPTS / "teams_meeting.vtt", cues)
    assert snapshot.meeting.source_format == FORMAT_VTT
    # six cues, two pairs of consecutive same-speaker cues → four turns
    assert snapshot.stats.utterance_count == 4
    first = snapshot.utterances[0]
    assert first.speaker_name == "Rowan Ellisdale"
    assert "thanks for joining" in first.text and "follow up on service operations" in first.text
    assert "<v" not in first.text


def test_plain_profile_still_produces_a_snapshot(cues):
    snapshot = parse_transcript(TRANSCRIPTS / "plain_notes.txt", cues)
    assert snapshot.meeting.source_format == FORMAT_PLAIN
    assert snapshot.stats.utterance_count == 3
    assert snapshot.actions and snapshot.actions[0].owner_name == "Kaya"


def test_unreadable_speaker_free_text_never_raises(tmp_path: Path, cues):
    path = tmp_path / "notes.txt"
    path.write_text("Some free-form notes with nobody speaking.\n\nAnother paragraph.\n", encoding="utf-8")
    snapshot = parse_transcript(path, cues)
    assert snapshot.stats.utterance_count == 2
    assert snapshot.stats.unattributed_utterances == 2


def test_empty_transcript_degrades_to_warnings(tmp_path: Path, cues):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    snapshot = parse_transcript(path, cues)
    assert snapshot.utterances == []
    assert any(w.code == "no_dialogue" for w in snapshot.warnings)


def test_utf16_transcript_is_decoded(tmp_path: Path, cues):
    path = tmp_path / "utf16.txt"
    path.write_bytes("Rowan: The billing system stays.\n".encode("utf-16"))
    snapshot = parse_transcript(path, cues)
    assert snapshot.utterances[0].text == "The billing system stays."


# ---------------------------------------------------------------------------
# Snapshot IO
# ---------------------------------------------------------------------------


def test_transcript_snapshot_round_trips_deterministically(workshop, tmp_path: Path):
    path = tmp_path / "transcript-snapshot.json"
    save_transcript_snapshot(workshop, path)
    assert snapshot_kind(path) == "transcript"
    reloaded = load_transcript_snapshot(path)
    assert dump_transcript_snapshot(reloaded) == dump_transcript_snapshot(workshop)
    assert reloaded.stats.utterance_count == workshop.stats.utterance_count


def test_solution_snapshot_is_rejected_by_the_transcript_loader(built_fixtures, tmp_path: Path):
    from docgen.parsers import parse_solution
    from docgen.snapshot.io import save_snapshot

    path = tmp_path / "snapshot.json"
    save_snapshot(parse_solution(built_fixtures / "minimal.zip"), path)
    assert snapshot_kind(path) == "solution"
    with pytest.raises(SnapshotVersionError):
        load_transcript_snapshot(path)


def test_transcript_snapshot_is_rejected_by_the_solution_loader(workshop, tmp_path: Path):
    from docgen.snapshot.io import load_snapshot

    path = tmp_path / "transcript-snapshot.json"
    save_transcript_snapshot(workshop, path)
    with pytest.raises(SnapshotVersionError):
        load_snapshot(path)
