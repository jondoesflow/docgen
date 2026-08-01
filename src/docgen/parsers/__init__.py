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
from docgen.parsers import entities as entities_mod
from docgen.parsers import generic, manifest, optionsets
from docgen.parsers.base import ParseContext
from docgen.snapshot.models import Snapshot

# customizations.xml top-level families with a specialised parser. Parsers for
# families marked None land in later milestones; until then those families are
# reported as unparsed (warning) so their presence is never invisible.
_HANDLED_FAMILIES = {
    "Entities",
    "EntityRelationships",
    "Relationships",  # tolerated alias seen in some exports
    "optionsets",
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
            other_components=other,
            warnings=ctx.warnings,
        )
