"""Breaking-change heuristics for Dynamics 365 solution diffs.

Every flag carries the metadata evidence it was derived from. "Breaking" here
means: likely to break existing data, integrations, code, or user processes in
a target environment that already runs the old version.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docgen.diffing.engine import Change, FieldChange

_REQUIREMENT_RANK = {"none": 0, "recommended": 1, "required": 2, "system_required": 2}

_REMOVED_COLLECTION_REASONS = {
    "entities": "Table removed — dependent data, code and integrations will break",
    "connection_references": "Connection reference removed — flows bound to it will fail",
    "global_option_sets": "Global choice set removed — columns referencing it will break",
    "plugin_steps": "Plug-in step removed — server-side behaviour changes silently",
    "environment_variables": "Environment variable removed — configuration lookups will fail",
}

_ATTR_ITEM = re.compile(r"attributes\[([^\]]+)\]$")
_ATTR_FIELD = re.compile(r"attributes\[([^\]]+)\]\.(.+)$")
_REL_ITEM = re.compile(r"relationships\[([^\]]+)\]$")
_OPTION_ITEM = re.compile(r"options\[([^\]]+)\]$")


def _flag(reason: str, evidence: str) -> "BreakingFlag":
    from docgen.diffing.engine import BreakingFlag

    return BreakingFlag(reason=reason, evidence=evidence)


def _classify_field_change(change: "Change", fc: "FieldChange") -> list["BreakingFlag"]:
    flags = []
    path = fc.path

    m = _ATTR_ITEM.fullmatch(path)
    if m and fc.new is None:
        flags.append(_flag("Column removed — existing data and references to it are lost",
                           f"{change.key}: {path} removed"))
        return flags

    m = _REL_ITEM.fullmatch(path)
    if m and fc.new is None:
        flags.append(_flag("Relationship removed — related records and queries will break",
                           f"{change.key}: {path} removed"))
        return flags

    # options[...] may be nested (attributes[x].local_option_set.options[1]) — match the tail
    if _OPTION_ITEM.search(path) and fc.new is None:
        flags.append(_flag("Choice value removed — rows holding this value become invalid",
                           f"{change.key}: {path} removed"))
        return flags

    m = _ATTR_FIELD.fullmatch(path)
    if m:
        attribute, field = m.group(1), m.group(2)
        evidence = f"{change.key}.{attribute}: {field} {fc.old!r} -> {fc.new!r}"
        if field == "type":
            flags.append(_flag("Column type changed — data conversion/loss and integration breakage likely", evidence))
        elif field == "requirement_level":
            old_rank = _REQUIREMENT_RANK.get(str(fc.old), 0)
            new_rank = _REQUIREMENT_RANK.get(str(fc.new), 0)
            if new_rank > old_rank:
                flags.append(_flag("Requirement level tightened — existing rows/integrations may fail validation", evidence))
        elif field == "max_length":
            if isinstance(fc.old, int) and isinstance(fc.new, int) and fc.new < fc.old:
                flags.append(_flag("Maximum length reduced — existing longer values will be rejected", evidence))
        elif field == "lookup_targets":
            removed = set(fc.old or []) - set(fc.new or [])
            if removed:
                flags.append(_flag(f"Lookup target(s) removed: {', '.join(sorted(removed))} — "
                                   "existing references to those tables break", evidence))
        return flags

    if change.collection == "cloud_flows" and (path == "trigger" or path.startswith("trigger.")):
        flags.append(_flag("Flow trigger changed — the flow now starts under different conditions",
                           f"{change.key}: {path} {fc.old!r} -> {fc.new!r}"))
    elif change.collection == "plugin_steps" and path in ("message", "primary_entity", "stage"):
        flags.append(_flag("Plug-in step registration changed — server-side behaviour timing/target changed",
                           f"{change.key}: {path} {fc.old!r} -> {fc.new!r}"))
    elif change.collection == "environment_variables" and path == "type":
        flags.append(_flag("Environment variable type changed — consumers parsing the value may fail",
                           f"{change.key}: type {fc.old!r} -> {fc.new!r}"))
    return flags


def classify_change(change: "Change") -> list["BreakingFlag"]:
    flags: list["BreakingFlag"] = []
    if change.kind == "removed":
        reason = _REMOVED_COLLECTION_REASONS.get(change.collection)
        if reason:
            flags.append(_flag(reason, f"{change.collection}[{change.key}] removed"))
        return flags
    if change.kind != "modified":
        return flags
    seen: set[str] = set()
    for fc in change.field_changes:
        for flag in _classify_field_change(change, fc):
            fingerprint = flag.reason + flag.evidence
            if fingerprint not in seen:
                seen.add(fingerprint)
                flags.append(flag)
    return flags
