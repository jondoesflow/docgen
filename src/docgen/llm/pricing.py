"""Cost estimation for LLM usage.

Rates live on each provider's registry entry (docgen.llm.registry,
ProviderSpec.pricing) as USD per million tokens (input, output), from the
provider's published API pricing. They change over time — treat the figure
docgen prints as an estimate for commercial awareness, not an invoice; the
provider's billing console is authoritative. Matching is by model-id prefix so
dated variants (e.g. claude-haiku-4-5-20251001) resolve to their family. An
unknown provider or model yields None and docgen prints "pricing unknown"
rather than a wrong number.
"""

from __future__ import annotations

from docgen.llm.registry import UnknownProviderError, get_provider


def rates_for(model: str, provider: str = "anthropic") -> tuple[float, float] | None:
    """(input, output) $/MTok for a provider's model id, or None when unknown."""
    try:
        spec = get_provider(provider)
    except UnknownProviderError:
        return None
    best = None
    for prefix, rates in spec.pricing.items():
        if model == prefix or model.startswith(prefix + "-"):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, rates)
    return best[1] if best else None


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  provider: str = "anthropic") -> float | None:
    """Estimated USD cost, or None when the model's pricing is unknown."""
    rates = rates_for(model, provider)
    if rates is None:
        return None
    input_rate, output_rate = rates
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


def usage_summary_line(model: str, calls: int, input_tokens: int, output_tokens: int,
                       provider: str = "anthropic") -> str:
    """One console line summarising a run's LLM usage and estimated cost."""
    base = (f"LLM usage: {calls} call(s), {input_tokens:,} input + {output_tokens:,} output tokens "
            f"({provider}/{model})")
    cost = estimate_cost(model, input_tokens, output_tokens, provider)
    if cost is None:
        return base + " - pricing unknown for this model, no cost estimate"
    return base + f" - estimated cost ${cost:.4f} USD"
