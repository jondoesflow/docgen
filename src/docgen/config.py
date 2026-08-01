"""docgen.yaml loading and validation.

Discovery order: explicit --config path → ./docgen.yaml → built-in defaults.
The Anthropic API key is read from the ANTHROPIC_API_KEY environment variable
only; it must never appear in config files or CLI arguments.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from docgen.constants import ALL_DOC_KEYS, ALL_FORMATS


class ConfigError(ValueError):
    pass


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    enabled: bool = True


class DocgenConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_dir: Path = Path("out")
    default_docs: list[str] = Field(default_factory=lambda: list(ALL_DOC_KEYS))
    formats: list[str] = Field(default_factory=lambda: list(ALL_FORMATS))
    docx_template: Path | None = None
    rules_dir: Path | None = None
    redact_file: Path | None = None
    llm: LLMConfig = Field(default_factory=LLMConfig)


def load_config(explicit_path: Path | None = None, cwd: Path | None = None) -> DocgenConfig:
    """Load configuration; unknown keys or malformed YAML raise ConfigError."""
    cwd = cwd or Path.cwd()
    if explicit_path is not None:
        path = Path(explicit_path)
        if not path.is_file():
            raise ConfigError(f"Config file not found: {path}")
    else:
        candidate = cwd / "docgen.yaml"
        path = candidate if candidate.is_file() else None

    if path is None:
        return DocgenConfig()

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Could not parse {path}: {exc}") from exc
    if raw is None:
        return DocgenConfig()
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping, got {type(raw).__name__}")
    try:
        return DocgenConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Invalid config in {path}:\n{exc}") from exc
