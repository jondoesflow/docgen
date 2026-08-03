"""Per-document Word templates.

A project can drop branded Word templates into a templates folder — `HLD.docx`
for the High-Level Design, `LLD.docx` for the Low-Level Design, and so on — and
docgen pours that document into that template. Resolution order per document:

1. `<templates_dir>/<name>.docx`, where `<name>` is the document key, its title
   or a common abbreviation (matched case-insensitively, so `HLD.docx`,
   `hld.docx` and `High-Level Design.docx` all work).
2. `docx_template` from config — a single template for every document.
3. The plain template shipped inside the package.

Nothing is required: with no templates folder the behaviour is exactly as it
was. A folder that only holds `HLD.docx` gives the HLD its branding and leaves
every other document on the fallback — templates are opt-in per document.
"""

from __future__ import annotations

from pathlib import Path

from docgen.config import DocgenConfig

TEMPLATE_SUFFIX = ".docx"

# Names accepted for each document, beyond the document key itself. Everything
# is matched case-insensitively and with -/_/space treated alike.
TEMPLATE_ALIASES: dict[str, tuple[str, ...]] = {
    # solution documents
    "lld": ("LLD", "Low-Level Design", "Low Level Design"),
    "data-dictionary": ("DD", "Data Dictionary"),
    "security": ("Security Model", "Security & Access Model", "Security and Access Model"),
    "deployment": ("Deployment Configuration Register", "Deployment Register"),
    "licensing": ("Licensing Impact Summary",),
    "hygiene": ("Solution Hygiene Report", "Hygiene Report"),
    "hld": ("HLD", "High-Level Design", "High Level Design"),
    "integration": ("Integration Design",),
    "rraid": ("RRAID", "RRAID Log"),
    "release-notes": ("Release Notes",),
    # transcript documents
    "meeting-notes": ("Meeting Notes", "Minutes", "Meeting Minutes"),
    "requirements": ("Requirements Catalogue", "Requirements Catalog"),
    "actions": ("Actions & Decisions Register", "Actions and Decisions Register", "Action Log"),
    "discovery-rraid": ("Discovery RRAID", "Discovery RRAID Log", "Workshop RRAID"),
}


def _normalise(name: str) -> str:
    """`High-Level Design` / `high_level_design` / `HIGH LEVEL DESIGN` → one key."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def candidate_names(key: str, title: str = "") -> list[str]:
    """Every file stem that would be accepted for this document, best first."""
    names = [key, *TEMPLATE_ALIASES.get(key, ())]
    if title and title not in names:
        names.append(title)
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        normalised = _normalise(name)
        if normalised and normalised not in seen:
            seen.add(normalised)
            ordered.append(name)
    return ordered


def templates_dir(cfg: DocgenConfig) -> Path | None:
    directory = Path(cfg.templates_dir) if cfg.templates_dir is not None else None
    return directory if directory is not None and directory.is_dir() else None


def find_document_template(key: str, title: str, cfg: DocgenConfig) -> Path | None:
    """The per-document template for this document, or None if there isn't one."""
    directory = templates_dir(cfg)
    if directory is None:
        return None
    wanted = {_normalise(name): rank for rank, name in enumerate(candidate_names(key, title))}
    best: tuple[int, Path] | None = None
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() != TEMPLATE_SUFFIX:
            continue
        rank = wanted.get(_normalise(path.stem))
        if rank is not None and (best is None or rank < best[0]):
            best = (rank, path)
    return best[1] if best else None


def resolve_template(key: str, title: str, cfg: DocgenConfig) -> tuple[Path | None, str]:
    """Returns (template path or None for the shipped default, a short source label)."""
    specific = find_document_template(key, title, cfg)
    if specific is not None:
        return specific, f"template {specific.name}"
    if cfg.docx_template is not None:
        return Path(cfg.docx_template), f"template {Path(cfg.docx_template).name}"
    return None, ""
