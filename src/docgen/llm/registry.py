"""Provider registry for the LLM tier.

Each supported provider is a ProviderSpec entry here plus a client class
registered in docgen.llm.client — adding the next provider is a registry
entry, not a code change elsewhere. OpenAI, DeepSeek, Kimi (Moonshot), Mistral
and xAI all speak the OpenAI-compatible chat API and differ only by base_url;
Anthropic and Google Gemini use their own SDKs.

known_models is advisory: model strings not listed here warn but never block,
because new models ship faster than registries update. pricing is an estimate
cache — an empty dict means docgen prints "pricing unknown" rather than a
wrong number.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class UnknownProviderError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderSpec:
    key: str  # registry key, used in config as llm.provider
    display_name: str
    env_var: str  # environment variable holding the API key
    known_models: tuple[str, ...]
    supports_structured_output: bool
    # OpenAI-compatible endpoint for this provider; None = the SDK's default
    # (native Anthropic/Gemini SDKs, or api.openai.com for OpenAI itself).
    base_url: str | None = None
    # Newer OpenAI models reject `max_tokens` in favour of `max_completion_tokens`;
    # every other OpenAI-compatible provider still expects `max_tokens`.
    max_tokens_param: str = "max_tokens"
    # model-id prefix -> (input $/MTok, output $/MTok), from the provider's
    # published API pricing. Estimates only — the provider's billing console is
    # authoritative. An empty dict means docgen prints "pricing unknown"
    # rather than a wrong number; dated model variants resolve by prefix.
    pricing: dict[str, tuple[float, float]] = field(default_factory=dict)


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
        # Cached 2026-06 from Anthropic's published API pricing.
        pricing={
            "claude-fable-5": (10.00, 50.00),
            "claude-opus-5": (5.00, 25.00),
            "claude-opus-4-8": (5.00, 25.00),
            "claude-opus-4-7": (5.00, 25.00),
            "claude-opus-4-6": (5.00, 25.00),
            # Sonnet 5 has an introductory rate ($2/$10) through 2026-08-31;
            # the standard rate below is an upper bound during that window.
            "claude-sonnet-5": (3.00, 15.00),
            "claude-sonnet-4-6": (3.00, 15.00),
            "claude-haiku-4-5": (1.00, 5.00),
        },
    ),
    "openai": ProviderSpec(
        key="openai",
        display_name="OpenAI",
        env_var="OPENAI_API_KEY",
        known_models=("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"),
        supports_structured_output=True,
        max_tokens_param="max_completion_tokens",
    ),
    "deepseek": ProviderSpec(
        key="deepseek",
        display_name="DeepSeek",
        env_var="DEEPSEEK_API_KEY",
        known_models=("deepseek-chat", "deepseek-reasoner"),
        supports_structured_output=True,
        base_url="https://api.deepseek.com/v1",
    ),
    "kimi": ProviderSpec(
        key="kimi",
        display_name="Kimi (Moonshot AI)",
        env_var="MOONSHOT_API_KEY",
        known_models=("kimi-latest", "moonshot-v1-8k", "moonshot-v1-32k"),
        supports_structured_output=False,
        base_url="https://api.moonshot.ai/v1",
    ),
    "gemini": ProviderSpec(
        key="gemini",
        display_name="Google Gemini",
        env_var="GEMINI_API_KEY",
        known_models=("gemini-2.5-pro", "gemini-2.5-flash"),
        supports_structured_output=True,
    ),
    "mistral": ProviderSpec(
        key="mistral",
        display_name="Mistral",
        env_var="MISTRAL_API_KEY",
        known_models=("mistral-large-latest", "mistral-small-latest"),
        supports_structured_output=True,
        base_url="https://api.mistral.ai/v1",
    ),
    "xai": ProviderSpec(
        key="xai",
        display_name="xAI",
        env_var="XAI_API_KEY",
        known_models=("grok-4", "grok-3", "grok-3-mini"),
        supports_structured_output=True,
        base_url="https://api.x.ai/v1",
    ),
}


def get_provider(key: str) -> ProviderSpec:
    spec = PROVIDERS.get(key)
    if spec is None:
        raise UnknownProviderError(
            f"Unknown LLM provider {key!r}. Supported providers: {', '.join(sorted(PROVIDERS))}."
        )
    return spec


def parse_model_string(value: str) -> tuple[ProviderSpec, str]:
    """'provider/model' -> (ProviderSpec, model). Model strings may themselves
    contain '/' (only the first separator splits)."""
    provider, sep, model = value.partition("/")
    if not sep or not provider or not model:
        raise ValueError(
            f"Expected provider/model (e.g. anthropic/claude-sonnet-4-6), got {value!r}."
        )
    return get_provider(provider), model
