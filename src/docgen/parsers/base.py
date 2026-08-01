"""Shared parsing infrastructure: the ParseContext plus tolerant XML accessors.

Everything here is deliberately forgiving: real solution exports vary between
platform versions, so missing elements yield defaults (usually None) and a
parse warning where that absence is meaningful — never an exception. Any
exception raised while parsing a single component must be caught by the
caller, converted to a `component_error` warning, and parsing must continue.
"""

from __future__ import annotations

import zipfile

from lxml import etree

from docgen.snapshot.models import ParseWarning


class ParseContext:
    """Carries the open zip, the warnings sink, and root-component claims."""

    def __init__(self, zf: zipfile.ZipFile, source_name: str):
        self.zf = zf
        self.source_name = source_name
        self._names = {n.lower(): n for n in zf.namelist()}  # case-insensitive index
        self.warnings: list[ParseWarning] = []
        # RootComponent claims: type code -> set of lowercase keys (schemaName or id)
        self.claimed: dict[int, set[str]] = {}

    def warn(self, code: str, context: str = "", message: str = "") -> None:
        self.warnings.append(ParseWarning(code=code, context=context, message=message))

    def has_file(self, name: str) -> bool:
        return name.lower() in self._names

    def file_names(self) -> list[str]:
        return list(self._names.values())

    def read_bytes(self, name: str) -> bytes | None:
        real = self._names.get(name.lower())
        if real is None:
            return None
        return self.zf.read(real)

    def read_xml(self, name: str) -> etree._Element | None:
        data = self.read_bytes(name)
        if data is None:
            return None
        try:
            return etree.fromstring(data)
        except etree.XMLSyntaxError as exc:
            self.warn("invalid_xml", name, str(exc))
            return None

    def claim(self, type_code: int, key: str) -> None:
        """Record that a specialised parser handled root component (type, key)."""
        self.claimed.setdefault(type_code, set()).add(key.lower())

    def is_claimed(self, type_code: int, key: str) -> bool:
        return key.lower() in self.claimed.get(type_code, set())


# ---------------------------------------------------------------------------
# Tolerant accessors
# ---------------------------------------------------------------------------


def text(el: etree._Element | None, path: str, default: str | None = None) -> str | None:
    """Text of the first element at `path`, stripped; default when absent/empty."""
    if el is None:
        return default
    found = el.find(path)
    if found is None or found.text is None:
        return default
    value = found.text.strip()
    return value if value else default


def attr(el: etree._Element | None, name: str, default: str | None = None) -> str | None:
    if el is None:
        return default
    value = el.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def loc_text(el: etree._Element | None, path: str, attribute: str = "description") -> str | None:
    """Localized label: the `description` attribute of the first child at path.

    Handles the export idiom <LocalizedNames><LocalizedName description="..."
    languagecode="1033"/></LocalizedNames> and its lowercase variants.
    """
    if el is None:
        return None
    found = el.find(path)
    if found is None:
        return None
    value = found.get(attribute)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def to_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes")


def to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def clean(value: str | None) -> str | None:
    """Strip; collapse empty strings to None (blank descriptions become None)."""
    if value is None:
        return None
    value = value.strip()
    return value if value else None
