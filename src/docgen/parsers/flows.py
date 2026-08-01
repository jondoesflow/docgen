"""Workflows block: cloud flows (category 5, clientdata JSON) and business rules
(category 2). Other workflow categories stay unclaimed and surface via the
generic root-component fallback."""

from __future__ import annotations

import json

from lxml import etree

from docgen.parsers.base import ParseContext, text, to_int
from docgen.snapshot.models import BusinessRule, CloudFlow, FlowAction, FlowTrigger

TYPE_WORKFLOW = 29

_STATE_CODES = {0: "Draft", 1: "Activated"}
_BR_SCOPES = {1: "Entity", 2: "All Forms", 3: "Specific Forms"}
ERROR_STATUSES = {"failed", "timedout"}


def _connector_of(node: dict) -> tuple[str | None, str | None]:
    """(connector api name, operationId) from an action/trigger inputs.host block."""
    host = (node.get("inputs") or {}).get("host") or {}
    connector = host.get("connectionName")
    api_id = host.get("apiId") or ""
    if connector is None and api_id:
        connector = api_id.rstrip("/").rsplit("/", 1)[-1]
    return connector, host.get("operationId")


def _walk_actions(actions: dict, prefix: str = "") -> list[FlowAction]:
    result: list[FlowAction] = []
    if not isinstance(actions, dict):
        return result
    for name in sorted(actions):
        node = actions[name]
        if not isinstance(node, dict):
            continue
        path = f"{prefix}{name}"
        connector, operation_id = _connector_of(node)
        run_after = node.get("runAfter") or {}
        statuses = sorted({s for deps in run_after.values() if isinstance(deps, list) for s in deps})
        result.append(FlowAction(
            path=path,
            name=name,
            type=node.get("type", ""),
            connector=connector,
            operation_id=operation_id,
            run_after_statuses=statuses,
        ))
        for child_key in ("actions",):
            result.extend(_walk_actions(node.get(child_key) or {}, f"{path}/"))
        else_block = node.get("else") or {}
        result.extend(_walk_actions(else_block.get("actions") or {}, f"{path}/else/"))
        for case_name, case in sorted((node.get("cases") or {}).items()):
            if isinstance(case, dict):
                result.extend(_walk_actions(case.get("actions") or {}, f"{path}/{case_name}/"))
    return result


def _parse_clientdata(ctx: ParseContext, flow: CloudFlow, raw: bytes, context: str) -> CloudFlow:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        ctx.warn("invalid_flow_json", context, str(exc))
        return flow

    properties = data.get("properties") or {}
    definition = properties.get("definition") or {}

    trigger = None
    triggers = definition.get("triggers") or {}
    for name in sorted(triggers):
        node = triggers[name]
        if not isinstance(node, dict):
            continue
        connector, operation_id = _connector_of(node)
        trigger = FlowTrigger(name=name, type=node.get("type", ""), kind=operation_id, connector=connector)
        break
    if len(triggers) > 1:
        ctx.warn("unparsed_element", context, f"flow has {len(triggers)} triggers; only the first is recorded")

    actions = _walk_actions(definition.get("actions") or {})

    connection_refs = []
    connectors = set()
    for api_name, binding in (properties.get("connectionReferences") or {}).items():
        connectors.add(api_name)
        if isinstance(binding, dict):
            logical = ((binding.get("connection") or {}).get("connectionReferenceLogicalName"))
            if logical:
                connection_refs.append(logical)
    if trigger and trigger.connector:
        connectors.add(trigger.connector)
    connectors.update(a.connector for a in actions if a.connector)

    has_error_scope = any(ERROR_STATUSES & {s.lower() for s in a.run_after_statuses} for a in actions)

    return flow.model_copy(update={
        "trigger": trigger,
        "actions": actions,
        "connectors_used": sorted(connectors),
        "connection_reference_names": sorted(set(connection_refs)),
        "has_error_scope": has_error_scope,
    })


def parse_workflows(
    ctx: ParseContext, block: etree._Element | None
) -> tuple[list[CloudFlow], dict[str, list[BusinessRule]]]:
    """Returns (cloud flows, business rules keyed by primary entity logical name)."""
    flows: list[CloudFlow] = []
    business_rules: dict[str, list[BusinessRule]] = {}
    if block is None:
        return flows, business_rules

    for wf in block.findall("Workflow"):
        name = wf.get("Name") or "(unnamed workflow)"
        workflow_id = (wf.get("WorkflowId") or "").strip("{}").lower()
        try:
            category = to_int(text(wf, "Category"))
            state = _STATE_CODES.get(to_int(text(wf, "StateCode")), text(wf, "StateCode"))
            if category == 5:
                flow = CloudFlow(
                    unique_name=workflow_id or name,
                    display_name=name,
                    description=text(wf, "Description"),
                    state=state,
                )
                json_name = (text(wf, "JsonFileName") or "").lstrip("/")
                if json_name:
                    raw = ctx.read_bytes(json_name)
                    if raw is None:
                        ctx.warn("missing_flow_json", f"customizations.xml/Workflows/{name}",
                                 f"clientdata file {json_name!r} not found in zip; "
                                 "flow recorded with metadata only")
                    else:
                        flow = _parse_clientdata(ctx, flow, raw, f"{json_name}")
                else:
                    ctx.warn("missing_flow_json", f"customizations.xml/Workflows/{name}",
                             "cloud flow has no JsonFileName")
                flows.append(flow)
                if workflow_id:
                    ctx.claim(TYPE_WORKFLOW, workflow_id)
            elif category == 2:
                scope = _BR_SCOPES.get(to_int(text(wf, "Scope")), text(wf, "Scope"))
                primary = (text(wf, "PrimaryEntity") or "").lower()
                rule = BusinessRule(name=name, scope=scope, state=state, primary_entity=primary or None)
                business_rules.setdefault(primary, []).append(rule)
                if workflow_id:
                    ctx.claim(TYPE_WORKFLOW, workflow_id)
            # other categories (classic workflows, actions, BPFs) are left for the
            # generic root-component fallback so they stay visible
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/Workflows/{name}", str(exc))
    return flows, business_rules
