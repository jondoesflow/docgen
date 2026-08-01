"""Golden snapshot tests: fixture zip → snapshot must byte-match committed JSON.

Regenerate goldens after intentional parser/schema changes with:
    pytest --update-goldens
"""

from pathlib import Path

import pytest

from docgen.parsers import parse_solution
from docgen.snapshot.io import dump_snapshot

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"

GOLDEN_CASES = ["minimal", "rich", "diff_v1", "diff_v2"]


def normalised_dump(snapshot) -> str:
    """Snapshot JSON with run-varying fields zeroed for comparison."""
    return dump_snapshot(snapshot.model_copy(update={"generated_at": "", "docgen_version": ""}))


@pytest.mark.parametrize("name", GOLDEN_CASES)
def test_golden_snapshot(name: str, fixtures_dir: Path, update_goldens: bool):
    zip_path = fixtures_dir / f"{name}.zip"
    snapshot = parse_solution(zip_path)
    actual = normalised_dump(snapshot)

    golden_path = GOLDEN_DIR / f"{name}.snapshot.json"
    if update_goldens:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(actual, encoding="utf-8", newline="\n")
        pytest.skip(f"golden updated: {golden_path.name}")

    assert golden_path.is_file(), (
        f"Golden file missing: {golden_path}. Run `pytest --update-goldens` to create it."
    )
    expected = golden_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == expected, (
        f"Snapshot for {name} differs from golden. If the change is intentional, "
        "run `pytest --update-goldens` and review the golden diff in git."
    )


def test_parse_is_deterministic(fixtures_dir: Path):
    a = normalised_dump(parse_solution(fixtures_dir / "rich.zip"))
    b = normalised_dump(parse_solution(fixtures_dir / "rich.zip"))
    assert a == b


def test_minimal_content(fixtures_dir: Path):
    snap = parse_solution(fixtures_dir / "minimal.zip")
    assert snap.solution.unique_name == "MinimalSolution"
    assert snap.solution.version == "1.0.0.0"
    assert snap.solution.managed is False
    assert snap.solution.publisher.prefix == "min"
    assert [e.logical_name for e in snap.entities] == ["min_widget"]
    widget = snap.entities[0]
    assert widget.primary_name_attribute == "min_name"
    names = sorted(a.logical_name for a in widget.attributes)
    assert names == ["min_name", "min_size"]
    name_attr = next(a for a in widget.attributes if a.logical_name == "min_name")
    assert name_attr.requirement_level == "system_required"
    assert name_attr.max_length == 100


def test_rich_entities_and_relationships(fixtures_dir: Path):
    snap = parse_solution(fixtures_dir / "rich.zip")
    by_name = {e.logical_name: e for e in snap.entities}
    assert set(by_name) == {"abc_project", "abc_task", "abc_employee", "abc_invoice"}

    project = by_name["abc_project"]
    # 1:N owned by the referenced entity; N:N owned by the first-alphabetical entity
    assert {r.schema_name for r in project.relationships} == {"abc_project_task"}
    employee_rels = {r.schema_name for r in by_name["abc_employee"].relationships}
    assert employee_rels == {"abc_project_employee"}
    nn = next(r for r in by_name["abc_employee"].relationships if r.type == "many_to_many")
    assert {nn.referenced_entity, nn.referencing_entity} == {"abc_project", "abc_employee"}

    task = by_name["abc_task"]
    lookup = next(a for a in task.attributes if a.logical_name == "abc_projectid")
    assert lookup.lookup_targets == ["abc_project"]
    assert lookup.requirement_level == "required"
    priority = next(a for a in task.attributes if a.logical_name == "abc_priority")
    assert priority.local_option_set is not None
    assert [o.label for o in priority.local_option_set.options] == ["Low", "Medium", "High"]

    salary = next(a for a in by_name["abc_employee"].attributes if a.logical_name == "abc_salary")
    assert salary.is_secured is True

    assert [o.name for o in snap.global_option_sets] == ["abc_projectstatus", "abc_unused"]
    status = snap.global_option_sets[0]
    assert status.is_global and len(status.options) == 4

    # description deliberately missing on abc_description → None, visible to hygiene
    desc_attr = next(a for a in project.attributes if a.logical_name == "abc_description")
    assert desc_attr.description is None

    # forms and views
    assert {f.form_type for f in project.forms} == {"main", "quickcreate"}
    active = next(v for v in project.views if v.name == "Active Projects")
    assert active.is_default and active.columns == ["abc_name", "abc_status", "abc_budget"]
    lookup_view = next(v for v in project.views if v.name == "Project Lookup")
    assert lookup_view.view_type == "lookup"


def test_rich_unclaimed_components_and_warnings(fixtures_dir: Path):
    """Families without a parser yet must surface as generics + warnings, never vanish."""
    snap = parse_solution(fixtures_dir / "rich.zip")
    generics = {g.schema_name_or_id: g for g in snap.other_components}
    # the deliberately-unknown component type is captured
    assert "abc_mystery_component" in generics
    assert generics["abc_mystery_component"].component_type == 9999
    warning_codes = {w.code for w in snap.warnings}
    assert "unknown_component" in warning_codes
