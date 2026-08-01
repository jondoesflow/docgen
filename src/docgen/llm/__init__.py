"""LLM tier (milestone 7). Until it lands, rendering without --no-llm degrades
to offline placeholders with a notice instead of failing."""

from __future__ import annotations

from pathlib import Path

import typer

from docgen.config import DocgenConfig


def make_narrative_provider(snapshot, cfg: DocgenConfig, out_dir: Path):
    typer.secho(
        "LLM tier not implemented yet (milestone 7) — rendering with placeholders as if --no-llm was set.",
        fg=typer.colors.YELLOW,
        err=True,
    )
    from docgen.renderers.base import offline_narrative

    return offline_narrative
