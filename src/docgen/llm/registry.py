"""Provider registry for the LLM tier.

Each supported provider is a ProviderSpec entry here plus a client class in
docgen.llm.client — adding the next provider is a registry entry, not a code
change elsewhere. Phase 1 ships Anthropic only; the launch set (OpenAI,
DeepSeek, Kimi, Gemini, Mistral, xAI) lands once the client abstraction is
reviewed.

known_models is advisory: model strings not listed here warn but never block,
because new models ship faster than registries update.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class UnknownProviderError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderSpec:
    key: str  # registry key, used in config as llm.provider
    display_name: str
    env_var: str  # environment variable holding the API key
    known_models: tuple[str, ...]
    supports_structured_output: bool


PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        key="anthropic",
        display_name="Anthropic",
        env_var="ANTHROPIC_API_KEY",
        known_models=(
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5",
        ),
        supports_structured_output=True,
    ),
}


def get_provider(key: str) -> ProviderSpec:
    spec = PROVIDERS.get(key)
    if spec is None:
        raise UnknownProviderError(
            f"Unknown LLM provider {key!r}. Supported providers: {', '.join(sorted(PROVIDERS))}."
        )
    return spec


def resolve_api_key(spec: ProviderSpec) -> tuple[str, str] | None:
    """Return (key, human-readable source) for a provider, or None.

    Resolution today is the real environment variable only. The OS-keyring and
    .env fallbacks arrive with the `docgen model key` command; this function is
    the single place that precedence will live (env var → keyring → .env)."""
    value = os.environ.get(spec.env_var)
    if value:
        return value, f"environment variable {spec.env_var}"
    return None
