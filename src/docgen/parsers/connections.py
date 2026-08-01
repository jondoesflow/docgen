"""Connection references and environment variables."""

from __future__ import annotations

from lxml import etree

from docgen.parsers.base import ParseContext, text
from docgen.snapshot.models import ConnectionReference, EnvironmentVariable

TYPE_CONNECTION_REFERENCE = 10112
TYPE_ENV_VAR_DEFINITION = 380

_ENV_TYPES = {
    100000000: "string",
    100000001: "number",
    100000002: "boolean",
    100000003: "json",
    100000004: "data_source",
    100000005: "secret",
}


def parse_connection_references(ctx: ParseContext, block: etree._Element | None) -> list[ConnectionReference]:
    refs: list[ConnectionReference] = []
    if block is None:
        return refs
    for el in block.findall("connectionreference"):
        logical = el.get("connectionreferencelogicalname") or ""
        if not logical:
            ctx.warn("unparsed_element", "customizations.xml/connectionreferences",
                     "connectionreference without a logical name")
            continue
        try:
            connector_id = text(el, "connectorid")
            api_name = connector_id.rstrip("/").rsplit("/", 1)[-1] if connector_id else None
            refs.append(ConnectionReference(
                logical_name=logical,
                display_name=text(el, "connectionreferencedisplayname"),
                connector_id=connector_id,
                api_name=api_name,
            ))
            ctx.claim(TYPE_CONNECTION_REFERENCE, logical)
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/connectionreferences/{logical}", str(exc))
    return refs


def parse_environment_variables(ctx: ParseContext, block: etree._Element | None) -> list[EnvironmentVariable]:
    variables: list[EnvironmentVariable] = []
    if block is None:
        return variables
    for el in block.findall("environmentvariabledefinition"):
        schema = el.get("schemaname") or ""
        if not schema:
            ctx.warn("unparsed_element", "customizations.xml/EnvironmentVariables",
                     "environmentvariabledefinition without a schemaname")
            continue
        try:
            display_el = el.find("displayname")
            description_el = el.find("description")
            raw_type = text(el, "type")
            type_code = int(raw_type) if raw_type and raw_type.isdigit() else None
            type_name = _ENV_TYPES.get(type_code, raw_type or "")
            current_value = None
            value_el = el.find("environmentvariablevalues/environmentvariablevalue/value")
            if value_el is not None and value_el.text:
                current_value = value_el.text.strip()
            variables.append(EnvironmentVariable(
                schema_name=schema,
                display_name=display_el.get("default") if display_el is not None else None,
                description=description_el.get("default") if description_el is not None else None,
                type=type_name,
                default_value=text(el, "defaultvalue"),
                current_value=current_value,
                is_secret=type_name == "secret",
            ))
            ctx.claim(TYPE_ENV_VAR_DEFINITION, schema)
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/EnvironmentVariables/{schema}", str(exc))
    return variables
