"""Cost estimation for LLM usage.

Prices are USD per million tokens (input, output), from Anthropic's published
API pricing (cached 2026-06). They change over time — treat the figure docgen
prints as an estimate for commercial awareness, not an invoice; the billing
console is authoritative. Matching is by model-id prefix so dated variants
(e.g. claude-haiku-4-5-20251001) resolve to their family.
"""

from __future__ import annotations

# model-id prefix -> (input $/MTok, output $/MTok)
PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    # Sonnet 5 has an introductory rate ($2/$10) through 2026-08-31; the
    # standard rate below is therefore an upper bound during that window.
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def rates_for(model: str) -> tuple[float, float] | None:
    """(input, output) $/MTok for a model id, or None when unknown."""
    best = None
    for prefix, rates in PRICING.items():
        if model == prefix or model.startswith(prefix + "-"):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, rates)
    return best[1] if best else None


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimated USD cost, or None when the model's pricing is unknown."""
    rates = rates_for(model)
    if rates is None:
        return None
    input_rate, output_rate = rates
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


def usage_summary_line(model: str, calls: int, input_tokens: int, output_tokens: int) -> str:
    """One console line summarising a run's LLM usage and estimated cost."""
    base = (f"LLM usage: {calls} call(s), {input_tokens:,} input + {output_tokens:,} output tokens "
            f"({model})")
    cost = estimate_cost(model, input_tokens, output_tokens)
    if cost is None:
        return base + " - pricing unknown for this model, no cost estimate"
    return base + f" - estimated cost ${cost:.4f} USD"
