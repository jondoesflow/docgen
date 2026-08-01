"""Security roles (with privileges) and field security profiles."""

from __future__ import annotations

from lxml import etree

from docgen.parsers.base import ParseContext, text
from docgen.snapshot.models import FieldPermission, FieldSecurityProfile, RolePrivilege, SecurityRole

TYPE_ROLE = 20
TYPE_FIELD_SECURITY_PROFILE = 70

# Export privilege depth names → normalised levels
_LEVELS = {"none": "none", "basic": "user", "local": "business_unit", "deep": "parent_child", "global": "organization"}


def parse_roles(ctx: ParseContext, block: etree._Element | None) -> list[SecurityRole]:
    roles: list[SecurityRole] = []
    if block is None:
        return roles
    for role_el in block.findall("Role"):
        name = role_el.get("name") or "(unnamed role)"
        try:
            role_id = (role_el.get("id") or "").strip("{}").lower()
            privileges = []
            for priv in role_el.findall("RolePrivileges/RolePrivilege"):
                priv_name = priv.get("name")
                if not priv_name:
                    continue
                raw_level = (priv.get("level") or "none").lower()
                level = _LEVELS.get(raw_level)
                if level is None:
                    ctx.warn("unrecognised_value", f"customizations.xml/Roles/{name}",
                             f"unknown privilege level {raw_level!r} on {priv_name}")
                    level = raw_level
                privileges.append(RolePrivilege(name=priv_name, level=level))
            roles.append(SecurityRole(name=name, role_id=role_id or None,
                                      description=text(role_el, "Description"), privileges=privileges))
            if role_id:
                ctx.claim(TYPE_ROLE, role_id)
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/Roles/{name}", str(exc))
    return roles


def _permission_allowed(value: str | None) -> bool:
    return (value or "0").strip() not in ("", "0")


def parse_field_security_profiles(ctx: ParseContext, block: etree._Element | None) -> list[FieldSecurityProfile]:
    profiles: list[FieldSecurityProfile] = []
    if block is None:
        return profiles
    for profile_el in block.findall("fieldsecurityprofile"):
        name = profile_el.get("name") or "(unnamed profile)"
        try:
            profile_id = (profile_el.get("id") or "").strip("{}").lower()
            permissions = []
            for perm in profile_el.findall("fieldpermissions/fieldpermission"):
                permissions.append(FieldPermission(
                    entity=(perm.get("entityname") or "").lower(),
                    attribute=(perm.get("attributelogicalname") or "").lower(),
                    can_read=_permission_allowed(perm.get("canread")),
                    can_create=_permission_allowed(perm.get("cancreate")),
                    can_update=_permission_allowed(perm.get("canupdate")),
                ))
            profiles.append(FieldSecurityProfile(
                name=name, profile_id=profile_id or None,
                description=text(profile_el, "Description"), attribute_permissions=permissions,
            ))
            if profile_id:
                ctx.claim(TYPE_FIELD_SECURITY_PROFILE, profile_id)
        except Exception as exc:
            ctx.warn("component_error", f"customizations.xml/FieldSecurityProfiles/{name}", str(exc))
    return profiles
