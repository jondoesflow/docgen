"""Snapshot diff engine: keyed comparison of every collection with field-level
change paths. Nested keyed lists (attributes, options, privileges, actions...)
are re-indexed by their own key, so a change reads like
`entities[abc_project] attributes[abc_code].max_length: 20 -> 10`."""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from docgen.snapshot.models import Snapshot


class FieldChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    old: Any = None
    new: Any = None


class BreakingFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str
    evidence: str


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collection: str
    key: str
    label: str = ""  # display label where available
    kind: str  # added | removed | modified
    field_changes: list[FieldChange] = Field(default_factory=list)
    breaking: list[BreakingFlag] = Field(default_factory=list)


class ChangeSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    solution_name: str = ""
    old_version: str = ""
    new_version: str = ""
    changes: list[Change] = Field(default_factory=list)

    def by_collection(self) -> dict[str, list[Change]]:
        grouped: dict[str, list[Change]] = {}
        for change in self.changes:
            grouped.setdefault(change.collection, []).append(change)
        return grouped

    @property
    def breaking_changes(self) -> list[Change]:
        return [c for c in self.changes if c.breaking]


# Nested list fields re-indexed by their own key during dict comparison.
_KEYED_LISTS: dict[str, Callable[[dict], str]] = {
    "attributes": lambda d: d.get("logical_name", ""),
    "relationships": lambda d: d.get("schema_name", ""),
    "forms": lambda d: f"{d.get('form_type', '')}:{d.get('name', '')}",
    "views": lambda d: d.get("name", ""),
    "business_rules": lambda d: d.get("name", ""),
    "options": lambda d: str(d.get("value", "")),
    "privileges": lambda d: d.get("name", ""),
    "attribute_permissions": lambda d: f"{d.get('entity', '')}.{d.get('attribute', '')}",
    "actions": lambda d: d.get("path", ""),
}

# Top-level snapshot collections: (attribute, key field, label field)
COLLECTIONS: list[tuple[str, str, str | None]] = [
    ("entities", "logical_name", "display_name"),
    ("global_option_sets", "name", "display_name"),
    ("security_roles", "name", None),
    ("field_security_profiles", "name", None),
    ("cloud_flows", "unique_name", "display_name"),
    ("connection_references", "logical_name", "display_name"),
    ("environment_variables", "schema_name", "display_name"),
    ("plugin_assemblies", "name", None),
    ("plugin_steps", "name", None),
    ("web_resources", "name", "display_name"),
    ("custom_connectors", "name", "display_name"),
    ("canvas_apps", "name", "display_name"),
    ("other_components", "schema_name_or_id", "type_label"),
]


def _diff_value(path: str, field_name: str, old: Any, new: Any, out: list[FieldChange]) -> None:
    if old == new:
        return
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            child_path = f"{path}.{key}" if path else key
            _diff_value(child_path, key, old.get(key), new.get(key), out)
        return
    if isinstance(old, list) and isinstance(new, list) and field_name in _KEYED_LISTS:
        key_fn = _KEYED_LISTS[field_name]
        old_by_key = {key_fn(item): item for item in old if isinstance(item, dict)}
        new_by_key = {key_fn(item): item for item in new if isinstance(item, dict)}
        for key in sorted(set(old_by_key) | set(new_by_key)):
            item_path = f"{path}[{key}]"
            if key not in new_by_key:
                out.append(FieldChange(path=item_path, old=old_by_key[key], new=None))
            elif key not in old_by_key:
                out.append(FieldChange(path=item_path, old=None, new=new_by_key[key]))
            else:
                _diff_value(item_path, field_name, old_by_key[key], new_by_key[key], out)
        return
    out.append(FieldChange(path=path, old=old, new=new))


def _diff_item(old: dict, new: dict) -> list[FieldChange]:
    changes: list[FieldChange] = []
    for key in sorted(set(old) | set(new)):
        _diff_value(key, key, old.get(key), new.get(key), changes)
    return changes


def diff_snapshots(old: Snapshot, new: Snapshot) -> ChangeSet:
    from docgen.diffing.breaking import classify_change
    from docgen.snapshot.io import canonicalise

    old = canonicalise(old)
    new = canonicalise(new)
    changes: list[Change] = []

    for collection, key_field, label_field in COLLECTIONS:
        old_items = {getattr(item, key_field): item for item in getattr(old, collection)}
        new_items = {getattr(item, key_field): item for item in getattr(new, collection)}

        def label_of(item) -> str:
            if label_field:
                return getattr(item, label_field) or ""
            return ""

        for key in sorted(set(old_items) | set(new_items)):
            if key not in new_items:
                change = Change(collection=collection, key=key, label=label_of(old_items[key]), kind="removed")
            elif key not in old_items:
                change = Change(collection=collection, key=key, label=label_of(new_items[key]), kind="added")
            else:
                field_changes = _diff_item(old_items[key].model_dump(mode="json"),
                                           new_items[key].model_dump(mode="json"))
                if not field_changes:
                    continue
                change = Change(collection=collection, key=key, label=label_of(new_items[key]),
                                kind="modified", field_changes=field_changes)
            change.breaking = classify_change(change)
            changes.append(change)

    return ChangeSet(
        solution_name=new.solution.display_name or new.solution.unique_name,
        old_version=old.solution.version,
        new_version=new.solution.version,
        changes=changes,
    )
