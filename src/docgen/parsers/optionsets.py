"""Global option sets from the customizations.xml <optionsets> block."""

from __future__ import annotations

from lxml import etree

from docgen.parsers.base import ParseContext, loc_text, to_int
from docgen.snapshot.models import Option, OptionSet

# RootComponent type code for a global option set
TYPE_OPTION_SET = 9


def parse_option_el(el: etree._Element) -> OptionSet:
    """Parse one <optionset> element (used for both global and inline local sets)."""
    options: list[Option] = []
    for opt in el.findall("options/option"):
        value = to_int(opt.get("value"))
        if value is None:
            continue
        options.append(
            Option(
                value=value,
                label=loc_text(opt, "labels/label") or "",
                description=loc_text(opt, "Descriptions/Description"),
            )
        )
    from docgen.parsers.base import text

    return OptionSet(
        name=el.get("Name") or el.get("localizedName") or "",
        display_name=loc_text(el, "displaynames/displayname") or el.get("localizedName"),
        option_set_type=text(el, "OptionSetType"),
        options=options,
    )


def parse_global_optionsets(ctx: ParseContext, block: etree._Element | None) -> list[OptionSet]:
    result: list[OptionSet] = []
    if block is None:
        return result
    for el in block.findall("optionset"):
        try:
            option_set = parse_option_el(el)
            if not option_set.name:
                ctx.warn("unparsed_element", "customizations.xml/optionsets", "optionset without a Name attribute")
                continue
            option_set = option_set.model_copy(update={"is_global": True})
            result.append(option_set)
            ctx.claim(TYPE_OPTION_SET, option_set.name)
        except Exception as exc:  # tolerant: one bad component never kills the parse
            ctx.warn("component_error", "customizations.xml/optionsets", f"{el.get('Name')}: {exc}")
    return result
