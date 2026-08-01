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


TRANSCRIPT_SYSTEM_PROMPT = (
    "You draft narrative sections for consultancy documentation produced from a meeting "
    "transcript. You are given a JSON slice of a parsed transcript. Hard rules:\n"
    "1. Report ONLY what the transcript slice shows. Never add requirements, decisions, systems, "
    "numbers or intentions that are not in it.\n"
    "2. Attribute statements only to people named in the slice, and only to the person who "
    "actually said them. If you are not certain who said something, do not attribute it.\n"
    "3. Where the transcript is vague, say that it is vague. Do not resolve ambiguity by guessing; "
    "an unresolved point is a finding, not a gap to fill.\n"
    "4. Use the client's own terms for their business objects rather than substituting "
    "product or technology names.\n"
    "5. Write professional consultancy prose: clear, specific, no marketing filler.\n"
    "6. Respond with the prose only — no headings, no preamble, no markdown emphasis."
)

_TRANSCRIPT_PURPOSE_INSTRUCTIONS = {
    "meeting_summary": (
        "Write 2-3 paragraphs summarising this session for the front of a meeting-notes document: "
        "why it was held, the ground it covered, and the two or three points that most change the "
        "shape of the engagement. Base every statement on the transcript slice."
    ),
    "section_summary": (
        "Write one short paragraph summarising what was established in this section of the meeting: "
        "the points made, the positions taken, and anything explicitly left open. Do not list every "
        "turn; summarise."
    ),
    "requirement_statements": (
        "Rewrite each verbatim candidate as a single numbered, testable requirement in the form "
        "'REQ-nnn — The system shall ...', keeping the given ID so it stays traceable to the "
        "transcript. One line each, in the order given. Do not merge, add or drop any."
    ),
    "requirement_area": (
        "Write one paragraph summarising what the client needs in this functional area, and state "
        "plainly where the recorded statements conflict with each other or are too vague to build "
        "from."
    ),
    "discovery_seed": (
        "Rephrase this statement from the transcript as a single concise RRAID entry of the given "
        "category, written in the third person. Keep it to one sentence and do not add impact, "
        "likelihood or mitigation."
    ),
    # -- pre-build design documents -------------------------------------
    # These draft *design intent* from a discovery session. The standing rule is
    # sharper here than anywhere else in docgen: nothing has been built, so any
    # concrete technical claim would be invention. Describe what the client
    # needs, never what the system is.
    "design_context": (
        "Write 2-3 paragraphs of business context for a High-Level Design: what this organisation "
        "does, why it is changing now, and what the current way of working is costing it. Use only "
        "what the transcript slice shows, including the numbers stated in it."
    ),
    "design_scope": (
        "Write one or two paragraphs describing the scope boundary: what the solution covers, what "
        "was explicitly excluded, and where the boundary is still unresolved. Say plainly where it "
        "is unresolved rather than picking a side."
    ),
    "design_capability": (
        "Write one paragraph describing the capability the client needs in this area and how it "
        "hangs together as a business process. Do not name any product, platform, table or "
        "technology — none has been chosen."
    ),
    "design_architecture": (
        "Write 1-2 paragraphs describing the proposed architecture at a conceptual level only: the "
        "kinds of component needed, where data would live, how the parts communicate, and which "
        "stated non-functional requirements drive those choices. Do not name products or vendors."
    ),
    "design_data_model": (
        "Propose the core business entities and the relationships between them, using the client's "
        "own terms exactly as they appear in the slice. State which terms appear to be the same "
        "concept under different names, and which are attributes rather than entities. Do not "
        "invent entities that the terms do not support."
    ),
    "design_area_detail": (
        "Write one paragraph on how this capability area needs to work in detail: the information "
        "involved, the rules to enforce, and the decisions a user makes. End by naming anything the "
        "transcript leaves too vague to specify."
    ),
    "design_vocabulary": (
        "Group these business terms: which are the same concept under different names, which are "
        "entities, which are attributes of another entity, and which describe a process state "
        "rather than data. Work only from the terms and example sentences given."
    ),
    "design_roles": (
        "Propose a role structure from the groups of people named: the smallest set of roles that "
        "covers them, what each needs to do, and where the boundaries fall. Note where two named "
        "groups are probably one role."
    ),
    "design_access_rules": (
        "Explain what these access statements require of the security model: which restrictions are "
        "role-based, which are record-level, which need an explicit access list, and which are "
        "enforced by process rather than by the system."
    ),
    "design_availability": (
        "State the service levels implied by these statements — hours of operation, availability, "
        "maintenance window, recovery point and recovery time — and what each implies for hosting "
        "and backup. Where a figure was not stated, say it was not stated."
    ),
    "design_migration": (
        "Summarise the data migration position: what has to come across, from which sources, how "
        "far back, what would be archived rather than migrated, and where the scope is still "
        "genuinely unknown."
    ),
    "design_licensing": (
        "Explain where the commercial exposure sits and which design choices would move it. Do not "
        "quote prices, name licence SKUs or estimate costs — identify which decisions carry a cost."
    ),
    "design_integration": (
        "Describe the integration landscape: which systems the solution must exchange data with, in "
        "which direction, and which appear to be systems of record. Name explicitly any system "
        "that was mentioned but never described."
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


def build_transcript_prompt(purpose: str, payload: dict) -> str:
    instruction = _TRANSCRIPT_PURPOSE_INSTRUCTIONS.get(
        purpose, "Write a short factual narrative for this transcript slice."
    )
    return (
        f"{instruction}\n\n"
        f"Transcript slice (ground truth — report nothing outside it):\n"
        f"```json\n{json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)}\n```"
    )


def build_transcript_retry_prompt(purpose: str, payload: dict, violations: list[str]) -> str:
    return (
        build_transcript_prompt(purpose, payload)
        + "\n\nYour previous answer attributed statements to people who are NOT in this transcript: "
        + ", ".join(violations)
        + ". Rewrite it, attributing only to the people named in the slice, or leaving the "
        "statement unattributed."
    )
