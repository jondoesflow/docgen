"""Prompt builders for the narrative purposes docgen supports. Every prompt
carries the ground-truth instruction: reference only components present in the
provided metadata slice."""

from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "You draft narrative sections for Dynamics 365 / Power Platform consultancy documentation. "
    "You are given a JSON slice of a solution metadata snapshot. Hard rules:\n"
    "1. Reference ONLY tables, columns, flows, connectors and components that appear in the "
    "provided metadata. Never invent capabilities, integrations, or business intentions that "
    "the metadata does not show.\n"
    "2. If the metadata is insufficient to say something, write less rather than guessing.\n"
    "3. Write professional consultancy prose: clear, specific, no marketing filler.\n"
    "4. Respond with the prose only — no headings, no preamble, no markdown emphasis."
)

_PURPOSE_INSTRUCTIONS = {
    "hld_overview": (
        "Write 2-3 paragraphs for the Solution Overview section of a High-Level Design: what this "
        "solution manages, the functional areas it covers, and the automation it includes. "
        "Base every statement on the metadata."
    ),
    "hld_cluster": (
        "Write one paragraph for a functional-area section of a High-Level Design: what this cluster "
        "of tables models and how the tables relate, based only on the metadata."
    ),
    "hld_architecture": (
        "Write 1-2 paragraphs describing the technical architecture visible in the metadata: "
        "model-driven data model, automation, server-side logic and external connectors."
    ),
    "flow_description": (
        "Write a short plain-English description (2-4 sentences) of what this cloud flow does, "
        "step by step, for a non-technical reader. Mention the trigger and the key actions."
    ),
    "integration_overview": (
        "Write 1-2 paragraphs describing the integration landscape: which external systems/connectors "
        "this solution talks to and through which mechanism (flows, plug-ins, custom connectors)."
    ),
    "rraid_seed": (
        "Rephrase this automatically detected finding as a single concise risk/dependency statement "
        "for a RRAID log. Keep the component name exactly as given. One sentence."
    ),
}


def build_user_prompt(purpose: str, payload: dict) -> str:
    instruction = _PURPOSE_INSTRUCTIONS.get(purpose, "Write a short factual narrative for this metadata.")
    return (
        f"{instruction}\n\n"
        f"Solution metadata slice (ground truth — reference nothing outside it):\n"
        f"```json\n{json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)}\n```"
    )


def build_retry_prompt(purpose: str, payload: dict, violations: list[str]) -> str:
    return (
        build_user_prompt(purpose, payload)
        + "\n\nYour previous answer referenced component names that do NOT exist in the metadata: "
        + ", ".join(violations)
        + ". Rewrite the answer using only names present in the metadata slice."
    )
