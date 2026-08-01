"""Mermaid ERD generation and the graceful image-render fallback chain.

Markdown always embeds Mermaid source. For docx we try, in order:
mermaid-cli (mmdc) → graphviz (dot, using a generated DOT equivalent) →
no image (the docx emitter embeds the source in a code block with a note).
A missing or failing renderer never fails the documentation run.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from docgen.renderers.docmodel import Diagram
from docgen.snapshot.models import Entity, Relationship

# D365 attribute type → short label used inside ERD attribute blocks
_TYPE_LABELS = {
    "nvarchar": "string",
    "ntext": "text",
    "int": "int",
    "decimal": "decimal",
    "money": "money",
    "float": "float",
    "bit": "bool",
    "boolean": "bool",
    "datetime": "datetime",
    "lookup": "lookup",
    "picklist": "choice",
    "multiselectpicklist": "choices",
    "uniqueidentifier": "guid",
    "owner": "owner",
    "state": "state",
    "status": "status",
    "customer": "customer",
    "file": "file",
    "image": "image",
}

MAX_ERD_ATTRIBUTES = 14


def _erd_cardinality(rel: Relationship) -> str:
    return "}o--o{" if rel.type == "many_to_many" else "||--o{"


def build_erd(name: str, entities: list[Entity], *, include_attributes: bool = True,
              caption: str | None = None) -> Diagram:
    """ERD for a set of entities; relationships drawn only between included entities."""
    included = {e.logical_name for e in entities}
    mermaid_lines = ["erDiagram"]
    dot_lines = ["graph erd {", "  rankdir=LR;", '  node [shape=record, fontsize=10, fontname="Segoe UI"];']

    rels: list[Relationship] = []
    for entity in entities:
        for rel in entity.relationships:
            if rel.referenced_entity in included and rel.referencing_entity in included:
                rels.append(rel)

    for rel in sorted(rels, key=lambda r: r.schema_name):
        mermaid_lines.append(
            f'    {rel.referenced_entity} {_erd_cardinality(rel)} {rel.referencing_entity} : "{rel.schema_name}"'
        )
        style = "dir=none" if rel.type == "many_to_many" else "dir=back, arrowtail=crow"
        dot_lines.append(
            f'  {rel.referenced_entity} -- {rel.referencing_entity} [label="{rel.schema_name}", {style}];'
        )

    for entity in sorted(entities, key=lambda e: e.logical_name):
        if include_attributes and entity.attributes:
            mermaid_lines.append(f"    {entity.logical_name} {{")
            shown = entity.attributes[:MAX_ERD_ATTRIBUTES]
            for att in shown:
                type_label = _TYPE_LABELS.get(att.type, att.type or "field")
                marker = " PK" if att.logical_name == entity.primary_name_attribute else ""
                mermaid_lines.append(f"        {type_label} {att.logical_name}{marker}")
            if len(entity.attributes) > len(shown):
                mermaid_lines.append(f"        string _and_{len(entity.attributes) - len(shown)}_more_")
            mermaid_lines.append("    }")
            fields = "|".join(a.logical_name for a in shown)
            dot_lines.append(f'  {entity.logical_name} [label="{{{entity.logical_name}|{fields}}}"];')
        else:
            dot_lines.append(f'  {entity.logical_name} [label="{entity.logical_name}", shape=box];')

    dot_lines.append("}")
    return Diagram(name=name, mermaid="\n".join(mermaid_lines), dot="\n".join(dot_lines), caption=caption)


class DiagramService:
    """Renders Diagram nodes to PNG when a renderer is available on PATH."""

    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self._mmdc = shutil.which("mmdc")
        self._dot = shutil.which("dot")
        self.fallback_note: str | None = None
        if not self._mmdc and not self._dot:
            self.fallback_note = (
                "Diagram shown as Mermaid source — install mermaid-cli (mmdc) or Graphviz (dot) "
                "to embed rendered images, or paste the source into https://mermaid.live"
            )

    def render_image(self, diagram: Diagram) -> Path | None:
        """PNG path, or None when no renderer is available / rendering failed."""
        images_dir = self.out_dir / "diagrams"
        target = images_dir / f"{diagram.name}.png"
        if self._mmdc:
            try:
                images_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False, encoding="utf-8") as tmp:
                    tmp.write(diagram.mermaid)
                    source_path = tmp.name
                subprocess.run(
                    [self._mmdc, "-i", source_path, "-o", str(target), "-b", "white"],
                    check=True, capture_output=True, timeout=120,
                )
                if target.is_file():
                    return target
            except Exception:
                pass  # degrade to the next tier
        if self._dot and diagram.dot:
            try:
                images_dir.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    [self._dot, "-Tpng", "-o", str(target)],
                    input=diagram.dot.encode("utf-8"), check=True, capture_output=True, timeout=120,
                )
                if target.is_file():
                    return target
            except Exception:
                pass
        return None
