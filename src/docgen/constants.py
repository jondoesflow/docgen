"""Shared constants. Leaf module — must not import other docgen modules."""

# Document keys accepted by `docgen render --docs` for a solution snapshot.
# Release notes are produced by `docgen diff`, not listed here.
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

# Document keys accepted by `docgen render --docs` for a transcript snapshot.
# The design documents deliberately share their keys with the solution set: the
# same document is drafted from the workshop before build and regenerated from
# the solution export after it.
ALL_TRANSCRIPT_DOC_KEYS: tuple[str, ...] = (
    "meeting-notes",
    "requirements",
    "actions",
    "hld",
    "lld",
    "data-dictionary",
    "security",
    "deployment",
    "licensing",
    "integration",
    "rraid",
    "hygiene",
)

ALL_FORMATS: tuple[str, ...] = ("md", "docx")
