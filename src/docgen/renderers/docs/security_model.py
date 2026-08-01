"""Security & access model — role × table privilege matrix and field security
profiles. Fully deterministic."""

from __future__ import annotations

import re

from docgen.renderers.base import DocRenderer, RenderContext
from docgen.renderers.docmodel import Document, Paragraph, Section, Table
from docgen.renderers.docs.common import DASH, dash
from docgen.snapshot.models import SecurityRole, Snapshot

# Privilege name → action. D365 idiom: prv{Action}{EntitySchemaName}
_ACTIONS = ("AppendTo", "Append", "Assign", "Create", "Delete", "Read", "Share", "Write")
_LEVEL_ABBR = {"none": DASH, "user": "U", "business_unit": "BU", "parent_child": "P", "organization": "O"}


def _split_privilege(name: str) -> tuple[str, str] | None:
    m = re.fullmatch(r"prv(" + "|".join(_ACTIONS) + r")(\w+)", name)
    if not m:
        return None
    return m.group(1), m.group(2).lower()


def _role_matrix(role: SecurityRole, entity_names: set[str]) -> tuple[Table, list[str]]:
    """(matrix of entity privileges, leftover non-entity privileges)."""
    by_entity: dict[str, dict[str, str]] = {}
    other: list[str] = []
    for priv in role.privileges:
        split = _split_privilege(priv.name)
        if split is None:
            other.append(f"{priv.name} ({priv.level})")
            continue
        action, entity = split
        if entity not in entity_names:
            other.append(f"{priv.name} ({priv.level})")
            continue
        by_entity.setdefault(entity, {})[action] = _LEVEL_ABBR.get(priv.level, priv.level)
    headers = ["Table", "Create", "Read", "Write", "Delete", "Append", "Append To", "Assign", "Share"]
    rows = []
    for entity in sorted(by_entity):
        levels = by_entity[entity]
        rows.append([entity] + [levels.get(a, DASH)
                                for a in ("Create", "Read", "Write", "Delete", "Append", "AppendTo",
                                          "Assign", "Share")])
    return Table(headers=headers, rows=rows), other


class SecurityModelRenderer(DocRenderer):
    key = "security"
    title = "Security & Access Model"

    def build(self, snapshot: Snapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.solution.display_name or snapshot.solution.unique_name}",
                       subtitle=self.subtitle(snapshot))
        entity_names = {e.logical_name for e in snapshot.entities}

        roles_section = Section("Security roles")
        if snapshot.security_roles:
            roles_section.add(Paragraph(
                f"{len(snapshot.security_roles)} role(s) in this solution. Privilege depth: "
                "U = User, BU = Business Unit, P = Parent:Child business units, O = Organization."
            ))
            for role in snapshot.security_roles:
                role_section = Section(role.name)
                if role.description:
                    role_section.add(Paragraph(role.description))
                matrix, other = _role_matrix(role, entity_names)
                if matrix.rows:
                    role_section.add(matrix)
                else:
                    role_section.add(Paragraph("No table privileges over tables in this solution."))
                if other:
                    role_section.add(Section("Other privileges").add(
                        Table(headers=["Privilege"], rows=[[o] for o in other])))
                roles_section.add(role_section)
        else:
            roles_section.add(Paragraph("No security roles in this solution."))
        doc.add(roles_section)

        fsp_section = Section("Field security profiles")
        if snapshot.field_security_profiles:
            for profile in snapshot.field_security_profiles:
                p_section = Section(profile.name)
                if profile.description:
                    p_section.add(Paragraph(profile.description))
                p_section.add(Table(
                    headers=["Table", "Column", "Read", "Create", "Update"],
                    rows=[[perm.entity, perm.attribute,
                           "yes" if perm.can_read else DASH,
                           "yes" if perm.can_create else DASH,
                           "yes" if perm.can_update else DASH]
                          for perm in profile.attribute_permissions],
                ))
                fsp_section.add(p_section)
        else:
            fsp_section.add(Paragraph("No field security profiles in this solution."))
        doc.add(fsp_section)

        secured = [(e.logical_name, a.logical_name)
                   for e in snapshot.entities for a in e.attributes if a.is_secured]
        if secured:
            doc.add(Section("Field-secured columns").add(Table(
                headers=["Table", "Column"],
                rows=[[entity, attribute] for entity, attribute in secured],
            )))
        return doc
