# docgen — usage reference

Everything the CLI can do, with examples. See the [README](../README.md) for
the quickstart and the two-tier offline/LLM model.

## Running it on Windows

Every example below is written as `docgen …`, which works once the virtual
environment is active:

```powershell
.\.venv\Scripts\Activate.ps1
```

Without activating, use the wrapper — it forwards every argument unchanged and
creates the environment on first use:

```powershell
.\docgen.ps1 all MySolution.zip --no-llm -o out\
```

`.\docgen.ps1` with no arguments prints a quick start based on the files
actually sitting in the folder. It also smooths over two Windows argument
quirks: PowerShell splitting `--docs hld,lld` into separate arguments, and a
trailing backslash inside a quoted path (`-o "My Client\"`) escaping the
closing quote.

## Commands

docgen takes two kinds of input and the commands dispatch on what they are
given, so there is one workflow rather than two:

| Input | `parse` writes | Documents |
| --- | --- | --- |
| exported solution zip | `snapshot.json` | `hld`, `lld`, `data-dictionary`, `security`, `deployment`, `licensing`, `integration`, `rraid`, `hygiene` |
| meeting transcript (`.txt`, `.vtt`, `.md`) | `transcript-snapshot.json` | `meeting-notes`, `requirements`, `actions` + all nine of the above |

The nine shared keys are deliberate. A transcript produces the **design intent**
version of each document before the build; the solution export produces the
**as-built** version of the same document afterwards. Same key, same file name,
same Word template — see [Design documents before build](#design-documents-before-build).

### `docgen parse <solution.zip | transcript.txt> [-o OUT] [-c CONFIG]`

Parses the input into the canonical snapshot for its kind. The kind is decided
by content (a readable zip is a solution) then by suffix, not by a flag.

Outputs in the output folder:

- `snapshot.json` — the versioned, deterministically-ordered metadata snapshot
  every other command consumes (solution input), **or**
  `transcript-snapshot.json` — the equivalent for a transcript
- `parse-warnings.md` — anything docgen could not fully recognise. For a
  solution: unknown component types, unparsed families, missing flow JSON;
  components listed here are still captured as generic inventory entries. For
  a transcript: unrecognised lines, missing attendee list, missing section
  structure, speakers not on the attendee list. Nothing is silently dropped.

```bash
docgen parse MySolution_1_0_0_0.zip -o out/
docgen parse DiscoveryWorkshop.txt -o out/
```

Exit code 2 for a missing file, an invalid zip, or a file that is neither.

### `docgen render <snapshot.json> [--docs KEYS] [--format md,docx] [--no-llm] [--check-learn] [-o OUT] [-c CONFIG]`

Renders documentation from a snapshot. The document set follows the snapshot's
kind, which is read from the file.

- `--docs` — comma-separated document keys (default: all, or `default_docs` /
  `default_transcript_docs` from config).
  Solution: `hld`, `lld`, `data-dictionary`, `security`, `deployment`,
  `licensing`, `integration`, `rraid`, `hygiene`.
  Transcript: those same nine, plus `meeting-notes`, `requirements`, `actions`.
- `--format` — `md`, `docx` or both (default from config: both)
- `--no-llm` — fully offline; narrative sections become
  `[Consultant to complete]` placeholders
- `--check-learn` — also verify deprecation-rule Microsoft Learn references
  (network; writes `learn-check.md`; solution snapshots only)

```bash
docgen render out/snapshot.json --docs hld,lld --format md --no-llm -o out/
docgen render out/transcript-snapshot.json --docs meeting-notes,actions -o out/
```

Note: the Integration Design document is always produced, but when the
snapshot contains no connectors, connection references, custom connectors or
plug-in steps it is a one-page "no integrations detected" statement.

### `docgen diff <old_snapshot.json> <new_snapshot.json> [--format md,docx] [-o OUT]`

Compares two snapshots. Outputs:

- `release-notes.md` / `release-notes.docx` — added/removed/changed components
  grouped by type, schema changes first, breaking-change candidates flagged
  prominently with the metadata evidence
- `changed-components.json` — the full machine-readable change set with
  field-level paths (e.g. `attributes[abc_code].max_length: 20 -> 10`)

```bash
docgen diff v1/snapshot.json v2/snapshot.json -o diff/
```

Breaking-change heuristics include: removed tables/columns/relationships,
column type changes, tightened requirement levels, reduced max lengths,
removed choice values, removed lookup targets, changed flow triggers, removed
connection references, changed plug-in step registrations, changed environment
variable types.

### `docgen check <snapshot.json> [-o OUT] [-c CONFIG]`

Runs only the hygiene checks and writes the hygiene report — fast, always
offline.

For a **solution** snapshot: missing descriptions on custom components,
unmanaged solution, flows without error-handling scopes, unused global choice
sets, naming convention violations, deprecated features, missing dependencies
(flows referencing connection references not in the solution, steps
referencing missing assemblies).

For a **transcript** snapshot it writes the Discovery Hygiene Report instead —
the same question asked of the discovery rather than the build: themes never
discussed, requirement areas with no Must requirement, unprioritised
requirements, actions with no owner or date, parked items, attendees who never
spoke.

```bash
docgen check out/transcript-snapshot.json -o out/
```

### `docgen all <solution.zip | transcript.txt> [options] [-o OUT]`

`parse` + `check` + `render` in one step, for either input kind. Accepts the
same options as `render`.

```bash
docgen all MySolution.zip --no-llm -o out/
docgen all DiscoveryWorkshop.txt --no-llm -o out/
```

### Global

- `docgen --version`
- `docgen <command> --help`

## Transcripts

### Supported formats

Detected automatically from the file's content; `parse-warnings.md` and the
meeting notes both state which profile was used.

| Profile | Recognised by | Typical source |
| --- | --- | --- |
| `structured` | banner rules (`====` / `----`), an `ATTENDEES` block, `AF:` initials, `[ACTION:]` / `[PARKED:]` markers, end-of-document action and parked registers | a facilitated workshop written up by the BA |
| `teams_txt` | `Alex Fenwick   0:12` on its own line, then the words | Teams → *Download transcript* (.txt) |
| `vtt` | a `WEBVTT` header or `-->` cue timings; `<v Name>` voice spans are understood | Teams / Stream caption export |
| `plain` | `Alex: …` lines, or failing that blank-line separated paragraphs | hand-typed notes |

Teams and WebVTT split one turn across many cues; consecutive cues from the
same speaker are rejoined into a single turn before anything is extracted.
UTF-8, UTF-8-BOM, UTF-16 and CP1252 files all read correctly.

The richer the input, the richer the output: only the structured profile can
supply attendee roles, agenda items and section-by-section grouping. A raw
Teams export still produces every document — it just says plainly, in the
warnings and in the notes, that roles and section structure were not available.

### What gets extracted, and how to trust it

Everything deterministic is *detection*, never interpretation:

- **Requirement candidates** — sentences matching a requirement cue. Each row
  keeps the verbatim sentence, the speaker, the section and the line number.
- **Priority** — read from the words actually used (`non-negotiable` and
  `has to` → Must; `ideally` and `I'd like` → Could; `phase two` → Won't) and
  displayed next to the phrase it was read from. No signal → Unclassified,
  which is flagged for prioritisation rather than guessed at.
- **Kind** — functional, non-functional or constraint, from sentence cues
  falling back to the section the statement was made in.
- **Decisions** — statements that read as decisions, each flagged as needing
  confirmation before being treated as agreed.
- **Actions and parked items** — from the end-of-document registers where the
  transcript has them, and from `[ACTION:]` / `[PARKED:]` markers otherwise.
  Where both exist they are matched to each other, so the register's ID and
  due date are kept alongside the line where the item was actually raised.
- **RRAID seeds** — risks, assumptions, issues, dependencies and constraints,
  each quoting what was said. Impact, likelihood, owner and mitigation are
  deliberately left for the consultant.

Requirement candidates are candidates. Expect to delete a few rows of
facilitator scaffolding; that is the correct trade against silently dropping a
real requirement. Tune the cues per client with `transcript_cues.yaml` (below).

### Design documents before build

A discovery transcript produces the pre-build version of every solution
document. What changes between the two versions is the source of the content,
not the standard of evidence:

| Key | From a transcript (design intent) | From a solution export (as-built) |
| --- | --- | --- |
| `hld` | Drivers quoted from the session, capability areas derived from where requirements were raised, scope and explicit exclusions, open decisions | Solution overview, functional clusters, architecture facts, automation |
| `lld` | Requirements per area, candidate business terms, current-state process steps, requirements implying automation | ERDs per cluster, forms, views, flows, plug-in register |
| `data-dictionary` | The client's vocabulary: every repeated term with its mention count, who used it and a quote — "becomes a table?" left blank | Every table and column, types, lengths, blank descriptions flagged |
| `security` | User populations, access and confidentiality rules, audit obligations, candidate roles from job titles; empty role matrix | Role × table privilege matrices, field security profiles |
| `deployment` | Environments and sites, availability and recovery targets, support model, migration scope | Environment variables, connection references, post-deployment checklist |
| `licensing` | Cost drivers checked off against what was actually discussed, user numbers, third-party systems | Premium connectors and features detected in the metadata |
| `integration` | Every system named in the room with the sentence that named it, one design block each | Connectors, connection references, custom connectors, plug-in steps |
| `rraid` | Risks, assumptions, issues, dependencies and constraints quoted from the session | Risks and dependencies seeded from metadata findings |
| `hygiene` | **Discovery** hygiene: coverage gaps, unprioritised requirements, ownerless actions, parked items | **Build** hygiene: missing descriptions, unmanaged layers, deprecations |

Two rules keep these honest:

1. **A pre-build document never asserts schema.** No tables, no columns, no
   privilege levels — none exist yet. Every deterministic row is a quote with a
   speaker and a line number, or a count of how often a term was said.
2. **Design decisions stay with the consultant.** Which terms become tables,
   what the roles are, which interfaces are in scope: all
   `[Consultant to complete]`, or an explicitly *proposed* LLM draft.

A test enforces the first rule — it fails if a component-shaped name
(`abc_project`) ever appears in a document generated from a transcript.

The Discovery Hygiene Report is the one worth reading first. It reports what
the session did *not* establish: themes never discussed, requirement areas with
no Must, actions with no owner or date, attendees who never spoke. Run it with
`docgen check out/transcript-snapshot.json` on its own.

### Customising the cue phrases

`transcript_cues.yaml` is a rules file like the others: put a file of that name
in `rules_dir` and it **fully replaces** the shipped one (copy the shipped file
from `src/docgen/rules/` first — there is no merging). Keys:

- `requirement_cues` / `requirement_exclusions` — regexes that make a sentence
  a requirement candidate, and regexes that veto it
- `priority_cues` — an ordered list of `{priority, patterns}`; first match wins
- `kind_cues` — `non_functional` and `constraint` sentence patterns
- `section_kind_hints` — substrings of a section title used when the sentence
  itself is neutral
- `decision_cues`
- `finding_cues` — per RRAID category (`risk`, `assumption`, `issue`,
  `dependency`, `constraint`)

And for the design documents:

- `data_objects` — `min_mentions` and `max_words` for the vocabulary count,
  `exclusions` (regexes that are never a business object however often said)
  and `attribute_hints` (words that suggest a column rather than a table)
- `system_cues` — patterns with a named group `system`, feeding the interface
  inventory in the Integration Design
- `statement_groups` — a mapping of `category: {label, patterns}`. Each group
  becomes a table of verbatim statements in whichever document asks for that
  category, so **adding a new theme is a YAML change, not a code change**.
  The shipped groups are `user_population`, `access_control`, `availability`,
  `retention`, `data_migration`, `environment`, `support_model`,
  `licensing_signal`, `scope_out` and `process_step`.

All patterns are case-insensitive regexes matched against a single sentence. A
malformed pattern in an override is skipped, never fatal.

## Configuration — `docgen.yaml`

Discovery order: `--config PATH` → `./docgen.yaml` → built-in defaults.
Unknown keys are rejected with a clear error. All keys optional:

```yaml
output_dir: out                # default output folder
default_docs: [lld, data-dictionary, security, deployment,
               licensing, hygiene, hld, integration, rraid]
default_transcript_docs: [meeting-notes, requirements, actions, discovery-rraid]
formats: [md, docx]
templates_dir: templates       # per-document Word templates (see below); default: ./templates
docx_template: templates/client-brand.docx   # single fallback template (see below)
rules_dir: rules/              # rules overrides (see below)
redact_file: redact.yaml       # anonymisation rules for the LLM tier
llm:
  model: claude-sonnet-4-6
  max_tokens: 4096
  enabled: true                # config-level LLM kill-switch
```

### Environment variables

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_API_KEY` | Enables the LLM narrative tier. The **only** place the key is ever read from — never config or arguments. Missing key + LLM requested → docgen warns and falls back to placeholders. |

## Branded docx templates

Word output is poured into a docxtpl template. The shipped default is plain;
to use client branding, copy any branded .docx and add two jinja placeholders:

- `{{ title }}` — the document title (typically on the cover page)
- `{{ subtitle }}` — solution or meeting identity plus the generation note

The generated body is appended after the template content using the
template's styles — restyle `Title`, `Subtitle`, `Heading 1`–`Heading 4`,
`List Bullet` and `Table Grid` in the template to restyle the whole document.

### One template per document (`templates_dir`)

Put a template in the templates folder named after the document and docgen uses
it for that document:

```
templates/
├── HLD.docx                 # High-Level Design
├── LLD.docx                 # Low-Level Design
├── Data Dictionary.docx     # or DD.docx, or data-dictionary.docx
├── RRAID.docx
└── Meeting Notes.docx       # or Minutes.docx, or meeting-notes.docx
```

The folder defaults to `./templates`; change it with `templates_dir:` in
`docgen.yaml`. Names are matched case-insensitively and `-`, `_` and spaces are
treated alike, so `HLD.docx`, `hld.docx` and `High-Level Design.docx` are the
same thing. Accepted names per document:

| Document key | File name (any of) |
| --- | --- |
| `lld` | `lld`, `LLD`, `Low-Level Design`, `Low Level Design` |
| `data-dictionary` | `data-dictionary`, `DD`, `Data Dictionary` |
| `security` | `security`, `Security Model`, `Security & Access Model` |
| `deployment` | `deployment`, `Deployment Configuration Register`, `Deployment Register` |
| `licensing` | `licensing`, `Licensing Impact Summary` |
| `hygiene` | `hygiene`, `Solution Hygiene Report`, `Hygiene Report` |
| `hld` | `hld`, `HLD`, `High-Level Design`, `High Level Design` |
| `integration` | `integration`, `Integration Design` |
| `rraid` | `rraid`, `RRAID`, `RRAID Log` |
| `release-notes` | `release-notes`, `Release Notes` |
| `meeting-notes` | `meeting-notes`, `Meeting Notes`, `Minutes`, `Meeting Minutes` |
| `requirements` | `requirements`, `Requirements Catalogue` |
| `actions` | `actions`, `Actions & Decisions Register`, `Action Log` |
| `discovery-rraid` | `discovery-rraid`, `Discovery RRAID`, `Discovery RRAID Log` |

Resolution order per document, first hit wins:

1. `<templates_dir>/<matching name>.docx`
2. `docx_template:` from config — one template for everything
3. the plain template shipped inside the package

So the folder is opt-in one document at a time: a folder holding only
`HLD.docx` brands the HLD and leaves everything else exactly as it was. The
console line for each document names the template it used.

Beyond `{{ title }}` and `{{ subtitle }}`, a template may reference these
optional placeholders (empty when not applicable):

- **all documents** — `{{ doc_key }}`, `{{ doc_title }}`, `{{ source_file }}`,
  `{{ generated_at }}`, `{{ docgen_version }}`
- **solution documents** — `{{ solution_name }}`, `{{ solution_unique_name }}`,
  `{{ version }}`, `{{ managed }}`, `{{ publisher }}`
- **transcript documents** — `{{ meeting_title }}`, `{{ client }}`,
  `{{ consultancy }}`, `{{ meeting_date }}`, `{{ meeting_time }}`,
  `{{ location }}`, `{{ facilitator }}`

The shipped default template is regenerated with
`python scripts/make_default_template.py`.

## Extending the rules files

Four YAML rule files drive the licensing, hygiene, RRAID and transcript
detections. Defaults ship inside the package; to customise, set `rules_dir:` in
`docgen.yaml` — a file of the same name there **fully replaces** the shipped
one (copy the shipped file first; there is no merging).

- **`licensing.yaml`** — `premium_connectors` (list of `{api_name, label,
  note}`), `standard_connectors` (list of API names), `signals` (non-connector
  premium markers, e.g. `kind: custom_connector`)
- **`deprecations.yaml`** — `deprecations` list of `{id, match: {kind, value},
  title, guidance, learn_url}`. Supported `kind`s: `connector`,
  `plugin_isolation`, `web_resource_type`.
- **`naming.yaml`** — `rules` list of `{id, target, pattern, applies_to,
  severity, message}`. Targets: `entity`, `attribute`, `flow`,
  `environment_variable`, `web_resource`, `connection_reference`. `pattern`
  is a regex the full name must match; `applies_to: custom_only` limits to
  custom components.
- **`transcript_cues.yaml`** — the cue phrases that seed requirements,
  decisions and RRAID entries from a transcript. See
  [Customising the cue phrases](#customising-the-cue-phrases) above.

The shipped files (in `src/docgen/rules/`) are the reference for the exact
format.

## LLM cost reporting

Every run that calls the Anthropic API ends with a usage summary on the console:

```
  LLM usage: 9 call(s), 61,204 input + 4,318 output tokens (claude-sonnet-4-6) - estimated cost $0.2484 USD
  (estimate from published API prices; the Anthropic console is authoritative)
```

The estimate is computed from published per-token API prices for the
configured model (see `src/docgen/llm/pricing.py`; update that table if
Anthropic's pricing changes). Unknown models still get the token counts, just
no dollar figure. Per-call token detail is in `<output>/llm-log.jsonl`.
Offline (`--no-llm`) runs print nothing — nothing was sent, nothing was spent.

## Anonymisation — `redact.yaml`

Applied to every payload before it reaches the Anthropic API. See
[redact.example.yaml](../redact.example.yaml). `replacements` are exact-string
swaps reversed in responses (local docs keep real names); `patterns` are
one-way regex redactions. Substitutions are logged to
`<output>/redaction-log.md`; API calls to `<output>/llm-log.jsonl`.

For transcripts this matters more than it does for solution metadata: the
slices sent for meeting and section summaries contain speaker names and quoted
sentences. List the client organisation and every attendee in `replacements`
before running the LLM tier over a transcript — or use `--no-llm`, which sends
nothing and still fills every table in every document.

## Sample output

`docgen all tests/fixtures/rich.zip --no-llm -o out/` produces:

```
out/
├── snapshot.json            # canonical snapshot (git-diffable)
├── parse-warnings.md        # 2 warnings: unknown component type, missing flow JSON
├── lld.md / lld.docx        # + data-dictionary, security, deployment,
├── ...                      #   licensing, hygiene, hld, integration, rraid
└── diagrams/                # PNGs when mermaid-cli or Graphviz is installed
```

An excerpt from the hygiene report:

| Rule | Severity | Component | Finding | Evidence |
| --- | --- | --- | --- | --- |
| FLOW-001 | warning | flow Sync invoices to SQL | Flow has no error-handling path... | cloud_flows[...].has_error_scope = false over 2 action(s) |

## Troubleshooting

**"Not a valid zip file"** — the input must be the exported solution zip
itself, not an unzipped folder or a managed `.cab`. Re-export from the maker
portal (Solutions → Export).

**Documents render but diagrams are code blocks** — neither `mmdc`
(mermaid-cli, `npm install -g @mermaid-js/mermaid-cli`) nor Graphviz `dot` is
on PATH. This is by design: the run never fails over diagrams. Markdown always
embeds Mermaid source (renders on GitHub/Azure DevOps); paste into
https://mermaid.live for one-offs.

**"Snapshot schema version X is not compatible"** — the snapshot was produced
by a different major version of docgen. Re-run `docgen parse` on the original
zip.

**LLM narrative missing / placeholders despite no `--no-llm`** — check
`ANTHROPIC_API_KEY` is exported in the same shell, and look for yellow
warnings in the output: rejected narratives (invented component names) and API
errors both degrade to placeholders by design. `llm-log.jsonl` shows what was
attempted.

**Lots of `unknown_component` parse warnings** — expected for component types
docgen has no specialised parser for (they still appear in the generic
inventory and the LLD component inventory). If a component family you care
about is listed, raise it — adding a parser is a contained change (see
ARCHITECTURE.md).

**Config errors** — `docgen.yaml` rejects unknown keys with the offending
field named. Check for typos; the example file in the repo root lists every
valid key.

**"Unrecognised input"** — the file is neither a readable zip nor a transcript
suffix docgen accepts (`.txt`, `.vtt`, `.md`, `.text`, `.transcript`). Rename
the transcript, or check the export actually produced a file.

**A transcript parses but finds almost nothing** — check the `Source format`
row in the meeting notes. Falling back to `plain` usually means the speaker
lines are not in a shape docgen recognises (no `Name: text`, no
`Name   0:12`). Either re-export from Teams, or add `Name:` prefixes. If the
format is right but requirements are sparse, the client's phrasing is not
matching the shipped cues — override `transcript_cues.yaml`.

**Every speaker shows as "Unconfirmed"** — the transcript declares no attendee
block, so sides, roles and organisations are genuinely unknown. That is
reported as a `no_attendee_list` warning rather than guessed; complete the
attendee table in the notes.

**Requirement rows that are obviously not requirements** — expected, and the
reason they say "candidate". Requirement extraction errs towards including a
sentence rather than dropping a real requirement. Delete the rows, or tighten
`requirement_exclusions` in an overriding `transcript_cues.yaml`.

**A per-document template is not being picked up** — check the file is in
`templates_dir` (default `./templates`), has a `.docx` suffix, and its stem
matches one of the accepted names in the table above. The console line for
each document names the template it used, so a document rendering without a
`[template …]` suffix did not match.
