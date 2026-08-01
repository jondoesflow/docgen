# docgen — architecture

## The snapshot-first principle

```
solution.zip ──parse──▶ snapshot.json ──render──▶ documents (md + docx)
                             │
                             ├──check──▶ hygiene report
                             └──diff (two snapshots)──▶ release notes
```

Parsing and rendering are fully decoupled. `parse` is the only code that reads
the zip; every renderer consumes only the snapshot; `diff` compares two
snapshots. This is what makes the documents "living": re-export, re-parse,
re-render, and every document is true again.

## Snapshot schema (`src/docgen/snapshot/models.py`)

Top-level `Snapshot` (pydantic, `extra="forbid"`), `schema_version = "1.0"`:

| Field | Model | Key field |
| --- | --- | --- |
| `solution` | `SolutionMeta` (+ `Publisher`) | — |
| `entities` | `Entity` → `Attribute`, `Relationship`, `Form`, `View`, `BusinessRule` | `logical_name` |
| `global_option_sets` | `OptionSet` → `Option` | `name` |
| `security_roles` | `SecurityRole` → `RolePrivilege` | `name` |
| `field_security_profiles` | `FieldSecurityProfile` → `FieldPermission` | `name` |
| `cloud_flows` | `CloudFlow` → `FlowTrigger`, `FlowAction` | `unique_name` |
| `connection_references` | `ConnectionReference` | `logical_name` |
| `environment_variables` | `EnvironmentVariable` | `schema_name` |
| `plugin_assemblies` / `plugin_steps` | `PluginAssembly` / `PluginStep` | `name` |
| `web_resources` | `WebResource` | `name` |
| `custom_connectors` / `canvas_apps` | `CustomConnector` / `CanvasApp` | `name` |
| `other_components` | `GenericComponent` (unrecognised, never dropped) | `schema_name_or_id` |
| `warnings` | `ParseWarning` (code, context, message) | — |

Conventions:

- **Key fields** are what `snapshot/io.py::canonicalise` sorts by and what the
  diff engine matches on. Serialisation is deterministic — same solution, same
  bytes — so snapshots are git-diffable and golden tests compare text.
- **Values stay plain** (`str`/`int`/`bool`), normalised where useful
  (`requirement_level`, privilege levels, stages/modes). Odd values from
  unusual exports degrade to the raw string plus a warning, never a crash.
- `generated_at` / `docgen_version` are metadata, zeroed in golden
  comparisons.
- Version policy: same major version loads (minor additions allowed); a major
  mismatch is a hard error telling the user to re-parse.

## Parsers (`src/docgen/parsers/`)

One module per component family, orchestrated by `parse_solution` in
`__init__.py`. Shared infrastructure in `base.py`: `ParseContext` (open zip,
case-insensitive file index, warnings sink, root-component claims) and
tolerant accessors (`text`, `loc_text`, `to_bool`…) that default instead of
raising.

Tolerance contract: each component parses inside its own try/except → a broken
component becomes a `component_error` warning, and parsing continues.

The "nothing silently dropped" guarantee has two layers:

1. Unmapped top-level `customizations.xml` families → `unparsed_element`
   warning.
2. Every `RootComponent` in `solution.xml` is either **claimed** by a parser
   (`ctx.claim(type_code, key)`) or captured as a `GenericComponent` +
   `unknown_component` warning by `generic.py`.

## Renderers (`src/docgen/renderers/`)

One shared format-neutral **DocModel** (`docmodel.py`: `Document`, `Section`,
`Paragraph`, `Table`, `BulletList`, `CodeBlock`, `Diagram`, `Placeholder`,
`Callout`) with two emitters — `markdown.py` and `docx.py`. Because both walk
the same tree, the formats cannot drift apart and doc renderers contain zero
format code.

- `Diagram` carries Mermaid source (always) and a DOT equivalent. Markdown
  embeds the Mermaid; docx tries `mmdc` → `dot` → source-in-code-block with a
  note (`diagrams.py`). A missing renderer never fails a run.
- `clusters.py` groups entities into functional clusters by relationship
  connectivity (hub entities like `systemuser` excluded from edges; oversized
  components split by removing the highest-degree node).
- `RenderContext` (`base.py`) carries config, loaded rules, and the
  **narrative provider** — a `(purpose, payload) -> str | None` callable.
  Under `--no-llm` it always returns `None` and `ctx.narrative(...)` yields a
  `Placeholder`. Renderers never know whether the LLM is on.

### Adding a new document renderer

1. Create `src/docgen/renderers/docs/my_doc.py`:

   ```python
   from docgen.renderers.base import DocRenderer, RenderContext
   from docgen.renderers.docmodel import Document, Section, Table

   class MyDocRenderer(DocRenderer):
       key = "my-doc"
       title = "My Document"

       def build(self, snapshot, ctx: RenderContext) -> Document:
           doc = Document(title=f"{self.title} — {snapshot.solution.display_name}",
                          subtitle=self.subtitle(snapshot))
           doc.add(Section("Facts").add(Table(headers=[...], rows=[...])))
           return doc
   ```

2. Register it in `renderers/__init__.py::DOC_RENDERERS` and add the key to
   `constants.ALL_DOC_KEYS`.
3. Done — both formats, `--docs` filtering, and the renderer test matrix
   (`tests/test_render.py` iterates the registry) pick it up automatically.

Override `applies(snapshot)` to skip a document for solutions where it makes
no sense, and use `ctx.narrative(purpose, payload, hint)` for any prose slot
that a human (or the LLM tier) should write.

## Diff engine (`src/docgen/diffing/`)

`engine.py` indexes every collection by its key field: added/removed keys are
whole-component changes; common keys are compared as dicts with nested keyed
lists re-indexed (so a change path reads
`attributes[abc_code].max_length: 20 -> 10`). `breaking.py` classifies each
change against D365-specific heuristics, every flag carrying its evidence.
The release-notes builder consumes the resulting `ChangeSet`.

## Hygiene + rules (`src/docgen/hygiene/`, `src/docgen/rules_io.py`)

`checks.py` produces `Finding`s (rule id, severity, component, message,
**evidence**) consumed by both the hygiene report and the RRAID seeds — one
detection engine, two documents. Rules ship as package data
(`src/docgen/rules/*.yaml`); a same-named file in the configured `rules_dir`
fully replaces the shipped one.

## LLM tier (`src/docgen/llm/`)

`make_narrative_provider` wires the pipeline per request:
payload → redact (`redact.py`) → prompt (`prompts.py`, with the ground-truth
instruction) → API (`client.py`, key from env only, calls logged) →
validate (`validate.py`: every component-shaped token must exist in the
snapshot, rapidfuzz ≥ 90 for trivial drift) → one retry naming the violations
→ un-redact → prose. Every failure path returns `None`, which renders as a
placeholder: the LLM can improve a document but can never break a run or
invent a component.

## Test strategy (`tests/`)

- `fixture_builder.py` constructs realistic solution zips programmatically
  (deterministic GUIDs + zip timestamps); committed fixtures are rebuilt
  byte-identically. Fixtures: `minimal`, `rich` (flows/plugins/roles/etc. plus
  deliberate warts for hygiene findings), `diff_v1`/`diff_v2` (every breaking
  heuristic).
- Golden snapshot tests byte-compare parser output
  (`pytest --update-goldens` regenerates after intentional changes).
- The renderer matrix renders **every registered doc × every fixture × both
  formats** offline.
- The milestone gate test runs `docgen all --no-llm` end-to-end with socket
  access stubbed out, proving the offline tier needs no network.
- LLM tests are fully mocked, including the mandated
  "response naming a non-existent entity is rejected" case.
