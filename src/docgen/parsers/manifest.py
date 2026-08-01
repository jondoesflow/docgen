"""solution.xml parser: solution metadata, publisher, and the RootComponents list."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from docgen.parsers.base import ParseContext, loc_text, text, to_bool, to_int
from docgen.snapshot.models import Publisher, SolutionMeta


@dataclass
class RootComponent:
    type_code: int
    key: str  # schemaName where present, else id (GUID)
    schema_name: str | None
    component_id: str | None


def parse_manifest(ctx: ParseContext) -> tuple[SolutionMeta, list[RootComponent]]:
    root = ctx.read_xml("solution.xml")
    if root is None:
        ctx.warn("missing_file", "solution.xml", "solution.xml not found or unreadable in zip")
        return SolutionMeta(), []

    manifest = root.find("SolutionManifest")
    if manifest is None:
        ctx.warn("unparsed_element", "solution.xml", "SolutionManifest element not found")
        return SolutionMeta(), []

    publisher_el = manifest.find("Publisher")
    publisher = Publisher(
        unique_name=text(publisher_el, "UniqueName", "") or "",
        display_name=loc_text(publisher_el, "LocalizedNames/LocalizedName"),
        prefix=text(publisher_el, "CustomizationPrefix"),
        option_value_prefix=to_int(text(publisher_el, "CustomizationOptionValuePrefix")),
    )

    components: list[RootComponent] = []
    for rc in manifest.findall("RootComponents/RootComponent"):
        type_code = to_int(rc.get("type"))
        schema_name = rc.get("schemaName")
        component_id = rc.get("id")
        key = schema_name or component_id
        if type_code is None or key is None:
            ctx.warn(
                "unparsed_element",
                "solution.xml/RootComponents",
                f"RootComponent missing type or key: {etree.tostring(rc, encoding='unicode').strip()}",
            )
            continue
        components.append(
            RootComponent(
                type_code=type_code,
                key=key,
                schema_name=schema_name,
                component_id=component_id.strip("{}").lower() if component_id else None,
            )
        )

    meta = SolutionMeta(
        unique_name=text(manifest, "UniqueName", "") or "",
        display_name=loc_text(manifest, "LocalizedNames/LocalizedName"),
        version=text(manifest, "Version", "") or "",
        managed=to_bool(text(manifest, "Managed")),
        publisher=publisher,
        root_component_count=len(components),
    )
    return meta, components
