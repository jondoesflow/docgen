"""Snapshot serialisation: canonical ordering, save/load, schema version check.

Sorting happens exclusively here (never in parsers) so that a snapshot saved
twice — or produced by parsers that discovered components in a different
order — is byte-identical. That makes snapshot.json git-diffable and lets the
golden tests compare bytes.

Two snapshot kinds share this module: the solution `Snapshot` (from a solution
zip) and the `TranscriptSnapshot` (from a meeting transcript). They are told
apart on disk by the `kind` discriminator, which only transcript snapshots
carry — see `snapshot_kind` / `load_any`.
"""

from __future__ import annotations

import json
from pathlib import Path

from docgen.snapshot.models import SCHEMA_VERSION, Entity, Snapshot
from docgen.snapshot.transcript import (
    TRANSCRIPT_KIND,
    TRANSCRIPT_SCHEMA_VERSION,
    TranscriptSnapshot,
)

SOLUTION_KIND = "solution"


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
    path.write_text(dump_snapshot(snapshot), encoding="utf-8", newline="\n")


def load_snapshot(path: Path) -> Snapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("kind") == TRANSCRIPT_KIND:
        raise SnapshotVersionError(
            f"{path} is a transcript snapshot, not a solution snapshot. Render it with "
            "`docgen render` (which dispatches on snapshot kind) or the transcript document keys."
        )
    _check_version(data, SCHEMA_VERSION, "`docgen parse` on the solution zip")
    return Snapshot.model_validate(data)


# ---------------------------------------------------------------------------
# Transcript snapshots
# ---------------------------------------------------------------------------


def canonicalise_transcript(snapshot: TranscriptSnapshot) -> TranscriptSnapshot:
    """Only genuinely unordered collections are sorted.

    A transcript's participants, sections and utterances have a meaningful
    document order that is already deterministic, so re-sorting them would
    destroy information without buying determinism. Warnings are the one
    collection assembled out of order, so they are sorted.
    """
    return snapshot.model_copy(
        update={"warnings": sorted(snapshot.warnings, key=lambda w: (w.code, w.context, w.message))}
    )


def dump_transcript_snapshot(snapshot: TranscriptSnapshot) -> str:
    data = canonicalise_transcript(snapshot).model_dump(mode="json")
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def save_transcript_snapshot(snapshot: TranscriptSnapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_transcript_snapshot(snapshot), encoding="utf-8", newline="\n")


def load_transcript_snapshot(path: Path) -> TranscriptSnapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("kind") != TRANSCRIPT_KIND:
        raise SnapshotVersionError(
            f"{path} is a solution snapshot, not a transcript snapshot. Parse a transcript "
            "with `docgen parse <transcript.txt>` first."
        )
    _check_version(data, TRANSCRIPT_SCHEMA_VERSION, "`docgen parse` on the transcript file")
    return TranscriptSnapshot.model_validate(data)


# ---------------------------------------------------------------------------
# Kind dispatch
# ---------------------------------------------------------------------------


def snapshot_kind(path: Path) -> str:
    """`solution` or `transcript`, read from the file's discriminator."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotVersionError(f"{path} is not a readable snapshot JSON file: {exc}") from exc
    if not isinstance(data, dict):
        raise SnapshotVersionError(f"{path} is not a snapshot (expected a JSON object).")
    return TRANSCRIPT_KIND if data.get("kind") == TRANSCRIPT_KIND else SOLUTION_KIND


def load_any(path: Path) -> Snapshot | TranscriptSnapshot:
    """Load whichever snapshot kind the file holds."""
    if snapshot_kind(path) == TRANSCRIPT_KIND:
        return load_transcript_snapshot(path)
    return load_snapshot(path)


def _check_version(data: dict, expected: str, reparse_hint: str) -> None:
    version = str(data.get("schema_version", ""))
    if version.split(".")[0] != expected.split(".")[0]:
        raise SnapshotVersionError(
            f"Snapshot schema version {version!r} is not compatible with this docgen "
            f"(expected {expected.split('.')[0]}.x). Re-run {reparse_hint}."
        )
