"""Snapshot serialisation: canonical ordering, save/load, schema version check.

Sorting happens exclusively here (never in parsers) so that a snapshot saved
twice — or produced by parsers that discovered components in a different
order — is byte-identical. That makes snapshot.json git-diffable and lets the
golden tests compare bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

from docgen.snapshot.models import SCHEMA_VERSION, Entity, Snapshot


class SnapshotVersionError(ValueError):
    pass


def _sorted_entity(entity: Entity) -> Entity:
    return entity.model_copy(
        update={
            "attributes": sorted(entity.attributes, key=lambda a: a.logical_name),
            "relationships": sorted(entity.relationships, key=lambda r: r.schema_name),
            "forms": sorted(entity.forms, key=lambda f: (f.form_type, f.name, f.form_id)),
            "views": sorted(entity.views, key=lambda v: (v.name, v.saved_query_id)),
            "business_rules": sorted(entity.business_rules, key=lambda b: b.name),
        }
    )


def canonicalise(snapshot: Snapshot) -> Snapshot:
    """Return a copy of the snapshot with every collection in canonical order."""
    return snapshot.model_copy(
        update={
            "entities": sorted((_sorted_entity(e) for e in snapshot.entities), key=lambda e: e.logical_name),
            "global_option_sets": sorted(
                (
                    o.model_copy(update={"options": sorted(o.options, key=lambda opt: opt.value)})
                    for o in snapshot.global_option_sets
                ),
                key=lambda o: o.name,
            ),
            "security_roles": sorted(
                (
                    r.model_copy(update={"privileges": sorted(r.privileges, key=lambda p: p.name)})
                    for r in snapshot.security_roles
                ),
                key=lambda r: r.name,
            ),
            "field_security_profiles": sorted(
                (
                    p.model_copy(
                        update={
                            "attribute_permissions": sorted(
                                p.attribute_permissions, key=lambda fp: (fp.entity, fp.attribute)
                            )
                        }
                    )
                    for p in snapshot.field_security_profiles
                ),
                key=lambda p: p.name,
            ),
            "cloud_flows": sorted(
                (
                    f.model_copy(update={"actions": sorted(f.actions, key=lambda a: a.path)})
                    for f in snapshot.cloud_flows
                ),
                key=lambda f: f.unique_name,
            ),
            "connection_references": sorted(snapshot.connection_references, key=lambda c: c.logical_name),
            "environment_variables": sorted(snapshot.environment_variables, key=lambda v: v.schema_name),
            "plugin_assemblies": sorted(snapshot.plugin_assemblies, key=lambda a: a.name),
            "plugin_steps": sorted(snapshot.plugin_steps, key=lambda s: s.name),
            "web_resources": sorted(snapshot.web_resources, key=lambda w: w.name),
            "custom_connectors": sorted(snapshot.custom_connectors, key=lambda c: c.name),
            "canvas_apps": sorted(snapshot.canvas_apps, key=lambda a: a.name),
            "other_components": sorted(
                snapshot.other_components, key=lambda g: (g.component_type or -1, g.schema_name_or_id)
            ),
            "warnings": sorted(snapshot.warnings, key=lambda w: (w.code, w.context, w.message)),
        }
    )


def dump_snapshot(snapshot: Snapshot) -> str:
    """Canonical JSON text for a snapshot (deterministic bytes)."""
    data = canonicalise(snapshot).model_dump(mode="json")
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def save_snapshot(snapshot: Snapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_snapshot(snapshot), encoding="utf-8")


def load_snapshot(path: Path) -> Snapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = str(data.get("schema_version", ""))
    if version.split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise SnapshotVersionError(
            f"Snapshot schema version {version!r} is not compatible with this docgen "
            f"(expected {SCHEMA_VERSION.split('.')[0]}.x). Re-run `docgen parse` on the solution zip."
        )
    return Snapshot.model_validate(data)
