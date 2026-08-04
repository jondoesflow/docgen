"""docgen.yaml loading and validation.

Discovery order: explicit --config path → ./docgen.yaml → built-in defaults.
API keys never appear in config files or CLI arguments — each provider's key
is read from its environment variable (e.g. ANTHROPIC_API_KEY); see
docgen.llm.registry.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from docgen.constants import ALL_DOC_KEYS, ALL_FORMATS, ALL_TRANSCRIPT_DOC_KEYS


class ConfigError(ValueError):
    pass


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    enabled: bool = True
    # Prompt caching. On Anthropic this adds a cache breakpoint to the shared
    # system prompt (a no-op below the model's minimum cacheable size, so safe
    # to leave on). Other providers cache automatically server-side and ignore
    # this switch.
    cache: bool = True

    @field_validator("provider")
    @classmethod
    def _provider_in_registry(cls, value: str) -> str:
        # Imported lazily to avoid a config <-> llm import cycle at module load.
        from docgen.llm.registry import get_provider

        get_provider(value)  # raises UnknownProviderError (a ValueError) if unknown
        return value


class DocgenConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_dir: Path = Path("out")
    default_docs: list[str] = Field(default_factory=lambda: list(ALL_DOC_KEYS))
    default_transcript_docs: list[str] = Field(default_factory=lambda: list(ALL_TRANSCRIPT_DOC_KEYS))
    formats: list[str] = Field(default_factory=lambda: list(ALL_FORMATS))
    docx_template: Path | None = None
    # Folder of per-document Word templates (HLD.docx, LLD.docx, ...). Defaults to
    # ./templates; a missing folder simply means no per-document templates.
    templates_dir: Path | None = Path("templates")
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
