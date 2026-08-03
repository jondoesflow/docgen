# DocGen — Executive Summary

## What it is

DocGen is a command-line tool that generates a complete, client-ready set of consultancy design documents for **Microsoft Dynamics 365 CE / Power Platform** engagements — directly from the system itself, not from memory. Give it a solution export (the zip file every Dynamics environment can produce) or a meeting transcript, and it produces the full professional document set in Word and Markdown, in minutes.

## The problem it solves

Design documentation on Dynamics engagements is expensive to write, inconsistent between consultants, and stale almost immediately — the system moves on, the documents don't. Reviews, audits and handovers then rely on documents nobody fully trusts. DocGen inverts the model: **documentation is regenerated from the source material on demand, so it never drifts.** Every generated statement is traceable to a specific piece of solution metadata or a specific line of a transcript.

## What it produces

**From a solution export:** High-Level Design, Low-Level Design, Data Dictionary, Security & Access Model, Deployment Configuration Register, Licensing Impact Summary, Solution Hygiene Report, Integration Design, and a RRAID (risks and dependencies) log — plus Release Notes comparing any two versions, with breaking-change candidates flagged.

**From a workshop or meeting transcript:** Meeting Notes, a Requirements register, an Actions & Decisions register, and the same pre-build design set — so the documents drafted at discovery can be regenerated as-built after go-live from the delivered solution. Every requirement and decision carries who said it and the line it came from.

All output is poured into your branded Word templates.

## How it works — two tiers

1. **Deterministic tier (always on, fully offline).** Data models, diagrams, inventories, security matrices, hygiene findings, licensing flags — generated entirely from the source material. Nothing leaves the machine. This is a complete, first-class mode on its own.
2. **AI narrative tier (optional).** Draft prose for overview and summary sections, written by an LLM and **validated before acceptance**: prose that invents a component that isn't in the solution, or attributes a statement to someone who wasn't in the meeting, is rejected and replaced with a visible "consultant to complete" placeholder. The AI can improve a document; it can never silently corrupt one.

## Governance and compliance

- **Offline by default** — no data leaves the machine unless the AI tier is deliberately enabled.
- **Anonymisation before anything is sent** — a configurable redaction pass strips client names, codenames and individuals; real names are restored locally so the AI provider never sees them. Every substitution is logged.
- **Provider choice is a per-engagement decision.** Anthropic is the default; OpenAI, DeepSeek, Kimi, Google Gemini, Mistral and xAI are selectable in one command. The active provider is printed on every run, so client data is never sent to a provider that wasn't consciously chosen. API keys live in the operating system's secure store — never in config files.
- **Full audit trail** — every AI call is logged (what, when, how much), and every run ends with a cost summary. A typical full document set costs **well under $1** in AI usage; $0 when run offline.

## The bottom line

DocGen turns days of documentation effort per engagement into a repeatable, minutes-long process whose output is consistent across consultants, traceable to evidence, safe to regenerate at any point in the project lifecycle, and compliant with client-by-client constraints on where data may be sent.
