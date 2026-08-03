"""LLM tier tests — all mocked, no network. Includes the mission-mandated test:
a mocked response naming a non-existent entity is rejected."""

from pathlib import Path

import pytest

from docgen.commands import render_documents
from docgen.config import DocgenConfig
from docgen.llm import make_narrative_provider
from docgen.llm.redact import Redactor
from docgen.llm.validate import collect_component_names, extract_candidates, find_violations
from docgen.parsers import parse_solution
from docgen.renderers.docmodel import PLACEHOLDER_TEXT


@pytest.fixture(scope="module")
def rich(built_fixtures):
    return parse_solution(built_fixtures / "rich.zip")


@pytest.fixture(scope="module")
def names(rich):
    return collect_component_names(rich)


class FakeClient:
    """Stands in for LlmClient; returns queued responses and records prompts."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, purpose: str, system: str, user: str) -> str:
        self.calls.append((purpose, user))
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_names_cover_snapshot_components(names):
    for expected in ("abc_project", "abc_task", "project", "shared_sql", "abc_dataverse",
                     "project manager", "abc_apikey"):
        assert expected in names


def test_candidate_extraction():
    text = "The `abc_project` table links to abc_task via lookup. Plain words stay out."
    candidates = extract_candidates(text)
    assert "abc_project" in candidates and "abc_task" in candidates
    assert "plain" not in candidates


def test_valid_response_passes(names):
    text = "The abc_project table tracks engagements; abc_task records work items."
    assert find_violations(text, names) == []


def test_nonexistent_entity_rejected(names):
    """Mission-mandated: a response naming a non-existent entity must be rejected."""
    text = "The abc_project table syncs nightly to the xyz_warehouse entity."
    violations = find_violations(text, names)
    assert violations == ["xyz_warehouse"]


def test_near_miss_close_names_accepted(names):
    # trivial case drift should not reject
    assert find_violations("See `ABC_Project` for details.", names) == []


# ---------------------------------------------------------------------------
# Provider behaviour: retry then placeholder fallback
# ---------------------------------------------------------------------------


def test_provider_returns_valid_prose(rich, tmp_path: Path):
    client = FakeClient(["The abc_project table is the core of the solution."])
    provider = make_narrative_provider(rich, DocgenConfig(), tmp_path, client=client)
    prose = provider("hld_overview", {"entities": ["abc_project"]})
    assert prose == "The abc_project table is the core of the solution."
    assert len(client.calls) == 1


def test_provider_retries_on_violation_then_succeeds(rich, tmp_path: Path):
    client = FakeClient([
        "Data flows into the xyz_warehouse entity.",  # invented → rejected
        "Data is managed in the abc_project table.",  # valid retry
    ])
    provider = make_narrative_provider(rich, DocgenConfig(), tmp_path, client=client)
    prose = provider("hld_overview", {"entities": ["abc_project"]})
    assert prose == "Data is managed in the abc_project table."
    assert len(client.calls) == 2
    assert "xyz_warehouse" in client.calls[1][1]  # retry prompt names the violation


def test_provider_falls_back_to_none_after_two_failures(rich, tmp_path: Path):
    client = FakeClient([
        "Syncs to xyz_warehouse.",
        "Still syncing to xyz_warehouse.",
    ])
    provider = make_narrative_provider(rich, DocgenConfig(), tmp_path, client=client)
    assert provider("hld_overview", {}) is None


def test_provider_survives_client_exception(rich, tmp_path: Path):
    class ExplodingClient:
        def complete(self, *args):
            raise RuntimeError("api down")

    provider = make_narrative_provider(rich, DocgenConfig(), tmp_path, client=ExplodingClient())
    assert provider("hld_overview", {}) is None


def test_missing_api_key_degrades_to_placeholders(rich, tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = make_narrative_provider(rich, DocgenConfig(), tmp_path)  # no client injected
    assert provider("hld_overview", {}) is None


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_redaction_applied_and_reversed(rich, tmp_path: Path):
    redact_file = tmp_path / "redact.yaml"
    redact_file.write_text(
        "replacements:\n  - match: 'Rich CE Solution'\n    replace: 'ClientA Solution'\n"
        "patterns:\n  - regex: '[\\w.]+@[\\w.]+'\n    replace: '[EMAIL]'\n",
        encoding="utf-8",
    )
    cfg = DocgenConfig(redact_file=redact_file)
    client = FakeClient(["The ClientA Solution manages the abc_project table."])
    provider = make_narrative_provider(rich, cfg, tmp_path, client=client)
    prose = provider("hld_overview", {"solution": "Rich CE Solution", "contact": "pm@contoso.com"})

    sent = client.calls[0][1]
    assert "Rich CE Solution" not in sent and "ClientA Solution" in sent  # redacted before sending
    assert "pm@contoso.com" not in sent and "[EMAIL]" in sent
    assert prose == "The Rich CE Solution manages the abc_project table."  # un-redacted locally
    log = (tmp_path / "redaction-log.md").read_text(encoding="utf-8")
    assert "ClientA Solution" in log and "[EMAIL]" in log


def test_redactor_no_rules_logs_cleanly(tmp_path: Path):
    redactor = Redactor.from_file(None)
    assert redactor.redact("unchanged text") == "unchanged text"
    redactor.write_log(tmp_path)
    assert "No redaction rules configured" in (tmp_path / "redaction-log.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# End-to-end: narrative lands in the rendered document
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Transcript narrative: attribution is the ground truth
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def workshop():
    from docgen.config import DocgenConfig as _Config
    from docgen.rules_io import load_rules
    from docgen.transcripts import parse_transcript

    cues = load_rules(_Config()).get("transcript_cues", {})
    return parse_transcript(Path(__file__).parent / "fixtures" / "transcripts" / "workshop.txt", cues)


@pytest.fixture(scope="module")
def people(workshop):
    from docgen.llm.validate import collect_participant_names

    return collect_participant_names(workshop)


def test_participant_names_cover_every_form(people):
    for expected in ("rowan ellisdale", "rowan", "ellisdale", "re", "kaya petrov", "idris vance"):
        assert expected in people


def test_attribution_to_a_real_participant_passes(people):
    from docgen.llm.validate import find_attribution_violations

    text = ("Rowan Ellisdale set out the visibility problem, and Kaya Petrov raised the "
            "volume of status calls. According to Idris Vance, offline capture is the "
            "larger technical risk.")
    assert find_attribution_violations(text, people) == []


def test_attribution_to_someone_not_in_the_meeting_is_rejected(people):
    """The transcript equivalent of the invented-component test: prose may not put
    words in the mouth of somebody who was not in the room."""
    from docgen.llm.validate import find_attribution_violations

    text = "Rowan Ellisdale set out the drivers, and Harriet Wolstenholme confirmed the budget."
    assert find_attribution_violations(text, people) == ["Harriet Wolstenholme"]


def test_prose_without_attribution_is_never_flagged(people):
    from docgen.llm.validate import find_attribution_violations

    text = ("The session covered scheduling, notifications and constraints. The billing "
            "system stays in place and must be integrated with rather than replaced.")
    assert find_attribution_violations(text, people) == []


def test_transcript_provider_retries_then_falls_back(workshop, tmp_path: Path):
    from docgen.llm import make_transcript_narrative_provider

    client = FakeClient([
        "Harriet Wolstenholme confirmed the scope.",
        "Ingrid Halloway confirmed the scope.",
    ])
    provider = make_transcript_narrative_provider(workshop, DocgenConfig(), tmp_path, client=client)
    assert provider("meeting_summary", {"sections": []}) is None
    assert len(client.calls) == 2
    assert "Harriet Wolstenholme" in client.calls[1][1]  # retry names the violation


def test_transcript_provider_returns_valid_prose(workshop, tmp_path: Path):
    from docgen.llm import make_transcript_narrative_provider

    client = FakeClient(["Rowan Ellisdale set out the visibility problem."])
    provider = make_transcript_narrative_provider(workshop, DocgenConfig(), tmp_path, client=client)
    assert provider("meeting_summary", {}) == "Rowan Ellisdale set out the visibility problem."


def test_transcript_payload_is_redacted_before_sending(workshop, tmp_path: Path):
    """A transcript is almost entirely client names — redaction must apply here too."""
    from docgen.llm import make_transcript_narrative_provider

    redact_file = tmp_path / "redact.yaml"
    redact_file.write_text(
        "replacements:\n  - match: 'Northgate Utilities plc'\n    replace: 'ClientA'\n",
        encoding="utf-8",
    )
    cfg = DocgenConfig(redact_file=redact_file)
    client = FakeClient(["ClientA runs field maintenance across the region."])
    provider = make_transcript_narrative_provider(workshop, cfg, tmp_path, client=client)
    prose = provider("meeting_summary", {"client": "Northgate Utilities plc"})

    sent = client.calls[0][1]
    assert "Northgate Utilities plc" not in sent and "ClientA" in sent
    assert prose == "Northgate Utilities plc runs field maintenance across the region."


def test_rendered_meeting_notes_use_llm_narrative_when_valid(workshop, tmp_path: Path, monkeypatch):
    from docgen.commands import render_transcript_documents

    def fake_provider_factory(snapshot, cfg, out_dir):
        return lambda purpose, payload: "Rowan Ellisdale set out the drivers for change."

    import docgen.llm

    monkeypatch.setattr(docgen.llm, "make_transcript_narrative_provider", fake_provider_factory)
    render_transcript_documents(workshop, ["meeting-notes"], ["md"], tmp_path,
                                DocgenConfig(), no_llm=False)
    text = (tmp_path / "meeting-notes.md").read_text(encoding="utf-8")
    assert "Rowan Ellisdale set out the drivers for change." in text


def test_rendered_hld_uses_llm_narrative_when_valid(rich, tmp_path: Path, monkeypatch):
    calls = {"n": 0}

    def fake_provider_factory(snapshot, cfg, out_dir):
        def provider(purpose, payload):
            calls["n"] += 1
            return "Narrative drafted from metadata about the abc_project table."
        return provider

    import docgen.llm

    monkeypatch.setattr(docgen.llm, "make_narrative_provider", fake_provider_factory)
    render_documents(rich, ["hld"], ["md"], tmp_path, DocgenConfig(), no_llm=False)
    text = (tmp_path / "hld.md").read_text(encoding="utf-8")
    assert "Narrative drafted from metadata" in text
    assert calls["n"] > 0
    assert PLACEHOLDER_TEXT not in text.split("Automation")[0]  # overview narrative filled
