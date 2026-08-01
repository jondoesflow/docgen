"""Shared constants. Leaf module — must not import other docgen modules."""

# Document keys accepted by `docgen render --docs`. Release notes are produced
# by `docgen diff`, not listed here.
ALL_DOC_KEYS: tuple[str, ...] = (
    "lld",
    "data-dictionary",
    "security",
    "deployment",
    "licensing",
    "hygiene",
    "hld",
    "integration",
    "rraid",
)

ALL_FORMATS: tuple[str, ...] = ("md", "docx")
