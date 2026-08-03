"""Loading of rules YAML files (licensing / deprecations / naming / transcript cues).

Defaults ship inside the package; a file of the same name in the configured
`rules_dir` fully replaces the shipped one (no merging semantics).
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml

from docgen.config import DocgenConfig

RULE_FILES = ("licensing", "deprecations", "naming", "transcript_cues")


def load_rules(cfg: DocgenConfig) -> dict[str, dict]:
    rules: dict[str, dict] = {}
    for stem in RULE_FILES:
        data = None
        if cfg.rules_dir is not None:
            override = Path(cfg.rules_dir) / f"{stem}.yaml"
            if override.is_file():
                data = yaml.safe_load(override.read_text(encoding="utf-8"))
        if data is None:
            shipped = resources.files("docgen") / "rules" / f"{stem}.yaml"
            data = yaml.safe_load(shipped.read_text(encoding="utf-8"))
        rules[stem] = data or {}
    return rules
