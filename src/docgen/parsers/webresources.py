"""Web resource inventory."""

from __future__ import annotations

from lxml import etree

from docgen.parsers.base import ParseContext, text
from docgen.snapshot.models import WebResource

TYPE_WEB_RESOURCE = 61

_TYPES = {1: "html", 2: "css", 3: "js", 4: "xml", 5: "png", 6: "jpg", 7: "gif",
          8: "silverlight", 9: "xsl", 10: "ico", 11: "svg", 12: "resx"}


def parse_web_resources(ctx: ParseContext, block: etree._Element | None) -> list[WebResource]:
    resources: list[WebResource] = []
    if block is None:
        return resources
    for el in block.findall("WebResource"):
        name = text(el, "Name") or ""
        if not name:
            ctx.warn("unparsed_element", "customizations.xml/WebResources", "WebResource without a Name")
            continue
        try:
            raw_type = text(el, "WebResourceType")
            type_code = int(raw_type) if raw_type and raw_type.isdigit() else None
            resources.append(WebResource(
                name=name,
                display_name=text(el, "DisplayName"),
                type=_TYPES.get(type_code, raw_type or ""),
                description=text(el, "Description"),
            ))
            ctx.claim(TYPE_WEB_RESOURCE, name)
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/WebResources/{name}", str(exc))
    return resources
