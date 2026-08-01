"""Small formatting helpers shared by doc renderers."""

from __future__ import annotations

from docgen.snapshot.models import Attribute, Entity, Snapshot

DASH = "—"
MISSING_DESCRIPTION = "⚠ No description"

REQUIREMENT_LABELS = {
    "none": "Optional",
    "recommended": "Recommended",
    "required": "Required",
    "system_required": "System required",
}


def dash(value: object) -> str:
    if value is None or value == "" or value == []:
        return DASH
    return str(value)


def requirement(att: Attribute) -> str:
    return REQUIREMENT_LABELS.get(att.requirement_level, att.requirement_level)


def description_cell(description: str | None) -> str:
    """Blank descriptions are flagged visibly, never silently blank."""
    return description if description else MISSING_DESCRIPTION


def attribute_type(att: Attribute) -> str:
    extra = ""
    if att.type == "lookup" and att.lookup_targets:
        extra = f" → {', '.join(att.lookup_targets)}"
    elif att.option_set_name:
        extra = f" ({att.option_set_name})"
    elif att.local_option_set is not None:
        extra = " (local choices)"
    elif att.max_length is not None:
        extra = f" ({att.max_length})"
    return f"{att.type or '?'}{extra}"


def entity_label(entity: Entity) -> str:
    display = entity.display_name or entity.logical_name
    return f"{display} ({entity.logical_name})"


def solution_facts(snapshot: Snapshot) -> list[list[str]]:
    s = snapshot.solution
    return [
        ["Solution", f"{s.display_name or s.unique_name} ({s.unique_name})"],
        ["Version", s.version or DASH],
        ["Type", "Managed" if s.managed else "Unmanaged"],
        ["Publisher", f"{s.publisher.display_name or s.publisher.unique_name} (prefix: {dash(s.publisher.prefix)})"],
        ["Source file", dash(snapshot.source_file)],
        ["Snapshot generated", dash(snapshot.generated_at)],
        ["docgen version", dash(snapshot.docgen_version)],
    ]
