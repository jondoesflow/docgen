"""Canvas apps and custom connectors — inventory level only (v1 does not open
.msapp internals)."""

from __future__ import annotations

from lxml import etree

from docgen.parsers.base import ParseContext, text
from docgen.snapshot.models import CanvasApp, CustomConnector

TYPE_CANVAS_APP = 300
TYPE_CONNECTOR_A = 371
TYPE_CONNECTOR_B = 372


def parse_canvas_apps(ctx: ParseContext, block: etree._Element | None) -> list[CanvasApp]:
    apps: list[CanvasApp] = []
    if block is None:
        return apps
    for el in block.findall("CanvasApp"):
        name = text(el, "Name") or ""
        if not name:
            ctx.warn("unparsed_element", "customizations.xml/CanvasApps", "CanvasApp without a Name")
            continue
        try:
            connections_raw = text(el, "Connections") or ""
            apps.append(CanvasApp(
                name=name,
                display_name=text(el, "DisplayName"),
                connections=sorted(c.strip() for c in connections_raw.split(",") if c.strip()),
            ))
            ctx.claim(TYPE_CANVAS_APP, name)
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/CanvasApps/{name}", str(exc))
    return apps


def parse_custom_connectors(ctx: ParseContext, block: etree._Element | None) -> list[CustomConnector]:
    connectors: list[CustomConnector] = []
    if block is None:
        return connectors
    for el in block.findall("Connector"):
        name = text(el, "Name") or ""
        if not name:
            ctx.warn("unparsed_element", "customizations.xml/Connectors", "Connector without a Name")
            continue
        try:
            connectors.append(CustomConnector(
                name=name,
                display_name=text(el, "DisplayName"),
                description=text(el, "Description"),
            ))
            ctx.claim(TYPE_CONNECTOR_A, name)
            ctx.claim(TYPE_CONNECTOR_B, name)
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/Connectors/{name}", str(exc))
    return connectors
