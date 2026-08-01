"""Hygiene checks and licensing detection.

Every Finding states its metadata evidence, so the hygiene report and the
RRAID seeds it feeds are always traceable to the snapshot (ground truth only).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from docgen.snapshot.models import Snapshot

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Finding:
    rule_id: str
    severity: str  # error | warning | info
    category: str  # descriptions | unmanaged | flows | option_sets | naming | deprecation | references
    component: str  # human-readable component reference
    message: str
    evidence: str  # the metadata fact this finding is based on


@dataclass
class LicensingHit:
    connector: str
    label: str
    used_by: list[str]
    note: str


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_descriptions(snapshot: Snapshot) -> list[Finding]:
    findings = []
    for entity in snapshot.entities:
        if entity.is_custom and not entity.description:
            findings.append(Finding(
                "DESC-001", "warning", "descriptions", f"table {entity.logical_name}",
                "Custom table has no description.",
                f"entities[{entity.logical_name}].description is empty",
            ))
        for att in entity.attributes:
            if att.is_custom and not att.description:
                findings.append(Finding(
                    "DESC-002", "warning", "descriptions",
                    f"column {entity.logical_name}.{att.logical_name}",
                    "Custom column has no description.",
                    f"entities[{entity.logical_name}].attributes[{att.logical_name}].description is empty",
                ))
    return findings


def check_unmanaged(snapshot: Snapshot) -> list[Finding]:
    if snapshot.solution.managed:
        return []
    return [Finding(
        "MGMT-001", "info", "unmanaged", f"solution {snapshot.solution.unique_name}",
        "Solution exported as unmanaged. Deploying unmanaged solutions to downstream "
        "environments creates unmanaged layers that cannot be cleanly removed.",
        "solution.managed = false",
    )]


def check_flow_error_handling(snapshot: Snapshot) -> list[Finding]:
    findings = []
    for flow in snapshot.cloud_flows:
        if flow.actions and not flow.has_error_scope:
            findings.append(Finding(
                "FLOW-001", "warning", "flows", f"flow {flow.display_name or flow.unique_name}",
                "Flow has no error-handling path (no action runs after Failed/TimedOut).",
                f"cloud_flows[{flow.unique_name}].has_error_scope = false over {len(flow.actions)} action(s)",
            ))
    return findings


def check_unused_option_sets(snapshot: Snapshot) -> list[Finding]:
    referenced = {a.option_set_name for e in snapshot.entities for a in e.attributes if a.option_set_name}
    findings = []
    for option_set in snapshot.global_option_sets:
        if option_set.name not in referenced:
            findings.append(Finding(
                "OPT-001", "warning", "option_sets", f"global choice set {option_set.name}",
                "Global choice set is not referenced by any column in this solution.",
                f"no attribute has option_set_name = {option_set.name!r}",
            ))
    return findings


def check_naming(snapshot: Snapshot, naming_rules: dict) -> list[Finding]:
    findings = []
    rules = naming_rules.get("rules") or []

    def targets(rule: dict):
        target = rule.get("target")
        custom_only = rule.get("applies_to") == "custom_only"
        if target == "entity":
            for e in snapshot.entities:
                if not custom_only or e.is_custom:
                    yield f"table {e.logical_name}", e.logical_name
        elif target == "attribute":
            for e in snapshot.entities:
                for a in e.attributes:
                    if not custom_only or a.is_custom:
                        yield f"column {e.logical_name}.{a.logical_name}", a.logical_name
        elif target == "flow":
            for f in snapshot.cloud_flows:
                yield f"flow {f.display_name or f.unique_name}", f.display_name or f.unique_name
        elif target == "environment_variable":
            for v in snapshot.environment_variables:
                yield f"environment variable {v.schema_name}", v.schema_name
        elif target == "web_resource":
            for w in snapshot.web_resources:
                yield f"web resource {w.name}", w.name
        elif target == "connection_reference":
            for c in snapshot.connection_references:
                yield f"connection reference {c.logical_name}", c.logical_name

    for rule in rules:
        pattern = rule.get("pattern")
        if not pattern:
            continue
        try:
            compiled = re.compile(pattern)
        except re.error:
            continue
        for component, value in targets(rule):
            if not compiled.fullmatch(value):
                findings.append(Finding(
                    rule.get("id", "NAME-?"), rule.get("severity", "warning"), "naming", component,
                    rule.get("message", f"Name does not match {pattern}"),
                    f"{value!r} does not match /{pattern}/",
                ))
    return findings


def check_deprecations(snapshot: Snapshot, deprecation_rules: dict) -> list[Finding]:
    findings = []
    rules = deprecation_rules.get("deprecations") or []

    connector_usage: dict[str, list[str]] = {}
    for flow in snapshot.cloud_flows:
        for connector in flow.connectors_used:
            connector_usage.setdefault(connector, []).append(f"flow {flow.display_name or flow.unique_name}")
    for ref in snapshot.connection_references:
        if ref.api_name:
            connector_usage.setdefault(ref.api_name, []).append(f"connection reference {ref.logical_name}")
    for app in snapshot.canvas_apps:
        for connector in app.connections:
            connector_usage.setdefault(connector, []).append(f"canvas app {app.name}")

    for rule in rules:
        match = rule.get("match") or {}
        kind, value = match.get("kind"), str(match.get("value", "")).lower()
        rule_id = rule.get("id", "DEP-?")
        title = rule.get("title", "Deprecated feature in use")
        guidance = rule.get("guidance", "")
        if kind == "connector":
            for user in connector_usage.get(value, []):
                findings.append(Finding(
                    rule_id, "warning", "deprecation", user,
                    f"{title}. {guidance}".strip(),
                    f"uses connector {value}",
                ))
        elif kind == "plugin_isolation":
            for assembly in snapshot.plugin_assemblies:
                if (assembly.isolation_mode or "").lower() == value:
                    findings.append(Finding(
                        rule_id, "warning", "deprecation", f"plugin assembly {assembly.name}",
                        f"{title}. {guidance}".strip(),
                        f"plugin_assemblies[{assembly.name}].isolation_mode = {assembly.isolation_mode!r}",
                    ))
        elif kind == "web_resource_type":
            for resource in snapshot.web_resources:
                if (resource.type or "").lower() == value:
                    findings.append(Finding(
                        rule_id, "warning", "deprecation", f"web resource {resource.name}",
                        f"{title}. {guidance}".strip(),
                        f"web_resources[{resource.name}].type = {resource.type!r}",
                    ))
    return findings


def check_dangling_references(snapshot: Snapshot) -> list[Finding]:
    findings = []
    known_refs = {c.logical_name for c in snapshot.connection_references}
    for flow in snapshot.cloud_flows:
        for logical in flow.connection_reference_names:
            if logical not in known_refs:
                findings.append(Finding(
                    "REF-001", "warning", "references",
                    f"flow {flow.display_name or flow.unique_name}",
                    f"Flow uses connection reference {logical!r} which is not in this solution — "
                    "a missing dependency unless it exists in the target environment.",
                    f"cloud_flows[{flow.unique_name}].connection_reference_names includes {logical!r}",
                ))
    known_assemblies = {a.name for a in snapshot.plugin_assemblies}
    for step in snapshot.plugin_steps:
        if step.assembly_name and step.assembly_name not in known_assemblies:
            findings.append(Finding(
                "REF-002", "warning", "references", f"plugin step {step.name}",
                f"Step references assembly {step.assembly_name!r} which is not in this solution.",
                f"plugin_steps[{step.name}].assembly_name = {step.assembly_name!r}",
            ))
    return findings


def run_all_checks(snapshot: Snapshot, rules: dict[str, dict]) -> list[Finding]:
    findings: list[Finding] = []
    findings += check_descriptions(snapshot)
    findings += check_unmanaged(snapshot)
    findings += check_flow_error_handling(snapshot)
    findings += check_unused_option_sets(snapshot)
    findings += check_naming(snapshot, rules.get("naming", {}))
    findings += check_deprecations(snapshot, rules.get("deprecations", {}))
    findings += check_dangling_references(snapshot)
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.rule_id, f.component))
    return findings


# ---------------------------------------------------------------------------
# Licensing detection
# ---------------------------------------------------------------------------


def detect_licensing(snapshot: Snapshot, licensing_rules: dict) -> tuple[list[LicensingHit], list[str]]:
    """(premium connector hits, other premium signals) from rules/licensing.yaml."""
    premium = {p["api_name"]: p for p in licensing_rules.get("premium_connectors", []) if p.get("api_name")}

    usage: dict[str, list[str]] = {}
    for flow in snapshot.cloud_flows:
        for connector in flow.connectors_used:
            usage.setdefault(connector, []).append(f"flow: {flow.display_name or flow.unique_name}")
    for ref in snapshot.connection_references:
        if ref.api_name:
            usage.setdefault(ref.api_name, []).append(f"connection reference: {ref.logical_name}")
    for app in snapshot.canvas_apps:
        for connector in app.connections:
            usage.setdefault(connector, []).append(f"canvas app: {app.display_name or app.name}")

    hits = []
    for api_name in sorted(usage):
        rule = premium.get(api_name)
        if rule:
            hits.append(LicensingHit(
                connector=api_name,
                label=rule.get("label", api_name),
                used_by=sorted(set(usage[api_name])),
                note=rule.get("note", ""),
            ))

    signals = []
    signal_rules = {s.get("kind"): s for s in licensing_rules.get("signals", [])}
    if snapshot.custom_connectors and "custom_connector" in signal_rules:
        names = ", ".join(c.display_name or c.name for c in snapshot.custom_connectors)
        signals.append(f"{signal_rules['custom_connector'].get('note', 'Custom connectors are premium.')} "
                       f"Detected: {names}.")
    return hits, signals
