# docgen — usage reference

Everything the CLI can do, with examples. See the [README](../README.md) for
the quickstart and the two-tier offline/LLM model.

## Commands

### `docgen parse <solution.zip> [-o OUT] [-c CONFIG]`

Parses an exported solution zip into the canonical snapshot.

Outputs in the output folder:

- `snapshot.json` — the versioned, deterministically-ordered metadata snapshot
  every other command consumes
- `parse-warnings.md` — anything docgen could not fully recognise (unknown
  component types, unparsed families, missing flow JSON). Components listed
  here are still captured as generic inventory entries — nothing is silently
  dropped.

```bash
docgen parse MySolution_1_0_0_0.zip -o out/
```

Exit code 2 for a missing or invalid zip.

### `docgen render <snapshot.json> [--docs KEYS] [--format md,docx] [--no-llm] [--check-learn] [-o OUT] [-c CONFIG]`

Renders documentation from a snapshot.

- `--docs` — comma-separated document keys (default: all, or `default_docs`
  from config): `lld`, `data-dictionary`, `security`, `deployment`,
  `licensing`, `hygiene`, `hld`, `integration`, `rraid`
- `--format` — `md`, `docx` or both (default from config: both)
- `--no-llm` — fully offline; narrative sections become
  `[Consultant to complete]` placeholders
- `--check-learn` — also verify deprecation-rule Microsoft Learn references
  (network; writes `learn-check.md`)

```bash
docgen render out/snapshot.json --docs hld,lld --format md --no-llm -o out/
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
offline. Checks: missing descriptions on custom components, unmanaged
solution, flows without error-handling scopes, unused global choice sets,
naming convention violations, deprecated features, missing dependencies
(flows referencing connection references not in the solution, steps
referencing missing assemblies).

### `docgen all <solution.zip> [options] [-o OUT]`

`parse` + `check` + `render` in one step. Accepts the same options as
`render`.

```bash
docgen all MySolution.zip --no-llm -o out/
```

### Global

- `docgen --version`
- `docgen <command> --help`

## Configuration — `docgen.yaml`

Discovery order: `--config PATH` → `./docgen.yaml` → built-in defaults.
Unknown keys are rejected with a clear error. All keys optional:

```yaml
output_dir: out                # default output folder
default_docs: [lld, data-dictionary, security, deployment,
               licensing, hygiene, hld, integration, rraid]
formats: [md, docx]
docx_template: templates/client-brand.docx   # branded template (see below)
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
- `{{ subtitle }}` — solution name, version and generation note

The generated body is appended after the template content using the
template's styles — restyle `Title`, `Subtitle`, `Heading 1`–`Heading 4`,
`List Bullet` and `Table Grid` in the template to restyle the whole document.
Point config at it:

```yaml
docx_template: templates/client-brand.docx
```

The shipped default template is regenerated with
`python scripts/make_default_template.py`.

## Extending the rules files

Three YAML rule files drive the licensing, hygiene and RRAID detections.
Defaults ship inside the package; to customise, set `rules_dir:` in
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

The shipped files (in `src/docgen/rules/`) are the reference for the exact
format.

## Anonymisation — `redact.yaml`

Applied to every payload before it reaches the Anthropic API. See
[redact.example.yaml](../redact.example.yaml). `replacements` are exact-string
swaps reversed in responses (local docs keep real names); `patterns` are
one-way regex redactions. Substitutions are logged to
`<output>/redaction-log.md`; API calls to `<output>/llm-log.jsonl`.

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
