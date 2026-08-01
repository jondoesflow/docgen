# docgen

**Living design documentation for Dynamics 365 CE / Power Platform solutions.**

`docgen` takes an exported solution zip and generates a full consultancy
documentation set — HLD, LLD, data dictionary, security model, deployment
register, licensing summary, hygiene report, integration design and RRAID —
plus release notes when you feed it two versions.

The documents stay truthful because they are **regenerated from solution
metadata**, not written once and left to drift. Every generated statement is
traceable to a specific metadata element. Narrative and judgement sections are
either drafted by an optional LLM tier or left as clearly marked
`[Consultant to complete]` placeholders — docgen augments the consultant, it
does not replace them.

## Install

Python 3.11+ required.

On Windows, the one-shot setup script creates `.venv`, installs docgen and
smoke-tests it (`-Dev` also installs pytest and runs the test suite):

```powershell
.\setup.ps1
```

Or manually:

```bash
pip install .
```

or, isolated on your PATH with [pipx](https://pipx.pypa.io):

```bash
pipx install .
```

## Quickstart — zip to full doc set in three commands

```bash
docgen parse MySolution.zip -o out/
```

```bash
docgen check out/snapshot.json -o out/
```

```bash
docgen render out/snapshot.json --no-llm -o out/
```

Or all three in one step:

```bash
docgen all MySolution.zip --no-llm -o out/
```

`out/` now contains `snapshot.json` (the canonical metadata snapshot),
`parse-warnings.md`, and every document in Markdown and Word (`.docx`) form.

Release notes for what changed between two versions:

```bash
docgen diff out-v1/snapshot.json out-v2/snapshot.json -o out-diff/
```

## The two-tier model: offline first, LLM optional

**Tier 1 — deterministic (`--no-llm`).** Fully offline. Every document is
generated in full from the snapshot: data model, ERDs, inventories, privilege
matrices, deployment registers, hygiene findings, licensing flags, release
notes. Narrative sections (solution overview prose, plain-English flow
descriptions, RRAID phrasing) appear as `[Consultant to complete]`
placeholders with a hint describing what belongs there. This is a first-class
mode, not a degraded one.

**Tier 2 — LLM narrative (optional).** With `ANTHROPIC_API_KEY` set and
`--no-llm` omitted, docgen drafts those narrative sections using the Anthropic
API (`claude-sonnet-4-6` by default). The LLM only ever **adds prose** — no
document depends on it to exist. Every response is validated against the
snapshot: if it names a table, flow or component that does not exist in the
metadata, it is rejected and retried once; if it fails again, the placeholder
is used. No invented capabilities.

## Compliance: what leaves the machine, and when

- **Nothing, by default.** `--no-llm` runs are fully offline. All inputs and
  outputs are local files; docgen keeps no state outside the output folder and
  sends no telemetry.
- **With the LLM tier**: only the metadata slices needed for each narrative
  section are sent to the Anthropic API. Before anything is sent, a
  configurable anonymisation pass (`redact.yaml` — see
  [redact.example.yaml](redact.example.yaml)) replaces client names, project
  codenames and named individuals; named replacements are reversed in the
  response, so local documents keep real names while the API never sees them.
  Every substitution is logged to `<output>/redaction-log.md` and every API
  call to `<output>/llm-log.jsonl` (prompt hash and token counts, not content).
- **With `--check-learn`**: docgen fetches the Microsoft Learn URLs listed in
  the deprecation rules to verify they are still reachable. No solution data
  is sent — only the rule URLs are requested.
- The API key is read from the `ANTHROPIC_API_KEY` environment variable only —
  never from config files or command-line arguments.

## The document set

| Document | Key | Content |
| --- | --- | --- |
| Low-Level Design | `lld` | Data model + ERDs per functional cluster, forms/views, flows, plug-in register, full inventory |
| Data Dictionary | `data-dictionary` | Every table and column; blank descriptions visibly flagged |
| Security & Access Model | `security` | Role × table privilege matrices, field security profiles |
| Deployment Configuration Register | `deployment` | Environment variables, connection references, post-deployment checklist |
| Licensing Impact Summary | `licensing` | Premium connectors/features detected, flagged for commercial review |
| Solution Hygiene Report | `hygiene` | Missing descriptions, unmanaged layers, flows without error handling, naming violations, deprecations |
| High-Level Design | `hld` | Deterministic skeleton + narrative (LLM or placeholder) |
| Integration Design | `integration` | Auto-generated integration inventory + consultant template sections |
| RRAID Log | `rraid` | Risks/dependencies seeded from metadata with evidence + human-judgement sections |
| Release Notes | (from `diff`) | Added/removed/changed components, breaking-change candidates flagged |

## Architecture in one paragraph

`parse` turns the zip into a canonical, versioned `snapshot.json`
(pydantic-modelled, deterministically ordered, git-diffable). Everything else —
`render`, `check`, `diff` — consumes snapshots only, never the zip. Anything
in a solution that docgen has no specialised parser for is captured as a
generic inventory entry with a parse warning: nothing is silently dropped.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## More

- Full CLI reference, configuration, branded templates, rules customisation,
  troubleshooting: [docs/USAGE.md](docs/USAGE.md)
- Snapshot schema and how to add a new document renderer:
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Diagrams: Markdown embeds Mermaid source; Word embeds rendered images when
  `mmdc` (mermaid-cli) or Graphviz `dot` is installed, otherwise the diagram
  source with a note — a missing renderer never fails a run.
