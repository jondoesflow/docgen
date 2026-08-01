"""Generic fallback: root components no specialised parser claimed.

This is the "nothing silently dropped" guarantee — every RootComponent in
solution.xml either ends up in a typed snapshot collection or here, with a
warning either way it can be traced from.
"""

from __future__ import annotations

from docgen.parsers.base import ParseContext
from docgen.parsers.manifest import RootComponent
from docgen.snapshot.models import GenericComponent

# RootComponent type codes docgen recognises enough to label. Codes without a
# specialised parser still get a readable label here.
TYPE_LABELS = {
    1: "Entity",
    9: "Option Set",
    10: "Entity Relationship",
    20: "Security Role",
    24: "Form",
    26: "Saved Query",
    29: "Workflow / Cloud Flow",
    31: "Report",
    60: "System Form",
    61: "Web Resource",
    62: "Site Map",
    63: "Connection Role",
    65: "Hierarchy Rule",
    66: "Custom Control",
    70: "Field Security Profile",
    71: "Field Permission",
    80: "Model-driven App",
    90: "Plugin Type",
    91: "Plugin Assembly",
    92: "SDK Message Processing Step",
    93: "SDK Message Processing Step Image",
    95: "Service Endpoint",
    150: "Routing Rule",
    161: "Mobile Offline Profile",
    165: "Similarity Rule",
    300: "Canvas App",
    371: "Connector",
    372: "Connector",
    380: "Environment Variable Definition",
    381: "Environment Variable Value",
    10112: "Connection Reference",
}


def collect_unclaimed(ctx: ParseContext, root_components: list[RootComponent]) -> list[GenericComponent]:
    generics: list[GenericComponent] = []
    for rc in root_components:
        key = rc.schema_name or rc.component_id or rc.key
        if ctx.is_claimed(rc.type_code, rc.key) or (
            rc.component_id and ctx.is_claimed(rc.type_code, rc.component_id)
        ):
            continue
        label = TYPE_LABELS.get(rc.type_code)
        generics.append(
            GenericComponent(
                schema_name_or_id=key,
                component_type=rc.type_code,
                type_label=label,
                source="solution.xml",
                raw_summary={"behavior": "root_component"},
            )
        )
        ctx.warn(
            "unknown_component",
            f"solution.xml/RootComponents type={rc.type_code}",
            f"No specialised parser for {label or f'component type {rc.type_code}'} {key!r}; "
            "captured as a generic inventory entry.",
        )
    return generics
