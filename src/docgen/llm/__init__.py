"""LLM tier: optional narrative drafting via the Anthropic API.

Pipeline per narrative request:
payload slice → redaction (redact.yaml) → prompt → API → validate every
component-shaped name against the snapshot → (reject + one retry on
violations) → un-redact → prose. Any failure degrades to None, which the
renderer turns into a `[Consultant to complete]` placeholder — the LLM tier
can improve documents but never break a run.
"""

from __future__ import annotations

from pathlib import Path

import typer

from docgen.config import DocgenConfig
from docgen.llm.client import LlmClient, MissingApiKeyError
from docgen.llm.prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt
from docgen.llm.redact import Redactor
from docgen.llm.validate import collect_component_names, find_violations


def make_narrative_provider(snapshot, cfg: DocgenConfig, out_dir: Path, client: LlmClient | None = None):
    """Returns a (purpose, payload) -> str|None callable. `client` injectable for tests."""
    if client is None:
        try:
            client = LlmClient(cfg.llm.model, cfg.llm.max_tokens, out_dir)
        except MissingApiKeyError as exc:
            typer.secho(f"{exc} Continuing with placeholders.", fg=typer.colors.YELLOW, err=True)
            return lambda purpose, payload: None

    names = collect_component_names(snapshot)
    redactor = Redactor.from_file(cfg.redact_file)

    def provider(purpose: str, payload: dict) -> str | None:
        try:
            user_prompt = redactor.redact(build_user_prompt(purpose, payload))
            text = client.complete(purpose, SYSTEM_PROMPT, user_prompt)
            violations = find_violations(redactor.unredact(text), names)
            if violations:
                retry_prompt = redactor.redact(build_retry_prompt(purpose, payload, violations))
                text = client.complete(f"{purpose}:retry", SYSTEM_PROMPT, retry_prompt)
                violations = find_violations(redactor.unredact(text), names)
                if violations:
                    typer.secho(
                        f"  LLM narrative for {purpose} rejected twice "
                        f"(invented components: {', '.join(violations)}) - using placeholder",
                        fg=typer.colors.YELLOW, err=True,
                    )
                    return None
            return redactor.unredact(text) or None
        except Exception as exc:  # API/network errors degrade, never fail the run
            typer.secho(f"  LLM narrative for {purpose} failed ({exc}) - using placeholder",
                        fg=typer.colors.YELLOW, err=True)
            return None
        finally:
            redactor.write_log(out_dir)

    return provider
