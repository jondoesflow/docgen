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
