# docgen

Living design documentation for Dynamics 365 CE / Power Platform solutions.

`docgen` parses an exported solution zip into a canonical JSON snapshot, then
renders a full consultancy documentation set (HLD, LLD, data dictionary,
security model, deployment register, licensing summary, hygiene report,
integration design, RRAID) — regenerated from metadata, so it never drifts.
Feeding it two snapshots produces release notes.

> **Status: under construction.** This README is completed in the final
> documentation milestone.

## Quickstart (preview)

```bash
pip install .
docgen all MySolution.zip -o out/ --no-llm
```

Fully offline by default with `--no-llm`; the optional LLM tier
(`ANTHROPIC_API_KEY`) only adds narrative prose.
