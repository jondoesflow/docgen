"""RRAID (Risks, Assumptions, Issues, Dependencies) — seeded deterministically
from detection rules over the snapshot, each seed stating its metadata
evidence. Human-judgement sections are structured and left for the consultant.
The optional LLM tier only rephrases seed summaries; seeds always exist."""

from __future__ import annotations

from docgen.hygiene.checks import Finding, detect_licensing, run_all_checks
from docgen.renderers.base import DocRenderer, RenderContext
from docgen.renderers.docmodel import Callout, Document, Paragraph, Placeholder, Section, Table
from docgen.snapshot.models import Snapshot


class RraidRenderer(DocRenderer):
    key = "rraid"
    title = "RRAID Log"

    def _seed_summary(self, ctx: RenderContext, finding: Finding) -> str:
        prose = ctx.narrative_provider("rraid_seed", {
            "component": finding.component,
            "message": finding.message,
            "evidence": finding.evidence,
        })
        return prose or finding.message

    def build(self, snapshot: Snapshot, ctx: RenderContext) -> Document:
        doc = Document(title=f"{self.title} — {snapshot.solution.display_name or snapshot.solution.unique_name}",
                       subtitle=self.subtitle(snapshot))
        findings = run_all_checks(snapshot, ctx.rules)
        licensing_hits, licensing_signals = detect_licensing(snapshot, ctx.rules.get("licensing", {}))

        doc.add(Section("How to read this log").add(Paragraph(
            "Entries marked 'seeded' were detected automatically from solution metadata and state their "
            "evidence; they need an owner, impact assessment and mitigation. Empty sections are for "
            "risks, assumptions, issues and dependencies that require human judgement — metadata cannot "
            "see contractual, organisational or timeline factors."
        )))

        # ---------------- Risks ----------------
        risk_rows: list[list[str]] = []
        risk_id = 0

        def add_risk(summary: str, evidence: str) -> None:
            nonlocal risk_id
            risk_id += 1
            risk_rows.append([f"R-{risk_id:03d}", summary, evidence, "[Consultant]", "[Consultant]"])

        for finding in findings:
            if finding.category == "deprecation":
                add_risk(f"{finding.component}: {self._seed_summary(ctx, finding)}", finding.evidence)
        for hit in licensing_hits:
            add_risk(
                f"Premium connector {hit.label} ({hit.connector}) in use — licensing exposure. {hit.note}",
                "used by " + "; ".join(hit.used_by),
            )
        for signal in licensing_signals:
            add_risk(f"Licensing exposure: {signal}", "custom_connectors present in snapshot")
        for finding in findings:
            if finding.rule_id == "FLOW-001":
                add_risk(f"{finding.component}: {self._seed_summary(ctx, finding)}", finding.evidence)
        for finding in findings:
            if finding.rule_id == "MGMT-001":
                add_risk(self._seed_summary(ctx, finding), finding.evidence)

        risks = Section("Risks")
        if risk_rows:
            risks.add(Callout("risk", f"{len(risk_rows)} risk(s) seeded from solution metadata."))
            risks.add(Table(headers=["ID", "Risk (seeded)", "Metadata evidence", "Impact", "Mitigation"],
                            rows=risk_rows))
        else:
            risks.add(Paragraph("No risks seeded from metadata."))
        risks.add(Section("Additional risks (human judgement)").add(Placeholder(
            hint="Delivery, contractual, adoption, data-quality and timeline risks the metadata cannot see.")))
        doc.add(risks)

        # ---------------- Assumptions ----------------
        doc.add(Section("Assumptions").add(
            Table(headers=["ID", "Assumption", "Owner", "Validated?"], rows=[["A-001", "", "", ""]]),
            Placeholder(hint="Record the assumptions this design rests on: environment strategy, licensing "
                             "entitlements, data volumes, integration availability, go-live dates."),
        ))

        # ---------------- Issues ----------------
        issue_rows = []
        for i, finding in enumerate((f for f in findings if f.severity == "error"), start=1):
            issue_rows.append([f"I-{i:03d}", f"{finding.component}: {finding.message}", finding.evidence, ""])
        issues = Section("Issues")
        if issue_rows:
            issues.add(Table(headers=["ID", "Issue (seeded)", "Metadata evidence", "Resolution"], rows=issue_rows))
        else:
            issues.add(Paragraph("No issues seeded from metadata."))
        issues.add(Section("Open issues (human judgement)").add(Placeholder(
            hint="Live delivery issues: blocked work, unresolved decisions, defects under discussion.")))
        doc.add(issues)

        # ---------------- Dependencies ----------------
        dep_rows: list[list[str]] = []
        dep_id = 0

        def add_dep(summary: str, evidence: str) -> None:
            nonlocal dep_id
            dep_id += 1
            dep_rows.append([f"D-{dep_id:03d}", summary, evidence, "[Consultant]"])

        for finding in findings:
            if finding.category == "references":
                add_dep(f"{finding.component}: {self._seed_summary(ctx, finding)}", finding.evidence)
        for ref in snapshot.connection_references:
            add_dep(
                f"Connection reference {ref.display_name or ref.logical_name} ({ref.api_name}) must be "
                "bound to a connection in each target environment.",
                f"connection_references[{ref.logical_name}]",
            )
        for variable in snapshot.environment_variables:
            if variable.current_value is None and variable.default_value is None:
                add_dep(
                    f"Environment variable {variable.schema_name} has no value or default — a per-environment "
                    "value is required.",
                    f"environment_variables[{variable.schema_name}]",
                )
            if variable.is_secret:
                add_dep(
                    f"Secret environment variable {variable.schema_name} depends on a Key Vault / secret "
                    "store being configured per environment.",
                    f"environment_variables[{variable.schema_name}].is_secret = true",
                )

        deps = Section("Dependencies")
        if dep_rows:
            deps.add(Table(headers=["ID", "Dependency (seeded)", "Metadata evidence", "Owner"], rows=dep_rows))
        else:
            deps.add(Paragraph("No dependencies seeded from metadata."))
        deps.add(Section("External dependencies (human judgement)").add(Placeholder(
            hint="Third parties, other workstreams, environment provisioning, data migration cutover windows.")))
        doc.add(deps)
        return doc
