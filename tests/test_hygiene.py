"""Hygiene checks and licensing detection against the rich fixture."""

import pytest

from docgen.config import DocgenConfig
from docgen.hygiene.checks import detect_licensing, run_all_checks
from docgen.parsers import parse_solution
from docgen.rules_io import load_rules


@pytest.fixture(scope="module")
def rich(built_fixtures):
    return parse_solution(built_fixtures / "rich.zip")


@pytest.fixture(scope="module")
def rules():
    return load_rules(DocgenConfig())


def test_missing_description_findings(rich, rules):
    findings = run_all_checks(rich, rules)
    desc = [f for f in findings if f.rule_id == "DESC-002"]
    assert any("abc_project.abc_description" in f.component for f in desc)
    # every finding must state evidence (ground truth only)
    assert all(f.evidence for f in findings)


def test_unmanaged_and_flow_findings(rich, rules):
    findings = run_all_checks(rich, rules)
    assert any(f.rule_id == "MGMT-001" for f in findings)
    flow_findings = [f for f in findings if f.rule_id == "FLOW-001"]
    assert len(flow_findings) == 1
    assert "Sync invoices to SQL" in flow_findings[0].component


def test_unused_option_set_detected(rich, rules):
    findings = run_all_checks(rich, rules)
    unused = [f for f in findings if f.rule_id == "OPT-001"]
    assert len(unused) == 1 and "abc_unused" in unused[0].component


def test_naming_rules_pass_for_conventional_fixture(rich, rules):
    findings = run_all_checks(rich, rules)
    naming = [f for f in findings if f.category == "naming"]
    # rich fixture follows conventions except nothing — expect no naming findings
    assert naming == []


def test_naming_rule_catches_violation(built_fixtures, rules):
    import fixture_builder

    b = fixture_builder.SolutionBuilder("NamingBad", "Naming Bad", prefix="bad")
    ent = b.add_entity("BadEntityName", "Bad Entity")
    ent.add_attribute("bad_name", "Name", primary_name=True)
    b.add_flow("Copy of My Flow", fixture_builder.make_flow_clientdata(
        actions={"Do": fixture_builder.api_action("shared_office365", "SendEmailV2")}))
    path = built_fixtures / "naming_bad.zip"
    b.build(path)
    snap = parse_solution(path)
    findings = run_all_checks(snap, rules)
    ids = {f.rule_id for f in findings if f.category == "naming"}
    assert "NAME-001" in ids  # entity not lowercase-prefixed
    assert "NAME-004" in ids  # "Copy of" flow name


def test_licensing_detection(rich, rules):
    hits, signals = detect_licensing(rich, rules["licensing"])
    by_connector = {h.connector: h for h in hits}
    assert "shared_sql" in by_connector
    assert any("flow: Sync invoices to SQL" in u for u in by_connector["shared_sql"].used_by)
    assert "shared_commondataserviceforapps" in by_connector  # premium (Dataverse)
    assert signals and "Finance API Connector" in signals[0]


def test_dangling_reference_detection(built_fixtures, rules):
    import fixture_builder

    b = fixture_builder.SolutionBuilder("Dangling", "Dangling", prefix="dgl")
    b.add_flow("Orphan flow", fixture_builder.make_flow_clientdata(
        connection_references={"shared_office365": "dgl_missing_ref"},
        actions={"Send": fixture_builder.api_action("shared_office365", "SendEmailV2")}))
    path = built_fixtures / "dangling.zip"
    b.build(path)
    snap = parse_solution(path)
    findings = run_all_checks(snap, rules)
    assert any(f.rule_id == "REF-001" and "dgl_missing_ref" in f.message for f in findings)
