"""DocModel → GitHub-flavoured Markdown emitter. Mermaid embedded as fenced source."""

from __future__ import annotations

from pathlib import Path

from docgen.renderers.docmodel import (
    BulletList,
    Callout,
    CodeBlock,
    Diagram,
    Document,
    Paragraph,
    Placeholder,
    Section,
    Table,
)

_CALLOUT_LABELS = {"info": "Note", "warning": "Warning", "risk": "Risk"}


def _escape_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _emit_block(block, lines: list[str], level: int) -> None:
    if isinstance(block, Section):
        lines.append(f"{'#' * min(level, 6)} {block.heading}")
        lines.append("")
        for child in block.blocks:
            _emit_block(child, lines, level + 1)
    elif isinstance(block, Paragraph):
        lines.append(f"**{block.text}**" if block.bold else block.text)
        lines.append("")
    elif isinstance(block, BulletList):
        lines.extend(f"- {item}" for item in block.items)
        lines.append("")
    elif isinstance(block, Table):
        if block.caption:
            lines.append(f"*{block.caption}*")
            lines.append("")
        lines.append("| " + " | ".join(_escape_cell(h) for h in block.headers) + " |")
        lines.append("|" + "|".join(" --- " for _ in block.headers) + "|")
        for row in block.rows:
            lines.append("| " + " | ".join(_escape_cell(c) for c in row) + " |")
        lines.append("")
    elif isinstance(block, CodeBlock):
        lines.append(f"```{block.language or ''}")
        lines.append(block.text)
        lines.append("```")
        lines.append("")
    elif isinstance(block, Diagram):
        if block.caption:
            lines.append(f"*{block.caption}*")
            lines.append("")
        lines.append("```mermaid")
        lines.append(block.mermaid)
        lines.append("```")
        lines.append("")
    elif isinstance(block, Placeholder):
        hint = f" — {block.hint}" if block.hint else ""
        lines.append(f"> **{block.text}**{hint}")
        lines.append("")
    elif isinstance(block, Callout):
        label = _CALLOUT_LABELS.get(block.severity, block.severity.title())
        lines.append(f"> **{label}:** {block.text}")
        lines.append("")
    else:  # pragma: no cover - defensive
        raise TypeError(f"Unknown block type: {type(block).__name__}")


def emit_markdown(document: Document) -> str:
    lines: list[str] = [f"# {document.title}", ""]
    if document.subtitle:
        lines.append(f"*{document.subtitle}*")
        lines.append("")
    for section in document.sections:
        _emit_block(section, lines, 2)
    return "\n".join(lines).rstrip() + "\n"


def write_markdown(document: Document, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(emit_markdown(document), encoding="utf-8", newline="\n")
    return path
