"""Format-neutral document tree.

Every doc renderer builds one of these; the markdown and docx emitters walk it.
Adding a new document therefore never involves format-specific code, and the
two output formats cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PLACEHOLDER_TEXT = "[Consultant to complete]"


@dataclass
class Paragraph:
    text: str
    bold: bool = False


@dataclass
class BulletList:
    items: list[str]


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    caption: str | None = None


@dataclass
class CodeBlock:
    text: str
    language: str | None = None


@dataclass
class Diagram:
    """A diagram with Mermaid source (always) and optional DOT equivalent.

    Emitters decide presentation: markdown embeds the Mermaid source; docx tries
    to render an image (mermaid-cli, then graphviz) and falls back to embedding
    the source as a code block with a note. A missing renderer never fails a run.
    """

    name: str  # stable slug used for image file names
    mermaid: str
    dot: str | None = None
    caption: str | None = None


@dataclass
class Placeholder:
    """Narrative left for a human (or the optional LLM tier) to write."""

    hint: str = ""
    text: str = PLACEHOLDER_TEXT


@dataclass
class Callout:
    severity: str  # info | warning | risk
    text: str


Block = Paragraph | BulletList | Table | CodeBlock | Diagram | Placeholder | Callout


@dataclass
class Section:
    heading: str
    blocks: list["Block | Section"] = field(default_factory=list)

    def add(self, *blocks: "Block | Section") -> "Section":
        self.blocks.extend(blocks)
        return self


@dataclass
class Document:
    title: str
    subtitle: str = ""
    sections: list[Section] = field(default_factory=list)

    def add(self, *sections: Section) -> "Document":
        self.sections.extend(sections)
        return self
