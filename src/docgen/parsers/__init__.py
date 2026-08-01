"""Zip → Snapshot orchestrator.

`parse_solution` is the only public entry point. It reads solution.xml and
customizations.xml, dispatches each top-level customizations family to its
specialised parser, and funnels everything unrecognised into GenericComponent
entries plus parse warnings — nothing is silently dropped.
"""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path

from docgen import __version__
from docgen.parsers import apps as apps_mod
from docgen.parsers import connections as connections_mod
from docgen.parsers import entities as entities_mod
from docgen.parsers import flows as flows_mod
from docgen.parsers import generic, manifest, optionsets
from docgen.parsers import plugins as plugins_mod
from docgen.parsers import security as security_mod
from docgen.parsers import webresources as webresources_mod
from docgen.parsers.base import ParseContext
from docgen.snapshot.models import Snapshot

# customizations.xml top-level families with a specialised parser.
_HANDLED_FAMILIES = {
    "Entities",
    "EntityRelationships",
    "Relationships",  # tolerated alias seen in some exports
    "optionsets",
    "Roles",
    "FieldSecurityProfiles",
    "Workflows",
    "connectionreferences",
    "EnvironmentVariables",
    "PluginAssemblies",
    "SdkMessageProcessingSteps",
    "WebResources",
    "CanvasApps",
    "Connectors",
}

# Structural / metadata-only families that carry no solution components.
_IGNORED_FAMILIES = {"Languages", "EntityMaps", "EntityDataProviders", "OrganizationSettings"}


def parse_solution(zip_path: Path) -> Snapshot:
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        ctx = ParseContext(zf, zip_path.name)
        meta, root_components = manifest.parse_manifest(ctx)

        entity_list = []
        global_sets = []
        roles = []
        profiles = []
        cloud_flows = []
        connection_refs = []
        env_vars = []
        assemblies = []
        steps = []
        web_resources = []
        canvas_apps = []
        custom_connectors = []

        cust = ctx.read_xml("customizations.xml")
        if cust is None:
            ctx.warn("missing_file", "customizations.xml", "customizations.xml not found or unreadable in zip")
        else:
            entity_list = entities_mod.parse_entities(ctx, cust.find("Entities"))

            rel_block = cust.find("EntityRelationships")
            if rel_block is None:
                rel_block = cust.find("Relationships")
            rels = entities_mod.parse_relationships(ctx, rel_block)
            entities_mod.attach_relationships(ctx, entity_list, rels)

            global_sets = optionsets.parse_global_optionsets(ctx, cust.find("optionsets"))
            roles = security_mod.parse_roles(ctx, cust.find("Roles"))
            profiles = security_mod.parse_field_security_profiles(ctx, cust.find("FieldSecurityProfiles"))

            cloud_flows, business_rules = flows_mod.parse_workflows(ctx, cust.find("Workflows"))
            by_name = {e.logical_name: e for e in entity_list}
            for entity_name, rules in business_rules.items():
                owner = by_name.get(entity_name)
                if owner is None:
                    for rule in rules:
                        ctx.warn("business_rule_unattached", f"customizations.xml/Workflows/{rule.name}",
                                 f"primary entity {entity_name!r} is not in this solution")
                    continue
                owner.business_rules.extend(rules)

            connection_refs = connections_mod.parse_connection_references(ctx, cust.find("connectionreferences"))
            env_vars = connections_mod.parse_environment_variables(ctx, cust.find("EnvironmentVariables"))
            assemblies = plugins_mod.parse_plugin_assemblies(ctx, cust.find("PluginAssemblies"))
            steps = plugins_mod.parse_plugin_steps(ctx, cust.find("SdkMessageProcessingSteps"))
            web_resources = webresources_mod.parse_web_resources(ctx, cust.find("WebResources"))
            canvas_apps = apps_mod.parse_canvas_apps(ctx, cust.find("CanvasApps"))
            custom_connectors = apps_mod.parse_custom_connectors(ctx, cust.find("Connectors"))

            for child in cust:
                tag = str(child.tag)
                if tag in _HANDLED_FAMILIES or tag in _IGNORED_FAMILIES:
                    continue
                ctx.warn(
                    "unparsed_element",
                    f"customizations.xml/{tag}",
                    f"No parser for customizations family <{tag}>; its components appear "
                    "in the generic inventory if they are solution root components.",
                )

        other = generic.collect_unclaimed(ctx, root_components)

        return Snapshot(
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            docgen_version=__version__,
            source_file=zip_path.name,
            solution=meta,
            entities=entity_list,
            global_option_sets=global_sets,
            security_roles=roles,
            field_security_profiles=profiles,
            cloud_flows=cloud_flows,
            connection_references=connection_refs,
            environment_variables=env_vars,
            plugin_assemblies=assemblies,
            plugin_steps=steps,
            web_resources=web_resources,
            canvas_apps=canvas_apps,
            custom_connectors=custom_connectors,
            other_components=other,
            warnings=ctx.warnings,
        )
