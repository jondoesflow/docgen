# docgen

**Living consultancy documentation for Dynamics 365 CE / Power Platform
engagements — from the solution you built, and from the meetings you ran.**

`docgen` takes two kinds of input:

- an **exported solution zip** → HLD, LLD, data dictionary, security model,
  deployment register, licensing summary, hygiene report, integration design
  and RRAID, plus release notes when you feed it two versions;
- a **meeting transcript** (`.txt` from Teams, `.vtt`, or a facilitated
  workshop transcript) → meeting notes, a requirements catalogue, an actions
  and decisions register, and a discovery RRAID log.

The documents stay truthful because they are **regenerated from the source
material**, not written once and left to drift. Every generated statement is
traceable: to a specific metadata element for a solution, or to the verbatim
sentence, speaker and line number for a transcript. Narrative and judgement
sections are either drafted by an optional LLM tier or left as clearly marked
`[Consultant to complete]` placeholders — docgen augments the consultant, it
does not replace them.

## Install

Python 3.11+ required.

On Windows, the one-shot setup script creates `.venv`, installs docgen and
smoke-tests it (`-Dev` also installs pytest and runs the test suite):

```powershell
.\setup.ps1
```

Then run it with the wrapper — no activation, and it creates the environment
on first use if you skipped `setup.ps1` entirely:

```powershell
.\docgen.ps1                                       # what you can run right now
.\docgen.ps1 all MySolution.zip --no-llm -o out\   # solution → document set
.\docgen.ps1 all Workshop.txt --no-llm -o out\     # transcript → document set
```

Everything after `.\docgen.ps1` is passed straight to the CLI, so every example
below works there too. To type plain `docgen` instead, activate the environment
in your shell first — a script can't put a command on the PATH of the shell
that called it:

```powershell
.\.venv\Scripts\Activate.ps1
docgen all MySolution.zip --no-llm -o out\
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

## Quickstart — meeting transcript to a document set

The same commands take a transcript and dispatch on what they are given:

```bash
docgen all DiscoveryWorkshop.txt --no-llm -o out/
```

`out/` now contains `transcript-snapshot.json`, `parse-warnings.md`, and twelve
documents in Markdown and Word: the record of the session (`meeting-notes`,
`requirements`, `actions`) plus the pre-build design set (`hld`, `lld`,
`data-dictionary`, `security`, `deployment`, `licensing`, `integration`,
`rraid`, `hygiene`) — the same document keys the solution export produces after
the build. See [One document, two points in its life](#one-document-two-points-in-its-life).

Four transcript shapes are recognised automatically:

| Shape | Looks like | Typical source |
| --- | --- | --- |
| Structured workshop | banner-ruled sections, an attendee block, `AF:` initials, `[ACTION:]` markers, an end-of-document action register | a facilitated workshop written up by the BA |
| Teams `.txt` | `Alex Fenwick   0:12` then the words | Teams → *Download transcript* |
| WebVTT `.vtt` | `00:00:12.340 --> …` with `<v Alex Fenwick>` | Teams / Stream caption export |
| Plain | `Alex: …` lines | hand-typed notes |

Whatever the shape, every requirement, decision and RRAID entry carries the
sentence it came from, who said it and the line number, so any row can be
checked against the recording in seconds.

## The two-tier model: offline first, LLM optional

**Tier 1 — deterministic (`--no-llm`).** Fully offline. Every document is
generated in full from the snapshot: data model, ERDs, inventories, privilege
matrices, deployment registers, hygiene findings, licensing flags, release
notes; and for a transcript, the attendee table, agenda, per-section coverage,
requirement candidates with their priority wording, decisions, actions, parked
items and RRAID seeds. Narrative sections (solution overview prose,
plain-English flow descriptions, meeting and section summaries, formal
requirement wording) appear as `[Consultant to complete]` placeholders with a
hint describing what belongs there. This is a first-class mode, not a degraded
one — the Actions & Decisions Register is complete offline and can be
circulated the moment the transcript lands.

**Tier 2 — LLM narrative (optional).** With `ANTHROPIC_API_KEY` set and
`--no-llm` omitted, docgen drafts those narrative sections using the Anthropic
API (`claude-sonnet-4-6` by default). The LLM only ever **adds prose** — no
document depends on it to exist. Every response is validated against the
snapshot, on the axis that matters for that document:

- **Solution documents** — if the prose names a table, flow or component that
  does not exist in the metadata, it is rejected.
- **Transcript documents** — if the prose attributes a statement to somebody
  who was not in the meeting (“X said…”, “according to X”), it is rejected.
  Putting words in a client's mouth is the failure that discredits a set of
  notes, so it is the thing that is checked.

Either way the response is retried once naming the violations; if it fails
again, the placeholder is used. No invented capabilities, no invented
attributions.

## Compliance: what leaves the machine, and when

- **Nothing, by default.** `--no-llm` runs are fully offline. All inputs and
  outputs are local files; docgen keeps no state outside the output folder and
  sends no telemetry.
- **With the LLM tier**: only the slices needed for each narrative section are
  sent to the Anthropic API. Before anything is sent, a configurable
  anonymisation pass (`redact.yaml` — see
  [redact.example.yaml](redact.example.yaml)) replaces client names, project
  codenames and named individuals; named replacements are reversed in the
  response, so local documents keep real names while the API never sees them.
  Every substitution is logged to `<output>/redaction-log.md` and every API
  call to `<output>/llm-log.jsonl` (prompt hash and token counts, not content).
- **Transcripts raise the stakes on that.** A workshop transcript is people,
  commercial numbers and candid opinions, not schema. Slices sent for
  transcript narrative include speaker names and quoted sentences, so
  configure `redact.yaml` before running the LLM tier over one — or run
  `--no-llm`, which sends nothing at all and still produces every table in
  every document.
- **With `--check-learn`**: docgen fetches the Microsoft Learn URLs listed in
  the deprecation rules to verify they are still reachable. No solution data
  is sent — only the rule URLs are requested.
- The API key is read from the `ANTHROPIC_API_KEY` environment variable only —
  never from config files or command-line arguments.

## The document set

### From a solution zip

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

### From a transcript

The session record — three documents with no solution counterpart:

| Document | Key | Content |
| --- | --- | --- |
| Meeting Notes | `meeting-notes` | Meeting facts, attendees with contribution share, agenda, per-section coverage and verbatim points, decisions, actions, parked items |
| Requirements Catalogue | `requirements` | Requirement candidates by type and priority, each quoting the sentence, the speaker and the line; priority shown next to the phrase it was read from |
| Actions & Decisions Register | `actions` | Actions with owners and dates (missing ones flagged), actions by owner, decisions, parked items — complete offline |

**And the same nine keys as the solution set**, produced as *design intent*
before the build: `hld`, `lld`, `data-dictionary`, `security`, `deployment`,
`licensing`, `integration`, `rraid`, `hygiene`.

## One document, two points in its life

Design documents are written before a build and are meant to be true after it.
docgen produces both versions from the same document key:

```
workshop transcript ──▶  hld, lld, data-dictionary, …   design intent
                                    │                   "what we agreed to build"
        build happens               ▼
solution export     ──▶  hld, lld, data-dictionary, …   as-built
                                                        "what actually got built"
```

Same key, same Word template, same file name. Regenerating after go-live is
what proves the two still agree — and the diff between them is the difference
between what was agreed and what was delivered.

What changes is where the content comes from, never how honest it is:

| Document | Before build, from the workshop | After build, from the export |
| --- | --- | --- |
| `hld` | Drivers quoted from the session, capability areas from where requirements were raised, scope and exclusions | Solution overview, functional clusters, architecture facts |
| `lld` | Requirements per area, candidate business terms, process steps described, automation implied | ERDs, forms, views, flows, plug-in register |
| `data-dictionary` | The client's vocabulary with mention counts and a quote each — "becomes a table?" left to a human | Every table and column with types and lengths |
| `security` | User populations, access rules and audit obligations as stated; empty role matrix | Role × table privilege matrices, field security |
| `deployment` | Environments, availability, recovery, support model, migration scope | Environment variables, connection references, checklist |
| `licensing` | Cost drivers checked off against what was discussed; user numbers | Premium connectors and features detected |
| `integration` | Every system named in the room, with the sentence that named it | Connectors, connection references, custom connectors |
| `rraid` | Risks and issues quoted from the session | Risks seeded from metadata findings |
| `hygiene` | *Discovery* hygiene: is this good enough to design and estimate from? | Build hygiene: missing descriptions, unmanaged layers, deprecations |

A pre-build document never asserts schema, because none exists. It quotes what
was said, counts what was repeated, and leaves every design decision as a
`[Consultant to complete]` placeholder — enforced by a test that fails if any
component-shaped name appears in a document generated from a transcript.

## Branded Word templates, per document

Drop Word templates into a `templates/` folder named after the document —
`HLD.docx`, `LLD.docx`, `Data Dictionary.docx`, `Meeting Notes.docx` — and that
document is poured into that template, using its styles, headers and footers.
Names match case- and separator-insensitively (`hld.docx`, `HLD.docx`,
`High-Level Design.docx` are all the HLD). Any document without a template
falls back to `docx_template` from config, then to the plain shipped template,
so the folder is opt-in one document at a time.

Because a document key is the same before and after build, `HLD.docx` styles
the HLD drafted from the workshop *and* the one regenerated from the solution
export — one house style per document, for its whole life. See
[docs/USAGE.md](docs/USAGE.md#branded-docx-templates).

## Architecture in one paragraph

`parse` turns the input into a canonical, versioned snapshot — `snapshot.json`
for a solution zip, `transcript-snapshot.json` for a meeting transcript (both
pydantic-modelled, deterministically ordered, git-diffable). Everything else —
`render`, `check`, `diff` — consumes snapshots only, never the source file, and
dispatches on the snapshot's kind. Anything docgen has no specialised parser
for is captured anyway: an unrecognised solution component becomes a generic
inventory entry, an unrecognised transcript line is counted and reported.
Nothing is silently dropped. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## More

- Full CLI reference, configuration, branded templates, rules customisation,
  troubleshooting: [docs/USAGE.md](docs/USAGE.md)
- Snapshot schemas and how to add a new document renderer:
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Diagrams: Markdown embeds Mermaid source; Word embeds rendered images when
  `mmdc` (mermaid-cli) or Graphviz `dot` is installed, otherwise the diagram
  source with a note — a missing renderer never fails a run.
