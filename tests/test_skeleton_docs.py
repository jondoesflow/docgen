"""HLD / Integration Design / RRAID skeletons in --no-llm mode, plus the
milestone-6 gate: `docgen all --no-llm` clean end-to-end offline on all fixtures."""

from pathlib import Path

import pytest

from docgen.commands import render_documents, run_all
from docgen.config import DocgenConfig
from docgen.constants import ALL_DOC_KEYS
from docgen.parsers import parse_solution
from docgen.renderers.docmodel import PLACEHOLDER_TEXT


@pytest.fixture(scope="module")
def rich(built_fixtures):
    return parse_solution(built_fixtures / "rich.zip")


@pytest.fixture(scope="module")
def minimal(built_fixtures):
    return parse_solution(built_fixtures / "minimal.zip")


def test_hld_skeleton_offline(rich, tmp_path: Path):
    render_documents(rich, ["hld"], ["md"], tmp_path, DocgenConfig(), no_llm=True)
    text = (tmp_path / "hld.md").read_text(encoding="utf-8")
    assert "# High-Level Design — Rich CE Solution" in text
    # deterministic skeleton content
    assert "Functional areas" in text and "Architecture" in text
    assert "erDiagram" in text
    # every narrative slot is a visible placeholder offline
    assert text.count(PLACEHOLDER_TEXT) >= 5
    # per-flow plain-English description slots exist
    assert "Notify PM on project creation" in text


def test_integration_doc_with_integrations(rich, tmp_path: Path):
    render_documents(rich, ["integration"], ["md"], tmp_path, DocgenConfig(), no_llm=True)
    text = (tmp_path / "integration.md").read_text(encoding="utf-8")
    assert "Integration inventory" in text
    assert "shared_sql" in text
    assert "abc_financeapi" in text
    assert "Endpoints & environments" in text
    assert "Authentication & authorisation" in text
    assert PLACEHOLDER_TEXT in text


def test_integration_doc_without_integrations(minimal, tmp_path: Path):
    render_documents(minimal, ["integration"], ["md"], tmp_path, DocgenConfig(), no_llm=True)
    text = (tmp_path / "integration.md").read_text(encoding="utf-8")
    assert "No integrations detected" in text
    assert "Integration inventory" not in text


def test_rraid_seeds_state_evidence(rich, tmp_path: Path):
    render_documents(rich, ["rraid"], ["md"], tmp_path, DocgenConfig(), no_llm=True)
    text = (tmp_path / "rraid.md").read_text(encoding="utf-8")
    # premium licensing exposure seeded as risk with evidence
    assert "Premium connector SQL Server" in text
    assert "Sync invoices to SQL" in text
    # flow without error handling seeded
    assert "has_error_scope = false" in text
    # unmanaged solution seeded
    assert "solution.managed = false" in text
    # dependency seeds: connection references + secret env var
    assert "abc_dataverse" in text
    assert "abc_ApiKey" in text
    # structured human-judgement sections present
    for heading in ("Risks", "Assumptions", "Issues", "Dependencies"):
        assert heading in text
    assert text.count(PLACEHOLDER_TEXT) >= 4


@pytest.mark.parametrize("fixture_name", ["minimal", "rich", "diff_v1", "diff_v2"])
def test_gate_docgen_all_offline(fixture_name, built_fixtures, tmp_path: Path, monkeypatch):
    """Milestone-6 gate: full pipeline offline for every fixture, all docs, both formats.

    Network access is stubbed out to prove nothing in the --no-llm path needs it.
    """
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("offline gate violated: network access attempted")

    monkeypatch.setattr(socket.socket, "connect", no_network)

    out = tmp_path / fixture_name
    run_all(built_fixtures / f"{fixture_name}.zip", list(ALL_DOC_KEYS), ["md", "docx"],
            out, DocgenConfig(), no_llm=True)

    assert (out / "snapshot.json").is_file()
    assert (out / "parse-warnings.md").is_file()
    snap = parse_solution(built_fixtures / f"{fixture_name}.zip")
    from docgen.renderers import DOC_RENDERERS

    for key in ALL_DOC_KEYS:
        for ext in ("md", "docx"):
            path = out / f"{key}.{ext}"
            assert path.is_file(), f"{path.name} missing from `docgen all` output"
            assert path.stat().st_size > 0
