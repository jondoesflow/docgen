"""Plugin assemblies and SDK message processing steps."""

from __future__ import annotations

from lxml import etree

from docgen.parsers.base import ParseContext, text, to_int
from docgen.snapshot.models import PluginAssembly, PluginStep

TYPE_PLUGIN_ASSEMBLY = 91
TYPE_PLUGIN_STEP = 92

_ISOLATION = {1: "none", 2: "sandbox"}
_STAGES = {10: "pre_validation", 20: "pre_operation", 40: "post_operation"}
_MODES = {0: "sync", 1: "async"}
_STEP_STATES = {0: "Enabled", 1: "Disabled"}


def _parse_full_name(full_name: str) -> dict:
    """'Abc.Plugins, Version=1.0.0.0, Culture=neutral, PublicKeyToken=...' → parts."""
    parts = [p.strip() for p in full_name.split(",")]
    result = {"name": parts[0] if parts else full_name}
    for part in parts[1:]:
        if "=" in part:
            key, _, value = part.partition("=")
            result[key.strip().lower()] = value.strip()
    return result


def parse_plugin_assemblies(ctx: ParseContext, block: etree._Element | None) -> list[PluginAssembly]:
    assemblies: list[PluginAssembly] = []
    if block is None:
        return assemblies
    for el in block.findall("PluginAssembly"):
        full_name = el.get("FullName") or el.get("Name") or ""
        if not full_name:
            ctx.warn("unparsed_element", "customizations.xml/PluginAssemblies",
                     "PluginAssembly without a FullName")
            continue
        try:
            parts = _parse_full_name(full_name)
            isolation_code = to_int(text(el, "IsolationMode"))
            assemblies.append(PluginAssembly(
                name=parts["name"],
                version=parts.get("version") or text(el, "Version"),
                isolation_mode=_ISOLATION.get(isolation_code,
                                              str(isolation_code) if isolation_code is not None else None),
                culture=parts.get("culture"),
                public_key_token=parts.get("publickeytoken"),
            ))
            ctx.claim(TYPE_PLUGIN_ASSEMBLY, parts["name"])
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/PluginAssemblies/{full_name}", str(exc))
    return assemblies


def parse_plugin_steps(ctx: ParseContext, block: etree._Element | None) -> list[PluginStep]:
    steps: list[PluginStep] = []
    if block is None:
        return steps
    for el in block.findall("SdkMessageProcessingStep"):
        name = el.get("Name") or text(el, "Name") or "(unnamed step)"
        try:
            stage_code = to_int(text(el, "Stage"))
            mode_code = to_int(text(el, "Mode"))
            state_code = to_int(text(el, "StateCode"))
            filtering = text(el, "FilteringAttributes") or ""
            step_id = (el.get("SdkMessageProcessingStepId") or "").strip("{}").lower()
            steps.append(PluginStep(
                name=name,
                message=text(el, "SdkMessage") or text(el, "MessageName"),
                primary_entity=(text(el, "PrimaryEntity") or "").lower() or None,
                stage=_STAGES.get(stage_code, str(stage_code) if stage_code is not None else None),
                mode=_MODES.get(mode_code, str(mode_code) if mode_code is not None else None),
                rank=to_int(text(el, "Rank")),
                filtering_attributes=sorted(a.strip() for a in filtering.split(",") if a.strip()),
                assembly_name=text(el, "PluginAssemblyName"),
                plugin_type_name=text(el, "PluginTypeName"),
                state=_STEP_STATES.get(state_code, str(state_code) if state_code is not None else None),
            ))
            if step_id:
                ctx.claim(TYPE_PLUGIN_STEP, step_id)
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/SdkMessageProcessingSteps/{name}", str(exc))
    return steps
