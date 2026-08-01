"""Data dictionary — every table and column, with blank descriptions flagged."""

from __future__ import annotations

from docgen.renderers.base import DocRenderer, RenderContext
from docgen.renderers.docmodel import Callout, Document, Paragraph, Section, Table
from docgen.renderers.docs.common import (
    DASH,
    MISSING_DESCRIPTION,
    attribute_type,
    dash,
    description_cell,
    entity_label,
    requirement,
)
from docgen.snapshot.models import Snapshot


class DataDictionaryRenderer(DocRenderer):
    key = "data-dictionary"
    title = "Data Dictionary"

    def build(self, snapshot: Snapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.solution.display_name or snapshot.solution.unique_name}",
                       subtitle=self.subtitle(snapshot))

        total_columns = sum(len(e.attributes) for e in snapshot.entities)
        missing = sum(1 for e in snapshot.entities for a in e.attributes if not a.description)
        missing_tables = sum(1 for e in snapshot.entities if not e.description)
        intro = Section("Coverage")
        intro.add(Paragraph(
            f"{len(snapshot.entities)} tables, {total_columns} columns. "
            f"Columns without a description: {missing}. Tables without a description: {missing_tables}."
        ))
        if missing or missing_tables:
            intro.add(Callout(
                "warning",
                f"Rows marked '{MISSING_DESCRIPTION}' have no description in the solution metadata. "
                "Add descriptions in the maker portal so regenerated documentation stays complete.",
            ))
        doc.add(intro)

        for entity in snapshot.entities:
            section = Section(entity_label(entity))
            section.add(Paragraph(description_cell(entity.description)))
            if entity.attributes:
                section.add(Table(
                    headers=["Display name", "Schema name", "Type", "Requirement", "Description"],
                    rows=[
                        [dash(a.display_name), a.logical_name, attribute_type(a), requirement(a),
                         description_cell(a.description)]
                        for a in entity.attributes
                    ],
                ))
            else:
                section.add(Paragraph("No columns exported for this table."))
            doc.add(section)

        if snapshot.global_option_sets:
            section = Section("Global choice sets")
            for option_set in snapshot.global_option_sets:
                section.add(Section(f"{option_set.display_name or option_set.name} ({option_set.name})").add(
                    Table(headers=["Value", "Label"],
                          rows=[[str(o.value), o.label or DASH] for o in option_set.options])
                ))
            doc.add(section)
        return doc
