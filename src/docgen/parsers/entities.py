"""Entities, attributes, forms, views and relationships from customizations.xml.

Structure handled (mirroring real solution exports):

  <Entities><Entity>
    <Name LocalizedName="Project">abc_project</Name>
    <EntityInfo><entity Name="abc_project">
      <LocalizedNames/><LocalizedCollectionNames/><Descriptions/>
      <OwnershipTypeMask>1</OwnershipTypeMask> <IsCustomEntity>1</IsCustomEntity>
      <attributes><attribute PhysicalName="abc_name"> ... </attribute></attributes>
    </entity></EntityInfo>
    <FormXml><forms type="main"><systemform>...</systemform></forms></FormXml>
    <SavedQueries><savedqueries><savedquery>...</savedquery></savedqueries></SavedQueries>
  </Entity></Entities>

  <EntityRelationships><EntityRelationship Name="...">...</EntityRelationship></EntityRelationships>
"""

from __future__ import annotations

from lxml import etree

from docgen.parsers.base import (
    ParseContext,
    clean,
    loc_text,
    text,
    to_bool,
    to_float,
    to_int,
)
from docgen.parsers.optionsets import parse_option_el
from docgen.snapshot.models import Attribute, Entity, Form, Relationship, View

TYPE_ENTITY = 1

REQUIREMENT_LEVELS = {
    "none": "none",
    "recommended": "recommended",
    "required": "required",
    "applicationrequired": "required",
    "systemrequired": "system_required",
}

OWNERSHIP_MASKS = {1: "UserOwned", 2: "BusinessOwned", 4: "BusinessParented", 8: "OrganizationOwned"}

VIEW_TYPES = {0: "public", 1: "advanced_find", 2: "associated", 4: "quick_find", 8: "address_book", 16: "main_application", 64: "lookup"}


def _parse_attribute(ctx: ParseContext, el: etree._Element, entity_name: str) -> Attribute | None:
    logical = text(el, "LogicalName") or el.get("PhysicalName", "").lower()
    if not logical:
        ctx.warn("unparsed_element", f"customizations.xml/Entities/{entity_name}", "attribute without a logical name")
        return None

    raw_level = (text(el, "RequiredLevel") or "none").lower()
    requirement = REQUIREMENT_LEVELS.get(raw_level)
    if requirement is None:
        ctx.warn(
            "unrecognised_value",
            f"customizations.xml/Entities/{entity_name}/{logical}",
            f"unknown RequiredLevel {raw_level!r}",
        )
        requirement = raw_level

    local_set = None
    option_set_name = text(el, "OptionSetName")
    inline = el.find("optionset")
    if inline is not None:
        local_set = parse_option_el(inline)

    lookup_targets = [t.text.strip() for t in el.findall("LookupTypes/LookupType") if t.text and t.text.strip()]

    return Attribute(
        logical_name=logical,
        display_name=loc_text(el, "displaynames/displayname"),
        schema_name=el.get("PhysicalName"),
        type=(text(el, "Type") or "").lower(),
        requirement_level=requirement,
        description=clean(loc_text(el, "Descriptions/Description")),
        is_custom=to_bool(text(el, "IsCustomField")),
        max_length=to_int(text(el, "MaxLength")),
        min_value=to_float(text(el, "MinValue")),
        max_value=to_float(text(el, "MaxValue")),
        precision=to_int(text(el, "Accuracy")) if text(el, "Accuracy") is not None else to_int(text(el, "Precision")),
        option_set_name=option_set_name,
        local_option_set=local_set,
        lookup_targets=lookup_targets,
        is_secured=to_bool(text(el, "IsSecured")),
        is_calculated=to_bool(text(el, "IsCalculatedField")) or (text(el, "SourceType") == "1"),
        is_rollup=to_bool(text(el, "IsRollupField")) or (text(el, "SourceType") == "2"),
        audit_enabled=to_bool(text(el, "IsAuditEnabled")),
    )


def _primary_name_attribute(entity_el: etree._Element) -> str | None:
    """Attribute whose DisplayMask contains PrimaryName (the export idiom)."""
    for att in entity_el.findall("attributes/attribute"):
        mask = text(att, "DisplayMask") or ""
        if "PrimaryName" in mask:
            return text(att, "LogicalName") or att.get("PhysicalName", "").lower() or None
    return None


def _parse_forms(ctx: ParseContext, form_xml: etree._Element | None, entity_name: str) -> list[Form]:
    forms: list[Form] = []
    if form_xml is None:
        return forms
    for forms_el in form_xml.findall("forms"):
        form_type = forms_el.get("type") or ""
        for sf in forms_el.findall("systemform"):
            name = loc_text(sf, "LocalizedNames/LocalizedName") or text(sf, "formid") or "(unnamed form)"
            forms.append(
                Form(
                    name=name,
                    form_id=(text(sf, "formid") or "").strip("{}").lower(),
                    form_type=form_type,
                    state=text(sf, "FormActivationState") or text(sf, "formactivationstate"),
                )
            )
    return forms


def _parse_views(ctx: ParseContext, saved_queries: etree._Element | None, entity_name: str) -> list[View]:
    views: list[View] = []
    if saved_queries is None:
        return views
    for sq in saved_queries.findall(".//savedquery"):
        name = loc_text(sq, "LocalizedNames/LocalizedName") or "(unnamed view)"
        query_type = to_int(text(sq, "querytype"))
        columns = []
        layout = sq.find("layoutxml")
        if layout is not None:
            for cell in layout.findall(".//cell"):
                cell_name = cell.get("name")
                if cell_name:
                    columns.append(cell_name)
        views.append(
            View(
                name=name,
                saved_query_id=(text(sq, "savedqueryid") or "").strip("{}").lower(),
                view_type=VIEW_TYPES.get(query_type, str(query_type) if query_type is not None else ""),
                is_default=to_bool(text(sq, "isdefault")),
                columns=columns,
            )
        )
    return views


def parse_entities(ctx: ParseContext, block: etree._Element | None) -> list[Entity]:
    entities: list[Entity] = []
    if block is None:
        return entities
    for entity_block in block.findall("Entity"):
        entity_name = text(entity_block, "Name") or "(unknown)"
        try:
            entity_el = entity_block.find("EntityInfo/entity")
            if entity_el is None:
                ctx.warn("unparsed_element", f"customizations.xml/Entities/{entity_name}", "EntityInfo/entity missing")
                continue
            logical = (entity_el.get("Name") or entity_name).lower()

            attributes = []
            for att_el in entity_el.findall("attributes/attribute"):
                try:
                    parsed = _parse_attribute(ctx, att_el, logical)
                    if parsed is not None:
                        attributes.append(parsed)
                except Exception as exc:
                    ctx.warn("component_error", f"customizations.xml/Entities/{logical}", f"attribute: {exc}")

            ownership_mask = to_int(text(entity_el, "OwnershipTypeMask"))
            name_el = entity_block.find("Name")
            fallback_display = name_el.get("LocalizedName") if name_el is not None else None
            entity = Entity(
                logical_name=logical,
                display_name=loc_text(entity_el, "LocalizedNames/LocalizedName") or fallback_display,
                display_collection_name=loc_text(entity_el, "LocalizedCollectionNames/LocalizedCollectionName"),
                description=clean(loc_text(entity_el, "Descriptions/Description")),
                ownership_type=OWNERSHIP_MASKS.get(ownership_mask, str(ownership_mask) if ownership_mask is not None else None),
                is_custom=to_bool(text(entity_el, "IsCustomEntity")),
                is_activity=to_bool(text(entity_el, "IsActivity")),
                primary_name_attribute=_primary_name_attribute(entity_el),
                attributes=attributes,
                forms=_parse_forms(ctx, entity_block.find("FormXml"), logical),
                views=_parse_views(ctx, entity_block.find("SavedQueries"), logical),
            )
            entities.append(entity)
            ctx.claim(TYPE_ENTITY, logical)
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/Entities/{entity_name}", str(exc))
    return entities


def parse_relationships(ctx: ParseContext, block: etree._Element | None) -> list[Relationship]:
    rels: list[Relationship] = []
    if block is None:
        return rels
    for rel_el in block.findall("EntityRelationship"):
        name = rel_el.get("Name") or "(unnamed)"
        try:
            rel_type_raw = text(rel_el, "EntityRelationshipType") or ""
            if "manytomany" in rel_type_raw.lower().replace(" ", ""):
                rel = Relationship(
                    schema_name=name,
                    type="many_to_many",
                    referenced_entity=(text(rel_el, "FirstEntityName") or "").lower(),
                    referencing_entity=(text(rel_el, "SecondEntityName") or "").lower(),
                    is_custom=to_bool(text(rel_el, "IsCustomRelationship")) or name.split("_")[0].islower(),
                )
            else:
                rel = Relationship(
                    schema_name=name,
                    type="one_to_many",
                    referenced_entity=(text(rel_el, "ReferencedEntityName") or "").lower(),
                    referencing_entity=(text(rel_el, "ReferencingEntityName") or "").lower(),
                    referencing_attribute=(text(rel_el, "ReferencingAttributeName") or None),
                    cascade_delete=text(rel_el, "CascadeDelete"),
                    is_custom=to_bool(text(rel_el, "IsCustomRelationship")),
                )
            rels.append(rel)
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/EntityRelationships/{name}", str(exc))
    return rels


def attach_relationships(ctx: ParseContext, entities: list[Entity], rels: list[Relationship]) -> None:
    """Attach each relationship to exactly one owning entity in the snapshot.

    1:N → the referenced ("one") entity; N:N → whichever of the two entities
    sorts first alphabetically. If the preferred owner isn't in the solution,
    fall back to the other side; if neither is, record a warning (the diff and
    docs would otherwise silently lose it).
    """
    by_name = {e.logical_name: e for e in entities}
    for rel in rels:
        if rel.type == "many_to_many":
            candidates = sorted([rel.referenced_entity, rel.referencing_entity])
        else:
            candidates = [rel.referenced_entity, rel.referencing_entity]
        owner = next((by_name[c] for c in candidates if c in by_name), None)
        if owner is None:
            ctx.warn(
                "relationship_unattached",
                f"customizations.xml/EntityRelationships/{rel.schema_name}",
                f"neither {rel.referenced_entity!r} nor {rel.referencing_entity!r} is in this solution",
            )
            continue
        owner.relationships.append(rel)
