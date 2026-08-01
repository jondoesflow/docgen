"""Ground-truth validation of LLM output against the snapshot.

Any component-shaped name in a response that does not exist in the snapshot
(exact match, or rapidfuzz >= 90 for minor casing/pluralisation drift) is a
violation: the response is rejected and retried, and on second failure the
renderer falls back to a placeholder. No invented capabilities, ever."""

from __future__ import annotations

import re

from rapidfuzz import fuzz, process

from docgen.snapshot.models import Snapshot

# prefixed logical names, e.g. abc_project, new_myfield (publisher prefix idiom)
_LOGICAL_NAME = re.compile(r"\b[a-z][a-z0-9]{1,11}_[a-z0-9_]+\b")
_BACKTICKED = re.compile(r"`([^`]{2,80})`")

_ACCEPT_SCORE = 90


def collect_component_names(snapshot: Snapshot) -> set[str]:
    names: set[str] = set()

    def add(*values: str | None) -> None:
        for value in values:
            if value:
                names.add(value.lower())

    add(snapshot.solution.unique_name, snapshot.solution.display_name,
        snapshot.solution.publisher.unique_name, snapshot.solution.publisher.display_name)
    for entity in snapshot.entities:
        add(entity.logical_name, entity.display_name, entity.display_collection_name,
            entity.primary_name_attribute)
        for att in entity.attributes:
            add(att.logical_name, att.display_name, att.schema_name, att.option_set_name,
                *att.lookup_targets)
            if att.local_option_set:
                add(att.local_option_set.name)
        for rel in entity.relationships:
            add(rel.schema_name, rel.referenced_entity, rel.referencing_entity, rel.referencing_attribute)
        for form in entity.forms:
            add(form.name)
        for view in entity.views:
            add(view.name, *view.columns)
        for rule in entity.business_rules:
            add(rule.name)
    for option_set in snapshot.global_option_sets:
        add(option_set.name, option_set.display_name)
    for role in snapshot.security_roles:
        add(role.name)
        for priv in role.privileges:
            add(priv.name)
    for profile in snapshot.field_security_profiles:
        add(profile.name)
    for flow in snapshot.cloud_flows:
        add(flow.unique_name, flow.display_name, *flow.connectors_used, *flow.connection_reference_names)
        if flow.trigger:
            add(flow.trigger.name, flow.trigger.connector)
        for action in flow.actions:
            add(action.name, action.connector, action.operation_id)
    for ref in snapshot.connection_references:
        add(ref.logical_name, ref.display_name, ref.api_name)
    for variable in snapshot.environment_variables:
        add(variable.schema_name, variable.display_name)
    for assembly in snapshot.plugin_assemblies:
        add(assembly.name)
    for step in snapshot.plugin_steps:
        add(step.name, step.plugin_type_name, step.assembly_name, step.primary_entity)
    for resource in snapshot.web_resources:
        add(resource.name, resource.display_name)
    for connector in snapshot.custom_connectors:
        add(connector.name, connector.display_name)
    for app in snapshot.canvas_apps:
        add(app.name, app.display_name)
    for component in snapshot.other_components:
        add(component.schema_name_or_id)
    return names


def extract_candidates(text: str) -> set[str]:
    """Component-shaped tokens: prefixed logical names + backticked identifiers."""
    candidates = {m.group(0) for m in _LOGICAL_NAME.finditer(text)}
    for m in _BACKTICKED.finditer(text):
        token = m.group(1).strip()
        # only identifier-ish backticked tokens, not prose or code fragments
        if token and " " not in token and len(token) <= 60:
            candidates.add(token)
    return candidates


def find_violations(text: str, names: set[str]) -> list[str]:
    violations = []
    for candidate in sorted(extract_candidates(text)):
        lowered = candidate.lower()
        if lowered in names:
            continue
        best = process.extractOne(lowered, names, scorer=fuzz.ratio)
        if best is None or best[1] < _ACCEPT_SCORE:
            violations.append(candidate)
    return violations
