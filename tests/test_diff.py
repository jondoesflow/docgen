"""Diff engine + breaking heuristics + release notes over the v1/v2 fixture pair."""

from pathlib import Path

import pytest

from docgen.diffing.engine import diff_snapshots
from docgen.parsers import parse_solution
from docgen.renderers.docs.release_notes import build_release_notes
from docgen.renderers.markdown import emit_markdown


@pytest.fixture(scope="module")
def changeset(built_fixtures):
    old = parse_solution(built_fixtures / "diff_v1.zip")
    new = parse_solution(built_fixtures / "diff_v2.zip")
    return diff_snapshots(old, new)


def _by_key(changeset, collection):
    return {c.key: c for c in changeset.changes if c.collection == collection}


def test_versions_and_added_entity(changeset):
    assert changeset.old_version == "1.0.0.0"
    assert changeset.new_version == "2.0.0.0"
    entities = _by_key(changeset, "entities")
    assert entities["dif_invoice"].kind == "added"


def test_removed_attribute_is_breaking(changeset):
    client = _by_key(changeset, "entities")["dif_client"]
    assert client.kind == "modified"
    removed = [fc for fc in client.field_changes if fc.path == "attributes[dif_notes]"]
    assert removed and removed[0].new is None
    assert any("Column removed" in f.reason for f in client.breaking)


def test_requirement_tightened_and_max_length_reduced(changeset):
    client = _by_key(changeset, "entities")["dif_client"]
    paths = {fc.path: fc for fc in client.field_changes}
    assert paths["attributes[dif_code].requirement_level"].new == "required"
    assert paths["attributes[dif_code].max_length"].new == 10
    reasons = " | ".join(f.reason for f in client.breaking)
    assert "Requirement level tightened" in reasons
    assert "Maximum length reduced" in reasons


def test_option_value_removed_is_breaking(changeset):
    client = _by_key(changeset, "entities")["dif_client"]
    option_changes = [fc for fc in client.field_changes if "options[1]" in fc.path]
    assert option_changes and option_changes[0].new is None
    assert any("Choice value removed" in f.reason for f in client.breaking)


def test_type_change_is_breaking(changeset):
    contract = _by_key(changeset, "entities")["dif_contract"]
    type_change = next(fc for fc in contract.field_changes if fc.path == "attributes[dif_value].type")
    assert (type_change.old, type_change.new) == ("money", "decimal")
    assert any("Column type changed" in f.reason for f in contract.breaking)


def test_requirement_tightening_recommended_to_required_flagged(changeset):
    contract = _by_key(changeset, "entities")["dif_contract"]
    assert any("Requirement level tightened" in f.reason
               and "dif_clientid" in f.evidence for f in contract.breaking)


def test_flow_trigger_change_is_breaking(changeset):
    flows = _by_key(changeset, "cloud_flows")
    assert len(flows) == 1
    flow = next(iter(flows.values()))
    assert any("Flow trigger changed" in f.reason for f in flow.breaking)


def test_env_var_default_change_not_breaking(changeset):
    env = _by_key(changeset, "environment_variables")["dif_Endpoint"]
    assert env.kind == "modified"
    assert env.breaking == []


def test_release_notes_markdown(changeset, tmp_path: Path):
    doc = build_release_notes(changeset)
    text = emit_markdown(doc)
    assert "Release Notes — Diff Test Solution" in text
    assert "v1.0.0.0 -> v2.0.0.0" in text
    assert "Breaking-change candidates" in text
    assert "dif_invoice" in text
    assert "Tables (schema changes)" in text
    assert "BREAKING" in text


def test_identical_snapshots_produce_no_changes(built_fixtures):
    snap = parse_solution(built_fixtures / "diff_v1.zip")
    changeset = diff_snapshots(snap, snap)
    assert changeset.changes == []
    text = emit_markdown(build_release_notes(changeset))
    assert "No component changes detected" in text


def test_cli_diff_outputs(built_fixtures, tmp_path: Path):
    from docgen.commands import run_diff, run_parse
    from docgen.config import DocgenConfig

    old_snap = run_parse(built_fixtures / "diff_v1.zip", tmp_path / "v1")
    new_snap = run_parse(built_fixtures / "diff_v2.zip", tmp_path / "v2")
    run_diff(old_snap, new_snap, ["md", "docx"], tmp_path / "diff", DocgenConfig())
    assert (tmp_path / "diff" / "release-notes.md").is_file()
    assert (tmp_path / "diff" / "release-notes.docx").is_file()
    assert (tmp_path / "diff" / "changed-components.json").is_file()
