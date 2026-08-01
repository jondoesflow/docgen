# docgen — architecture

## The snapshot-first principle

```
solution.zip ──parse──▶ snapshot.json ──render──▶ documents (md + docx)
                             │
                             ├──check──▶ hygiene report
                             └──diff (two snapshots)──▶ release notes

transcript.txt ─parse──▶ transcript-snapshot.json ──render──▶ documents (md + docx)
   .vtt / .md
```

Parsing and rendering are fully decoupled. `parse` is the only code that reads
the source file; every renderer consumes only a snapshot; `diff` compares two
snapshots. This is what makes the documents "living": re-export or
re-transcribe, re-parse, re-render, and every document is true again.

Two snapshot kinds share the pipeline. They are told apart on disk by a `kind`
discriminator that only transcript snapshots carry, so existing solution
snapshots stay byte-identical to what earlier versions wrote:

| | Solution | Transcript |
| --- | --- | --- |
| Source | exported solution zip | `.txt` / `.vtt` / `.md` transcript |
| Parser | `parsers/` | `transcripts/` |
| Model | `snapshot/models.py::Snapshot` | `snapshot/transcript.py::TranscriptSnapshot` |
| File | `snapshot.json` | `transcript-snapshot.json` (`"kind": "transcript"`) |
| Registry | `renderers.DOC_RENDERERS` | `renderers.TRANSCRIPT_DOC_RENDERERS` |
| Base class | `DocRenderer` | `TranscriptDocRenderer` |
| Ground truth for the LLM tier | component names must exist | attributions must name a real participant |

`snapshot/io.py::snapshot_kind` reads the discriminator; `cli.py` dispatches
`parse`, `render`, `check` and `all` on it (and on the input file for
`parse`/`all`), so the user learns one workflow rather than two.

## Shared document keys: design intent and as-built

The two registries **deliberately share nine document keys** — `hld`, `lld`,
`data-dictionary`, `security`, `deployment`, `licensing`, `integration`,
`rraid`, `hygiene`:

```
workshop transcript ──▶ TRANSCRIPT_DOC_RENDERERS[hld] ──▶ hld.md/.docx   design intent
solution export     ──▶ DOC_RENDERERS[hld]            ──▶ hld.md/.docx   as-built
```

Same key, same output file name, same Word template, two points in one
document's life. `--docs` validates against the registry matching the snapshot
kind, so the keys never collide at runtime, and a test asserts that every
solution key has a transcript counterpart.

Pre-build renderers subclass `DesignDocRenderer`
(`renderers/docs/transcript_design.py`), which supplies the standing header
explaining that the document is design intent and how to regenerate it
as-built. The honesty contract is tighter on this side than anywhere else in
docgen, because a transcript contains no schema at all:

- deterministic content is a **quote with a speaker and a line**, or a **count
  of how often a term was said** — never an assertion about a table;
- every design decision is a `[Consultant to complete]` placeholder or an
  explicitly *proposed* LLM draft.

`tests/test_transcript_render.py` enforces the first rule directly: it fails if
a publisher-prefixed logical name (`abc_project`) appears in any document
generated from a transcript, since nothing in a transcript could produce one.

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

## Transcript snapshot schema (`src/docgen/snapshot/transcript.py`)

Top-level `TranscriptSnapshot`, `schema_version = "1.0"`, `kind = "transcript"`:

| Field | Model | Key field |
| --- | --- | --- |
| `meeting` | `MeetingMeta` | — |
| `participants` | `Participant` | `key` (initials, or a slug of the name) |
| `agenda` | `AgendaItem` | `number` |
| `sections` | `TranscriptSection` | `id` (`"5.1"`, or `"s3"` when unnumbered) |
| `utterances` | `Utterance` | `index` |
| `actions` / `parked_items` | `ActionItem` / `ParkedItem` | `id` |
| `decisions` | `DecisionItem` | `id` |
| `requirements` | `RequirementSeed` | `id` |
| `findings` | `DiscoveryFinding` (RRAID seeds) | `id` |
| `candidate_objects` | `CandidateObject` (repeated business terms + counts) | `name` |
| `external_systems` | `ExternalSystem` (systems named in the room) | `name` |
| `statements` | `LabelledStatement` (verbatim, routed by category) | `id` |
| `stats` | `TranscriptStats` (coverage + quality) | — |
| `warnings` | `ParseWarning` (shared with the solution schema) | — |

The last three feed the pre-build design documents. `LabelledStatement`
categories come entirely from `transcript_cues.yaml::statement_groups`, so a
new design theme — anything from data residency to accessibility — is a YAML
change rather than a schema or code change.

Conventions:

- **Every extracted item carries an `Evidence`**: the verbatim sentence, the
  speaker, the section and the source line. Nothing in a transcript document
  asserts something the reader cannot check against the tape in seconds.
- **Canonical ordering is narrower here.** Participants, sections and
  utterances have a meaningful document order that is already deterministic,
  so `canonicalise_transcript` sorts only the warnings — re-sorting the rest
  would destroy information without buying determinism.
- Values that were never in the transcript stay `None` and render as `—`.
  Roles, sides and organisations are unknown for a raw Teams export, and the
  documents say so rather than inferring them.

## Transcript parsing (`src/docgen/transcripts/`)

Two stages, deliberately separate:

1. **`formats.py` — structure.** `detect_format` picks a profile
   (`structured`, `teams_txt`, `vtt`, `plain`) from the file's content, and the
   matching parser produces `RawTranscript`: turns, sections, attendees,
   agenda, `[ACTION:]`/`[PARKED:]` markers and end-of-document registers.
   Teams and VTT split a turn across many cues, so consecutive cues from one
   speaker are rejoined before anything downstream sees them. A line that
   matches no construct increments a counter that surfaces in the
   transcript-quality section — the transcript equivalent of "nothing silently
   dropped".
2. **`extract.py` — meaning-bearing items.** Sentence-level cue matching
   against `rules/transcript_cues.yaml` produces requirement seeds (with the
   priority word that was actually used), decisions, RRAID seeds and the
   category-labelled statements the design documents consume. Register rows and
   inline markers are matched to each other with rapidfuzz so an action keeps
   both its register ID/due date and the line where it was raised.

   Candidate business objects are a frequency count, not a parse: n-grams of
   1–3 words with no function word are counted across the session, and the ones
   above `min_mentions` are reported with their count and an example. The
   example is taken from the section where the term is used *most*, not where
   it first appears — a term's first mention is usually incidental ("my job
   today is to…") while its home section is where the business talks about the
   thing itself.

`__init__.py::parse_transcript` joins the two, resolves speaker labels onto
attendee-block people (exact → name → fuzzy, creating an entry for anyone who
speaks but was never listed), and computes coverage stats.

The split matters: adding a fifth transcript format is a `formats.py` change
only, and tuning extraction for a client is a YAML change only.

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

A transcript document is the same three steps against
`TranscriptDocRenderer`, `TRANSCRIPT_DOC_RENDERERS` and
`constants.ALL_TRANSCRIPT_DOC_KEYS`. The two registries are kept separate
rather than union-typed so a renderer can never be handed the wrong kind of
snapshot; `RenderContext` is shared, so diagrams, rules and the narrative
provider work identically on both sides.

### Word templates (`src/docgen/doc_templates.py`)

`resolve_template(key, title, cfg)` picks the docx template for a document:
`<templates_dir>/<name>.docx` where `<name>` is the document key, its title or
a listed alias (normalised, so case and `-`/`_`/space do not matter) → the
single `docx_template` from config → the plain template shipped in the
package. Renderers know nothing about it; `write_docx` receives the resolved
path plus a context dict of solution/meeting facts that a branded template may
reference as jinja placeholders.

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
fully replaces the shipped one. `transcript_cues.yaml` is loaded the same way,
so cue phrases are tunable per client without touching code.

A transcript has no separate hygiene stage: `TranscriptStats` plus the parse
warnings are rendered as the *Transcript quality and coverage* section of the
meeting notes, which is the same idea — state what the source could not tell
you, rather than papering over it.

## LLM tier (`src/docgen/llm/`)

`make_narrative_provider` wires the pipeline per request:
payload → redact (`redact.py`) → prompt (`prompts.py`, with the ground-truth
instruction) → API (`client.py`, key from env only, calls logged) →
validate (`validate.py`: every component-shaped token must exist in the
snapshot, rapidfuzz ≥ 90 for trivial drift) → one retry naming the violations
→ un-redact → prose. Every failure path returns `None`, which renders as a
placeholder: the LLM can improve a document but can never break a run or
invent a component.

`make_transcript_narrative_provider` is the same pipeline with a different
ground truth. Component names are not the risk in meeting documentation;
**attribution** is. `find_attribution_violations` extracts names in attribution
positions ("X said", "according to X", "X's view") and rejects any that no
participant matches, so the LLM cannot put words in the mouth of somebody who
was not in the room. Redaction runs on the same path and matters more here — a
transcript slice is people and commercial detail, not schema.

## Test strategy (`tests/`)

- `fixture_builder.py` constructs realistic solution zips programmatically
  (deterministic GUIDs + zip timestamps); committed fixtures are rebuilt
  byte-identically. Fixtures: `minimal`, `rich` (flows/plugins/roles/etc. plus
  deliberate warts for hygiene findings), `diff_v1`/`diff_v2` (every breaking
  heuristic).
- Transcript fixtures are committed **text** files
  (`tests/fixtures/transcripts/`), one per format profile, because the thing
  under test is the text layout itself.
- Golden snapshot tests byte-compare parser output
  (`pytest --update-goldens` regenerates after intentional changes).
- Two renderer matrices render **every registered doc × every fixture × both
  formats** offline, one per snapshot kind.
- The milestone gate tests run `docgen all --no-llm` end-to-end — for a
  solution and for a transcript — with socket access stubbed out, proving the
  offline tier needs no network.
- LLM tests are fully mocked, including the mandated "response naming a
  non-existent entity is rejected" case and its transcript counterpart,
  "response attributing a statement to somebody who was not in the meeting is
  rejected".
- Template tests build real `.docx` templates on the fly and assert that
  `HLD.docx` brands the HLD, does not leak into the LLD, and that a missing
  template falls back silently.
