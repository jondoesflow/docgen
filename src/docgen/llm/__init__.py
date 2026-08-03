"""LLM tier: optional narrative drafting via the configured provider
(Anthropic by default; see docgen.llm.registry).

Pipeline per narrative request:
payload slice → redaction (redact.yaml) → prompt → API → validate every
component-shaped name against the snapshot → (reject + one retry on
violations) → un-redact → prose. Any failure degrades to None, which the
renderer turns into a `[Consultant to complete]` placeholder — the LLM tier
can improve documents but never break a run.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

from docgen.llm.client import LlmClient, MissingApiKeyError, create_client
from docgen.llm.prompts import (
    SYSTEM_PROMPT,
    TRANSCRIPT_SYSTEM_PROMPT,
    build_retry_prompt,
    build_transcript_prompt,
    build_transcript_retry_prompt,
    build_user_prompt,
)
from docgen.llm.redact import Redactor
from docgen.llm.validate import (
    collect_component_names,
    collect_participant_names,
    find_attribution_violations,
    find_violations,
)

if TYPE_CHECKING:
    from docgen.config import DocgenConfig


def _create_client_or_none(cfg: "DocgenConfig", out_dir: Path) -> LlmClient | None:
    """Build the configured provider's client, or None (degrade to placeholders)."""
    try:
        client = create_client(cfg.llm, out_dir)
    except MissingApiKeyError as exc:
        typer.secho(f"{exc} Continuing with placeholders.", fg=typer.colors.YELLOW, err=True)
        return None
    # Compliance: the active provider must be visible every time the LLM
    # tier runs — provider choice is a per-engagement decision.
    typer.secho(
        f"  LLM provider: {client.spec.display_name} — model {client.model} "
        f"(key from {client.key_source})",
        fg=typer.colors.CYAN,
    )
    return client


def make_narrative_provider(snapshot, cfg: "DocgenConfig", out_dir: Path, client: LlmClient | None = None):
    """Returns a (purpose, payload) -> str|None callable. `client` injectable for tests."""
    if client is None:
        client = _create_client_or_none(cfg, out_dir)
        if client is None:
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

    provider.client = client  # exposed so the run can report usage + estimated cost at the end
    return provider


def make_transcript_narrative_provider(snapshot, cfg: DocgenConfig, out_dir: Path,
                                       client: LlmClient | None = None):
    """Narrative provider for transcript documents.

    Same degrade-to-placeholder contract as the solution provider, validated on
    attribution instead of component names: prose that quotes or credits
    somebody who was not in the meeting is rejected and retried once.

    Redaction matters more here than anywhere else in docgen — a transcript is
    almost entirely client names, people and commercial detail — so `redact.yaml`
    is applied to every slice before it leaves the machine, exactly as it is for
    solution metadata.
    """
    if client is None:
        client = _create_client_or_none(cfg, out_dir)
        if client is None:
            return lambda purpose, payload: None

    names = collect_participant_names(snapshot)
    redactor = Redactor.from_file(cfg.redact_file)

    def provider(purpose: str, payload: dict) -> str | None:
        try:
            user_prompt = redactor.redact(build_transcript_prompt(purpose, payload))
            text = client.complete(purpose, TRANSCRIPT_SYSTEM_PROMPT, user_prompt)
            violations = find_attribution_violations(redactor.unredact(text), names)
            if violations:
                retry_prompt = redactor.redact(build_transcript_retry_prompt(purpose, payload, violations))
                text = client.complete(f"{purpose}:retry", TRANSCRIPT_SYSTEM_PROMPT, retry_prompt)
                violations = find_attribution_violations(redactor.unredact(text), names)
                if violations:
                    typer.secho(
                        f"  LLM narrative for {purpose} rejected twice "
                        f"(attributed to people not in the meeting: {', '.join(violations)}) - "
                        "using placeholder",
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

    provider.client = client
    return provider
