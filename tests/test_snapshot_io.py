from pathlib import Path

import pytest

from docgen.snapshot.io import SnapshotVersionError, dump_snapshot, load_snapshot, save_snapshot
from docgen.snapshot.models import (
    Attribute,
    Entity,
    Option,
    OptionSet,
    ParseWarning,
    RolePrivilege,
    SecurityRole,
    Snapshot,
    SolutionMeta,
)


def _unsorted_snapshot() -> Snapshot:
    return Snapshot(
        generated_at="2026-01-01T00:00:00Z",
        docgen_version="0.1.0",
        solution=SolutionMeta(unique_name="TestSol", version="1.0.0.0"),
        entities=[
            Entity(
                logical_name="zzz_beta",
                attributes=[
                    Attribute(logical_name="zzz_late", type="nvarchar"),
                    Attribute(logical_name="zzz_early", type="nvarchar"),
                ],
            ),
            Entity(logical_name="aaa_alpha"),
        ],
        global_option_sets=[
            OptionSet(name="b_set", is_global=True, options=[Option(value=2, label="Two"), Option(value=1, label="One")]),
            OptionSet(name="a_set", is_global=True),
        ],
        security_roles=[
            SecurityRole(name="Role B", privileges=[RolePrivilege(name="prvB"), RolePrivilege(name="prvA")]),
            SecurityRole(name="Role A"),
        ],
        warnings=[
            ParseWarning(code="z_code", message="later"),
            ParseWarning(code="a_code", message="earlier"),
        ],
    )


def test_round_trip(tmp_path: Path):
    snap = _unsorted_snapshot()
    path = tmp_path / "snapshot.json"
    save_snapshot(snap, path)
    loaded = load_snapshot(path)
    assert loaded.solution.unique_name == "TestSol"
    assert [e.logical_name for e in loaded.entities] == ["aaa_alpha", "zzz_beta"]


def test_canonical_ordering_is_applied_everywhere(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    save_snapshot(_unsorted_snapshot(), path)
    loaded = load_snapshot(path)
    beta = loaded.entities[1]
    assert [a.logical_name for a in beta.attributes] == ["zzz_early", "zzz_late"]
    assert [o.name for o in loaded.global_option_sets] == ["a_set", "b_set"]
    assert [o.value for o in loaded.global_option_sets[1].options] == [1, 2]
    assert [r.name for r in loaded.security_roles] == ["Role A", "Role B"]
    assert [p.name for p in loaded.security_roles[1].privileges] == ["prvA", "prvB"]
    assert [w.code for w in loaded.warnings] == ["a_code", "z_code"]


def test_serialisation_is_byte_stable():
    a = dump_snapshot(_unsorted_snapshot())
    b = dump_snapshot(_unsorted_snapshot())
    assert a == b
    # a canonically-sorted snapshot re-dumped is identical
    snap = _unsorted_snapshot()
    from docgen.snapshot.io import canonicalise

    assert dump_snapshot(canonicalise(snap)) == a


def test_incompatible_schema_version_rejected(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    save_snapshot(_unsorted_snapshot(), path)
    text = path.read_text(encoding="utf-8").replace('"schema_version": "1.0"', '"schema_version": "2.0"')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SnapshotVersionError):
        load_snapshot(path)


def test_unknown_field_in_snapshot_rejected(tmp_path: Path):
    path = tmp_path / "snapshot.json"
    save_snapshot(_unsorted_snapshot(), path)
    text = path.read_text(encoding="utf-8").replace('"generated_at"', '"bogus_field": 1, "generated_at"')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(Exception):
        load_snapshot(path)
