# Word templates

Drop a branded `.docx` in here named after the document it should style, and
docgen pours that document into it — styles, headers, footers and all. A
document with no template here falls back to `docx_template` in `docgen.yaml`,
and then to the plain template shipped inside the package. Nothing is
required: an empty folder means the behaviour is exactly as it was.

Change the folder with `templates_dir:` in `docgen.yaml`.

A template covers a document for its **whole life**. `HLD.docx` styles the
High-Level Design drafted from a discovery workshop *and* the one regenerated
from the solution export after build — same document key, same house style,
before and after.

## Naming

Names are matched **case-insensitively**, and `-`, `_` and spaces are treated
alike — `HLD.docx`, `hld.docx` and `High-Level Design.docx` are the same file
as far as docgen is concerned.

| Document | Name the file (any of) |
| --- | --- |
| High-Level Design | `HLD`, `hld`, `High-Level Design`, `High Level Design` |
| Low-Level Design | `LLD`, `lld`, `Low-Level Design`, `Low Level Design` |
| Data Dictionary | `data-dictionary`, `DD`, `Data Dictionary` |
| Security & Access Model | `security`, `Security Model`, `Security & Access Model` |
| Deployment Configuration Register | `deployment`, `Deployment Register`, `Deployment Configuration Register` |
| Licensing Impact Summary | `licensing`, `Licensing Impact Summary` |
| Solution / Discovery Hygiene Report | `hygiene`, `Hygiene Report`, `Solution Hygiene Report` |
| Integration Design | `integration`, `Integration Design` |
| RRAID Log | `rraid`, `RRAID`, `RRAID Log` |
| Release Notes | `release-notes`, `Release Notes` |
| Meeting Notes | `meeting-notes`, `Meeting Notes`, `Minutes`, `Meeting Minutes` |
| Requirements Catalogue | `requirements`, `Requirements Catalogue` |
| Actions & Decisions Register | `actions`, `Action Log`, `Actions & Decisions Register` |

The first eleven rows apply to both the pre-build and the as-built version of
that document; the last three exist only for meeting transcripts.

The console names the template used for each document, so a line without a
`[template …]` suffix did not match anything here.

## What a template needs

Start from any branded Word document and add two jinja placeholders, typically
on the cover page:

- `{{ title }}` — the document title
- `{{ subtitle }}` — solution or meeting identity plus the generation note

The generated body is appended after the template's own content using the
template's styles, so restyling `Title`, `Subtitle`, `Heading 1`–`Heading 4`,
`List Bullet` and `Table Grid` restyles the whole document.

Optionally available anywhere in the template (empty when not applicable):

- **any document** — `{{ doc_key }}`, `{{ doc_title }}`, `{{ source_file }}`,
  `{{ generated_at }}`, `{{ docgen_version }}`
- **solution documents** — `{{ solution_name }}`, `{{ solution_unique_name }}`,
  `{{ version }}`, `{{ managed }}`, `{{ publisher }}`
- **transcript documents** — `{{ meeting_title }}`, `{{ client }}`,
  `{{ consultancy }}`, `{{ meeting_date }}`, `{{ meeting_time }}`,
  `{{ location }}`, `{{ facilitator }}`

See [docs/USAGE.md](../docs/USAGE.md#branded-docx-templates) for the full
reference.
