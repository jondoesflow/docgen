"""Programmatic Dynamics 365 solution-zip builder for test fixtures.

How the fixtures are made
-------------------------
Real solution zips are hard to commit (client data, size, non-determinism), so
fixtures are assembled here with lxml element construction, mirroring the
structure of genuine unmanaged solution exports: `solution.xml` with a
SolutionManifest (UniqueName, LocalizedNames, Version, Managed, Publisher,
RootComponents), `customizations.xml` with an ImportExportXml root containing
the component families, `[Content_Types].xml`, and cloud-flow clientdata JSON
under `Workflows/`. Where the real format varies between platform versions we
follow the shape documented in Microsoft's solution file reference; the
parsers are deliberately tolerant of variation either way.

Determinism: GUIDs are uuid5 hashes of component names and every zip entry is
written with a fixed timestamp, so rebuilding produces byte-identical zips.

Regenerate all committed fixtures with:  python tests/fixture_builder.py
"""

from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

from lxml import etree
from lxml.builder import E

FIXTURES_DIR = Path(__file__).parent / "fixtures"
_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-00000000d0c6")
_ZIP_DATE = (2020, 1, 1, 0, 0, 0)


def guid(name: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, name))


def _loc(tag: str, description: str, child_tag: str | None = None) -> etree._Element:
    child_tag = child_tag or tag.rstrip("s")  # LocalizedNames -> LocalizedName
    el = etree.Element(tag)
    etree.SubElement(el, child_tag, description=description, languagecode="1033")
    return el


class EntitySpec:
    def __init__(self, logical: str, display: str, *, plural: str | None = None, description: str | None = None,
                 ownership_mask: int = 1, custom: bool = True, activity: bool = False):
        self.logical = logical
        self.display = display
        self.plural = plural or display + "s"
        self.description = description
        self.ownership_mask = ownership_mask
        self.custom = custom
        self.activity = activity
        self.attributes: list[dict] = []
        self.forms: list[dict] = []
        self.views: list[dict] = []

    def add_attribute(self, logical: str, display: str, *, type: str = "nvarchar", required: str = "none",
                      description: str | None = None, custom: bool = True, max_length: int | None = None,
                      min_value: float | None = None, max_value: float | None = None, precision: int | None = None,
                      optionset_name: str | None = None, inline_options: list[tuple[int, str]] | None = None,
                      lookup_targets: list[str] | None = None, primary_name: bool = False,
                      secured: bool = False, audit: bool = False) -> "EntitySpec":
        self.attributes.append(dict(
            logical=logical, display=display, type=type, required=required, description=description,
            custom=custom, max_length=max_length, min_value=min_value, max_value=max_value,
            precision=precision, optionset_name=optionset_name, inline_options=inline_options,
            lookup_targets=lookup_targets or [], primary_name=primary_name, secured=secured, audit=audit,
        ))
        return self

    def add_form(self, name: str, form_type: str = "main") -> "EntitySpec":
        self.forms.append(dict(name=name, form_type=form_type))
        return self

    def add_view(self, name: str, *, querytype: int = 0, default: bool = False,
                 columns: list[str] | None = None) -> "EntitySpec":
        self.views.append(dict(name=name, querytype=querytype, default=default, columns=columns or []))
        return self


class SolutionBuilder:
    def __init__(self, unique_name: str, display_name: str, *, version: str = "1.0.0.0", managed: bool = False,
                 publisher_unique: str = "devpub", publisher_display: str = "Dev Publisher",
                 prefix: str = "abc", option_prefix: int = 10000):
        self.unique_name = unique_name
        self.display_name = display_name
        self.version = version
        self.managed = managed
        self.publisher_unique = publisher_unique
        self.publisher_display = publisher_display
        self.prefix = prefix
        self.option_prefix = option_prefix
        self.entities: list[EntitySpec] = []
        self.relationships: list[dict] = []
        self.global_optionsets: list[dict] = []
        self.roles: list[dict] = []
        self.field_security_profiles: list[dict] = []
        self.flows: list[dict] = []
        self.business_rules: list[dict] = []
        self.connection_references: list[dict] = []
        self.environment_variables: list[dict] = []
        self.plugin_assemblies: list[dict] = []
        self.plugin_steps: list[dict] = []
        self.web_resources: list[dict] = []
        self.canvas_apps: list[dict] = []
        self.custom_connectors: list[dict] = []
        self.extra_root_components: list[dict] = []

    # ---------------- component adders ----------------

    def add_entity(self, logical: str, display: str, **kwargs) -> EntitySpec:
        spec = EntitySpec(logical, display, **kwargs)
        self.entities.append(spec)
        return spec

    def add_relationship_1n(self, name: str, referenced: str, referencing: str, attribute: str,
                            *, cascade_delete: str = "RemoveLink", custom: bool = True) -> None:
        self.relationships.append(dict(kind="1n", name=name, referenced=referenced, referencing=referencing,
                                       attribute=attribute, cascade_delete=cascade_delete, custom=custom))

    def add_relationship_nn(self, name: str, first: str, second: str, *, custom: bool = True) -> None:
        self.relationships.append(dict(kind="nn", name=name, first=first, second=second, custom=custom))

    def add_global_optionset(self, name: str, display: str, options: list[tuple[int, str]]) -> None:
        self.global_optionsets.append(dict(name=name, display=display, options=options))

    def add_role(self, name: str, privileges: list[tuple[str, str]]) -> None:
        """privileges: list of (privilege name, level) with level in Basic|Local|Deep|Global|None."""
        self.roles.append(dict(name=name, privileges=privileges))

    def add_field_security_profile(self, name: str, description: str | None,
                                   permissions: list[tuple[str, str, bool, bool, bool]]) -> None:
        """permissions: (entity, attribute, can_read, can_create, can_update)."""
        self.field_security_profiles.append(dict(name=name, description=description, permissions=permissions))

    def add_flow(self, name: str, clientdata: dict | None, *, state_code: int = 1,
                 missing_json: bool = False, description: str | None = None) -> None:
        """A cloud flow (Workflow category 5). clientdata None + missing_json emits a
        Workflow element whose JsonFileName points at a file absent from the zip."""
        self.flows.append(dict(name=name, clientdata=clientdata, state_code=state_code,
                               missing_json=missing_json, description=description))

    def add_business_rule(self, name: str, primary_entity: str, *, scope: int = 2, state_code: int = 1) -> None:
        self.business_rules.append(dict(name=name, primary_entity=primary_entity, scope=scope, state_code=state_code))

    def add_connection_reference(self, logical: str, display: str, api_name: str) -> None:
        self.connection_references.append(dict(logical=logical, display=display, api_name=api_name))

    def add_environment_variable(self, schema: str, display: str, *, type_code: int = 100000000,
                                 default: str | None = None, value: str | None = None,
                                 description: str | None = None) -> None:
        self.environment_variables.append(dict(schema=schema, display=display, type_code=type_code,
                                               default=default, value=value, description=description))

    def add_plugin_assembly(self, name: str, *, version: str = "1.0.0.0", isolation_mode: int = 2,
                            public_key_token: str = "abcdef1234567890") -> None:
        self.plugin_assemblies.append(dict(name=name, version=version, isolation_mode=isolation_mode,
                                           public_key_token=public_key_token))

    def add_plugin_step(self, name: str, *, assembly: str, plugin_type: str, message: str,
                        primary_entity: str, stage: int = 40, mode: int = 0, rank: int = 1,
                        filtering_attributes: list[str] | None = None, state_code: int = 0) -> None:
        self.plugin_steps.append(dict(name=name, assembly=assembly, plugin_type=plugin_type, message=message,
                                      primary_entity=primary_entity, stage=stage, mode=mode, rank=rank,
                                      filtering_attributes=filtering_attributes or [], state_code=state_code))

    def add_web_resource(self, name: str, display: str, *, type_code: int = 3) -> None:
        self.web_resources.append(dict(name=name, display=display, type_code=type_code))

    def add_canvas_app(self, name: str, display: str, *, connections: list[str] | None = None) -> None:
        self.canvas_apps.append(dict(name=name, display=display, connections=connections or []))

    def add_custom_connector(self, name: str, display: str, description: str | None = None) -> None:
        self.custom_connectors.append(dict(name=name, display=display, description=description))

    def add_root_component(self, type_code: int, *, schema_name: str | None = None,
                           component_id: str | None = None) -> None:
        """Extra raw RootComponent — used to test the generic/unknown fallback."""
        self.extra_root_components.append(dict(type_code=type_code, schema_name=schema_name,
                                               component_id=component_id))

    # ---------------- XML assembly ----------------

    def _solution_xml(self) -> bytes:
        publisher = E.Publisher(
            E.UniqueName(self.publisher_unique),
            _loc("LocalizedNames", self.publisher_display),
            E.Descriptions(),
            E.EMailAddress(),
            E.SupportingWebsiteUrl(),
            E.CustomizationPrefix(self.prefix),
            E.CustomizationOptionValuePrefix(str(self.option_prefix)),
        )
        root_components = etree.Element("RootComponents")

        def rc(type_code: int, schema_name: str | None = None, component_id: str | None = None):
            el = etree.SubElement(root_components, "RootComponent", type=str(type_code), behavior="0")
            if schema_name:
                el.set("schemaName", schema_name)
            if component_id:
                el.set("id", "{" + component_id + "}")

        for ent in self.entities:
            rc(1, schema_name=ent.logical)
        for os_ in self.global_optionsets:
            rc(9, schema_name=os_["name"])
        for role in self.roles:
            rc(20, component_id=guid("role:" + role["name"]))
        for fsp in self.field_security_profiles:
            rc(70, component_id=guid("fsp:" + fsp["name"]))
        for flow in self.flows:
            rc(29, component_id=guid("flow:" + flow["name"]))
        for br in self.business_rules:
            rc(29, component_id=guid("br:" + br["name"]))
        for cr in self.connection_references:
            rc(10112, schema_name=cr["logical"])
        for ev in self.environment_variables:
            rc(380, schema_name=ev["schema"])
        for pa in self.plugin_assemblies:
            rc(91, schema_name=pa["name"])
        for ps in self.plugin_steps:
            rc(92, component_id=guid("step:" + ps["name"]))
        for wr in self.web_resources:
            rc(61, schema_name=wr["name"])
        for app in self.canvas_apps:
            rc(300, schema_name=app["name"])
        for cc in self.custom_connectors:
            rc(372, schema_name=cc["name"])
        for extra in self.extra_root_components:
            rc(extra["type_code"], schema_name=extra["schema_name"], component_id=extra["component_id"])

        manifest = E.SolutionManifest(
            E.UniqueName(self.unique_name),
            _loc("LocalizedNames", self.display_name),
            E.Descriptions(),
            E.Version(self.version),
            E.Managed("1" if self.managed else "0"),
            publisher,
            root_components,
        )
        root = E.ImportExportXml(manifest, version="9.2.0.0", SolutionPackageVersion="9.2", languagecode="1033",
                                 generatedBy="CrmLive")
        return etree.tostring(root, xml_declaration=True, encoding="utf-8", pretty_print=True)

    def _attribute_xml(self, spec: dict) -> etree._Element:
        att = etree.Element("attribute", PhysicalName=spec["logical"])
        etree.SubElement(att, "Type").text = spec["type"]
        etree.SubElement(att, "Name").text = spec["logical"]
        etree.SubElement(att, "LogicalName").text = spec["logical"]
        etree.SubElement(att, "RequiredLevel").text = spec["required"]
        mask = ["ValidForAdvancedFind", "ValidForForm", "ValidForGrid"]
        if spec["primary_name"]:
            mask.append("PrimaryName")
        etree.SubElement(att, "DisplayMask").text = "|".join(mask)
        etree.SubElement(att, "IsCustomField").text = "1" if spec["custom"] else "0"
        etree.SubElement(att, "IsAuditEnabled").text = "1" if spec["audit"] else "0"
        etree.SubElement(att, "IsSecured").text = "1" if spec["secured"] else "0"
        if spec["max_length"] is not None:
            etree.SubElement(att, "MaxLength").text = str(spec["max_length"])
        if spec["min_value"] is not None:
            etree.SubElement(att, "MinValue").text = str(spec["min_value"])
        if spec["max_value"] is not None:
            etree.SubElement(att, "MaxValue").text = str(spec["max_value"])
        if spec["precision"] is not None:
            etree.SubElement(att, "Accuracy").text = str(spec["precision"])
        if spec["optionset_name"]:
            etree.SubElement(att, "OptionSetName").text = spec["optionset_name"]
        if spec["inline_options"]:
            att.append(self._optionset_xml(spec["logical"], spec["display"], spec["inline_options"], "picklist"))
        for target in spec["lookup_targets"]:
            lookup_types = att.find("LookupTypes")
            if lookup_types is None:
                lookup_types = etree.SubElement(att, "LookupTypes")
            lt = etree.SubElement(lookup_types, "LookupType", id=guid("lookup:" + spec["logical"] + ":" + target))
            lt.text = target
        att.append(_loc("displaynames", spec["display"], "displayname"))
        if spec["description"]:
            att.append(_loc("Descriptions", spec["description"], "Description"))
        return att

    def _optionset_xml(self, name: str, display: str, options: list[tuple[int, str]],
                       set_type: str = "picklist") -> etree._Element:
        os_el = etree.Element("optionset", Name=name, localizedName=display)
        etree.SubElement(os_el, "OptionSetType").text = set_type
        os_el.append(_loc("displaynames", display, "displayname"))
        options_el = etree.SubElement(os_el, "options")
        for value, label in options:
            opt = etree.SubElement(options_el, "option", value=str(value))
            opt.append(_loc("labels", label, "label"))
        return os_el

    def _entity_xml(self, spec: EntitySpec) -> etree._Element:
        entity_el = etree.Element("entity", Name=spec.logical)
        entity_el.append(_loc("LocalizedNames", spec.display))
        entity_el.append(_loc("LocalizedCollectionNames", spec.plural, "LocalizedCollectionName"))
        if spec.description:
            entity_el.append(_loc("Descriptions", spec.description, "Description"))
        else:
            entity_el.append(etree.Element("Descriptions"))
        etree.SubElement(entity_el, "OwnershipTypeMask").text = str(spec.ownership_mask)
        etree.SubElement(entity_el, "IsCustomEntity").text = "1" if spec.custom else "0"
        etree.SubElement(entity_el, "IsActivity").text = "1" if spec.activity else "0"
        attributes_el = etree.SubElement(entity_el, "attributes")
        for att in spec.attributes:
            attributes_el.append(self._attribute_xml(att))

        block = etree.Element("Entity")
        name_el = etree.SubElement(block, "Name", LocalizedName=spec.display, OriginalName=spec.display)
        name_el.text = spec.logical
        info = etree.SubElement(block, "EntityInfo")
        info.append(entity_el)

        if spec.forms:
            form_xml = etree.SubElement(block, "FormXml")
            by_type: dict[str, etree._Element] = {}
            for form in spec.forms:
                forms_el = by_type.get(form["form_type"])
                if forms_el is None:
                    forms_el = etree.SubElement(form_xml, "forms", type=form["form_type"])
                    by_type[form["form_type"]] = forms_el
                sf = etree.SubElement(forms_el, "systemform")
                etree.SubElement(sf, "formid").text = "{" + guid(f"form:{spec.logical}:{form['name']}") + "}"
                etree.SubElement(sf, "FormActivationState").text = "1"
                sf.append(_loc("LocalizedNames", form["name"]))

        if spec.views:
            saved = etree.SubElement(block, "SavedQueries")
            queries = etree.SubElement(saved, "savedqueries")
            for view in spec.views:
                sq = etree.SubElement(queries, "savedquery")
                etree.SubElement(sq, "savedqueryid").text = "{" + guid(f"view:{spec.logical}:{view['name']}") + "}"
                etree.SubElement(sq, "isdefault").text = "1" if view["default"] else "0"
                etree.SubElement(sq, "querytype").text = str(view["querytype"])
                layout = etree.SubElement(sq, "layoutxml")
                grid = etree.SubElement(layout, "grid", name="resultset", object="1", jump="name", select="1")
                row = etree.SubElement(grid, "row", name="result", id=f"{spec.logical}id")
                for col in view["columns"]:
                    etree.SubElement(row, "cell", name=col, width="150")
                sq.append(_loc("LocalizedNames", view["name"]))
        return block

    def _flow_json_name(self, flow_name: str) -> str:
        stem = flow_name.replace(" ", "")
        return f"Workflows/{stem}-{guid('flow:' + flow_name).upper()}.json"

    def _customizations_xml(self) -> bytes:
        root = etree.Element("ImportExportXml")

        entities_el = etree.SubElement(root, "Entities")
        for spec in self.entities:
            entities_el.append(self._entity_xml(spec))

        if self.relationships:
            rels_el = etree.SubElement(root, "EntityRelationships")
            for rel in self.relationships:
                rel_el = etree.SubElement(rels_el, "EntityRelationship", Name=rel["name"])
                if rel["kind"] == "nn":
                    etree.SubElement(rel_el, "EntityRelationshipType").text = "ManyToManyRelationship"
                    etree.SubElement(rel_el, "IsCustomRelationship").text = "1" if rel["custom"] else "0"
                    etree.SubElement(rel_el, "FirstEntityName").text = rel["first"]
                    etree.SubElement(rel_el, "SecondEntityName").text = rel["second"]
                else:
                    etree.SubElement(rel_el, "EntityRelationshipType").text = "OneToManyRelationship"
                    etree.SubElement(rel_el, "IsCustomRelationship").text = "1" if rel["custom"] else "0"
                    etree.SubElement(rel_el, "ReferencedEntityName").text = rel["referenced"]
                    etree.SubElement(rel_el, "ReferencingEntityName").text = rel["referencing"]
                    etree.SubElement(rel_el, "ReferencingAttributeName").text = rel["attribute"]
                    etree.SubElement(rel_el, "CascadeDelete").text = rel["cascade_delete"]

        if self.roles:
            roles_el = etree.SubElement(root, "Roles")
            for role in self.roles:
                role_el = etree.SubElement(roles_el, "Role",
                                           id="{" + guid("role:" + role["name"]) + "}", name=role["name"])
                privs = etree.SubElement(role_el, "RolePrivileges")
                for priv_name, level in role["privileges"]:
                    etree.SubElement(privs, "RolePrivilege", name=priv_name, level=level)

        if self.business_rules or self.flows:
            workflows_el = etree.SubElement(root, "Workflows")
            for flow in self.flows:
                wf = etree.SubElement(workflows_el, "Workflow",
                                      WorkflowId="{" + guid("flow:" + flow["name"]) + "}", Name=flow["name"])
                etree.SubElement(wf, "JsonFileName").text = "/" + self._flow_json_name(flow["name"])
                etree.SubElement(wf, "Type").text = "1"
                etree.SubElement(wf, "Category").text = "5"
                etree.SubElement(wf, "StateCode").text = str(flow["state_code"])
                etree.SubElement(wf, "PrimaryEntity").text = "none"
                if flow["description"]:
                    etree.SubElement(wf, "Description").text = flow["description"]
            for br in self.business_rules:
                wf = etree.SubElement(workflows_el, "Workflow",
                                      WorkflowId="{" + guid("br:" + br["name"]) + "}", Name=br["name"])
                etree.SubElement(wf, "Type").text = "1"
                etree.SubElement(wf, "Category").text = "2"
                etree.SubElement(wf, "Scope").text = str(br["scope"])
                etree.SubElement(wf, "StateCode").text = str(br["state_code"])
                etree.SubElement(wf, "PrimaryEntity").text = br["primary_entity"]

        if self.field_security_profiles:
            fsps_el = etree.SubElement(root, "FieldSecurityProfiles")
            for fsp in self.field_security_profiles:
                fsp_el = etree.SubElement(fsps_el, "fieldsecurityprofile",
                                          id="{" + guid("fsp:" + fsp["name"]) + "}", name=fsp["name"])
                if fsp["description"]:
                    etree.SubElement(fsp_el, "Description").text = fsp["description"]
                perms = etree.SubElement(fsp_el, "fieldpermissions")
                for entity, attribute, can_read, can_create, can_update in fsp["permissions"]:
                    etree.SubElement(perms, "fieldpermission",
                                     entityname=entity, attributelogicalname=attribute,
                                     canread="4" if can_read else "0",
                                     cancreate="4" if can_create else "0",
                                     canupdate="4" if can_update else "0",
                                     id="{" + guid(f"fp:{fsp['name']}:{entity}:{attribute}") + "}")

        if self.global_optionsets:
            optionsets_el = etree.SubElement(root, "optionsets")
            for os_ in self.global_optionsets:
                os_el = self._optionset_xml(os_["name"], os_["display"], os_["options"])
                etree.SubElement(os_el, "IsGlobal").text = "1"
                optionsets_el.append(os_el)

        if self.connection_references:
            crs_el = etree.SubElement(root, "connectionreferences")
            for cr in self.connection_references:
                cr_el = etree.SubElement(crs_el, "connectionreference",
                                         connectionreferencelogicalname=cr["logical"])
                etree.SubElement(cr_el, "connectionreferencedisplayname").text = cr["display"]
                etree.SubElement(cr_el, "connectorid").text = \
                    f"/providers/Microsoft.PowerApps/apis/{cr['api_name']}"

        if self.environment_variables:
            evs_el = etree.SubElement(root, "EnvironmentVariables")
            for ev in self.environment_variables:
                ev_el = etree.SubElement(evs_el, "environmentvariabledefinition", schemaname=ev["schema"])
                etree.SubElement(ev_el, "displayname", default=ev["display"])
                if ev["description"]:
                    etree.SubElement(ev_el, "description", default=ev["description"])
                etree.SubElement(ev_el, "type").text = str(ev["type_code"])
                if ev["default"] is not None:
                    etree.SubElement(ev_el, "defaultvalue").text = ev["default"]
                if ev["value"] is not None:
                    values_el = ev_el.find("environmentvariablevalues")
                    if values_el is None:
                        values_el = etree.SubElement(ev_el, "environmentvariablevalues")
                    val_el = etree.SubElement(values_el, "environmentvariablevalue", schemaname=ev["schema"])
                    etree.SubElement(val_el, "value").text = ev["value"]

        if self.plugin_assemblies:
            pas_el = etree.SubElement(root, "PluginAssemblies")
            for pa in self.plugin_assemblies:
                full_name = (f"{pa['name']}, Version={pa['version']}, Culture=neutral, "
                             f"PublicKeyToken={pa['public_key_token']}")
                pa_el = etree.SubElement(pas_el, "PluginAssembly", FullName=full_name)
                etree.SubElement(pa_el, "IsolationMode").text = str(pa["isolation_mode"])

        if self.plugin_steps:
            steps_el = etree.SubElement(root, "SdkMessageProcessingSteps")
            for ps in self.plugin_steps:
                step_el = etree.SubElement(
                    steps_el, "SdkMessageProcessingStep", Name=ps["name"],
                    SdkMessageProcessingStepId="{" + guid("step:" + ps["name"]) + "}")
                etree.SubElement(step_el, "PluginTypeName").text = ps["plugin_type"]
                etree.SubElement(step_el, "PluginAssemblyName").text = ps["assembly"]
                etree.SubElement(step_el, "SdkMessage").text = ps["message"]
                etree.SubElement(step_el, "PrimaryEntity").text = ps["primary_entity"]
                etree.SubElement(step_el, "Stage").text = str(ps["stage"])
                etree.SubElement(step_el, "Mode").text = str(ps["mode"])
                etree.SubElement(step_el, "Rank").text = str(ps["rank"])
                if ps["filtering_attributes"]:
                    etree.SubElement(step_el, "FilteringAttributes").text = ",".join(ps["filtering_attributes"])
                etree.SubElement(step_el, "StateCode").text = str(ps["state_code"])

        if self.web_resources:
            wrs_el = etree.SubElement(root, "WebResources")
            for wr in self.web_resources:
                wr_el = etree.SubElement(wrs_el, "WebResource")
                etree.SubElement(wr_el, "Name").text = wr["name"]
                etree.SubElement(wr_el, "DisplayName").text = wr["display"]
                etree.SubElement(wr_el, "WebResourceType").text = str(wr["type_code"])

        if self.canvas_apps:
            apps_el = etree.SubElement(root, "CanvasApps")
            for app in self.canvas_apps:
                app_el = etree.SubElement(apps_el, "CanvasApp")
                etree.SubElement(app_el, "Name").text = app["name"]
                etree.SubElement(app_el, "DisplayName").text = app["display"]
                if app["connections"]:
                    etree.SubElement(app_el, "Connections").text = ",".join(app["connections"])

        if self.custom_connectors:
            ccs_el = etree.SubElement(root, "Connectors")
            for cc in self.custom_connectors:
                cc_el = etree.SubElement(ccs_el, "Connector")
                etree.SubElement(cc_el, "Name").text = cc["name"]
                etree.SubElement(cc_el, "DisplayName").text = cc["display"]
                if cc["description"]:
                    etree.SubElement(cc_el, "Description").text = cc["description"]

        langs = etree.SubElement(root, "Languages")
        etree.SubElement(langs, "Language").text = "1033"

        return etree.tostring(root, xml_declaration=True, encoding="utf-8", pretty_print=True)

    @staticmethod
    def _content_types_xml() -> bytes:
        root = etree.Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
        etree.SubElement(root, "Default", Extension="xml", ContentType="application/octet-stream")
        etree.SubElement(root, "Default", Extension="json", ContentType="application/octet-stream")
        return etree.tostring(root, xml_declaration=True, encoding="utf-8", pretty_print=True)

    def build(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        entries: list[tuple[str, bytes]] = [
            ("[Content_Types].xml", self._content_types_xml()),
            ("solution.xml", self._solution_xml()),
            ("customizations.xml", self._customizations_xml()),
        ]
        for flow in self.flows:
            if flow["clientdata"] is not None and not flow["missing_json"]:
                payload = json.dumps(flow["clientdata"], indent=2, sort_keys=True).encode("utf-8")
                entries.append((self._flow_json_name(flow["name"]), payload))
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in entries:
                info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, data)
        return path


# ---------------------------------------------------------------------------
# Flow clientdata helpers
# ---------------------------------------------------------------------------


def make_flow_clientdata(*, trigger_name: str = "When_a_row_is_added",
                         trigger_connector: str | None = "shared_commondataserviceforapps",
                         trigger_type: str = "OpenApiConnectionWebhook",
                         connection_references: dict[str, str] | None = None,
                         actions: dict | None = None) -> dict:
    """Build a realistic clientdata JSON body.

    connection_references maps connector api name -> connection reference logical name.
    actions is the raw definition.actions dict (nesting allowed via "actions" children).
    """
    connection_references = connection_references or {}
    trigger: dict = {"type": trigger_type}
    if trigger_connector:
        trigger["inputs"] = {
            "host": {
                "connectionName": trigger_connector,
                "operationId": "SubscribeWebhookTrigger",
                "apiId": f"/providers/Microsoft.PowerApps/apis/{trigger_connector}",
            }
        }
    return {
        "schemaVersion": "1.0.0.0",
        "properties": {
            "connectionReferences": {
                api: {
                    "connection": {"connectionReferenceLogicalName": logical},
                    "api": {"name": api},
                }
                for api, logical in connection_references.items()
            },
            "definition": {
                "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
                "contentVersion": "1.0.0.0",
                "triggers": {trigger_name: trigger},
                "actions": actions or {},
            },
        },
    }


def api_action(name_connector: str, operation_id: str, *, run_after: dict | None = None) -> dict:
    return {
        "type": "OpenApiConnection",
        "runAfter": run_after or {},
        "inputs": {
            "host": {
                "connectionName": name_connector,
                "operationId": operation_id,
                "apiId": f"/providers/Microsoft.PowerApps/apis/{name_connector}",
            }
        },
    }


# ---------------------------------------------------------------------------
# Fixture definitions
# ---------------------------------------------------------------------------


def build_minimal() -> SolutionBuilder:
    b = SolutionBuilder("MinimalSolution", "Minimal Solution", version="1.0.0.0", prefix="min",
                        publisher_unique="minpub", publisher_display="Minimal Publisher")
    ent = b.add_entity("min_widget", "Widget", description="A minimal test table.")
    ent.add_attribute("min_name", "Name", required="systemrequired", max_length=100, primary_name=True,
                      description="Primary name of the widget.")
    ent.add_attribute("min_size", "Size", type="int", min_value=0, max_value=100)
    return b


def build_rich() -> SolutionBuilder:
    b = SolutionBuilder("RichSolution", "Rich CE Solution", version="2.1.0.0", prefix="abc")

    project = b.add_entity("abc_project", "Project", description="A client engagement or internal project.")
    project.add_attribute("abc_name", "Project Name", required="systemrequired", max_length=200, primary_name=True,
                          description="The name of the project.")
    project.add_attribute("abc_status", "Status", type="picklist", optionset_name="abc_projectstatus",
                          description="Lifecycle status of the project.")
    project.add_attribute("abc_budget", "Budget", type="money", min_value=0, max_value=10000000, precision=2,
                          description="Approved budget.", audit=True)
    project.add_attribute("abc_description", "Description", type="ntext", max_length=4000)  # no description: hygiene
    project.add_form("Information", "main").add_form("Quick Create", "quickcreate")
    project.add_view("Active Projects", default=True, columns=["abc_name", "abc_status", "abc_budget"])
    project.add_view("Project Lookup", querytype=64, columns=["abc_name"])

    task = b.add_entity("abc_task", "Project Task", description="Work item under a project.")
    task.add_attribute("abc_name", "Task Name", required="systemrequired", max_length=150, primary_name=True,
                       description="Short task title.")
    task.add_attribute("abc_projectid", "Project", type="lookup", required="required",
                       lookup_targets=["abc_project"], description="Parent project.")
    task.add_attribute("abc_effort", "Effort (hours)", type="decimal", min_value=0, max_value=1000, precision=2)
    task.add_attribute("abc_priority", "Priority", type="picklist",
                       inline_options=[(10000, "Low"), (10001, "Medium"), (10002, "High")],
                       description="Task priority.")
    task.add_form("Information", "main")
    task.add_view("My Tasks", default=True, columns=["abc_name", "abc_priority"])

    employee = b.add_entity("abc_employee", "Employee", description="Internal staff member.")
    employee.add_attribute("abc_name", "Full Name", required="systemrequired", max_length=120, primary_name=True,
                           description="Employee full name.")
    employee.add_attribute("abc_salary", "Salary", type="money", secured=True,
                           description="Annual salary — field-secured.")
    employee.add_view("All Employees", default=True, columns=["abc_name"])

    invoice = b.add_entity("abc_invoice", "Client Invoice", description="Invoice raised against a client.")
    invoice.add_attribute("abc_name", "Invoice Number", required="systemrequired", max_length=60, primary_name=True,
                          description="Invoice reference number.")
    invoice.add_attribute("abc_amount", "Amount", type="money", required="required",
                          description="Invoice total.")
    invoice.add_view("All Invoices", default=True, columns=["abc_name", "abc_amount"])

    b.add_relationship_1n("abc_project_task", "abc_project", "abc_task", "abc_projectid",
                          cascade_delete="Cascade")
    b.add_relationship_nn("abc_project_employee", "abc_project", "abc_employee")
    # invoice is deliberately unrelated to the project cluster → second functional cluster

    b.add_global_optionset("abc_projectstatus", "Project Status",
                           [(10000, "Planned"), (10001, "Active"), (10002, "On Hold"), (10003, "Complete")])
    b.add_global_optionset("abc_unused", "Unused Option Set", [(10000, "Never Referenced")])  # hygiene finding

    b.add_role("Project Manager", [
        ("prvCreateabc_project", "Global"), ("prvReadabc_project", "Global"),
        ("prvWriteabc_project", "Global"), ("prvDeleteabc_project", "Local"),
        ("prvCreateabc_task", "Global"), ("prvReadabc_task", "Global"), ("prvWriteabc_task", "Global"),
    ])
    b.add_role("Project Member", [
        ("prvReadabc_project", "Local"), ("prvReadabc_task", "Basic"), ("prvWriteabc_task", "Basic"),
    ])

    b.add_field_security_profile("HR Restricted", "Access to secured HR fields.",
                                 [("abc_employee", "abc_salary", True, False, False)])

    b.add_flow(
        "Notify PM on project creation",
        make_flow_clientdata(
            trigger_connector="shared_commondataserviceforapps",
            connection_references={
                "shared_commondataserviceforapps": "abc_dataverse",
                "shared_office365": "abc_office365",
            },
            actions={
                "Try_scope": {
                    "type": "Scope",
                    "runAfter": {},
                    "actions": {
                        "Get_project_manager": api_action("shared_commondataserviceforapps", "GetItem"),
                        "Send_notification": api_action("shared_office365", "SendEmailV2",
                                                        run_after={"Get_project_manager": ["Succeeded"]}),
                    },
                },
                "Catch_scope": {
                    "type": "Scope",
                    "runAfter": {"Try_scope": ["Failed", "TimedOut"]},
                    "actions": {
                        "Log_failure": api_action("shared_commondataserviceforapps", "CreateRecord"),
                    },
                },
            },
        ),
        description="Emails the project manager when a project is created.",
    )
    b.add_flow(
        "Sync invoices to SQL",
        make_flow_clientdata(
            trigger_name="When_an_invoice_is_updated",
            trigger_connector="shared_commondataserviceforapps",
            connection_references={
                "shared_commondataserviceforapps": "abc_dataverse",
                "shared_sql": "abc_sql",
            },
            actions={
                "Get_invoice": api_action("shared_commondataserviceforapps", "GetItem"),
                "Insert_row": api_action("shared_sql", "ExecuteProcedure",
                                         run_after={"Get_invoice": ["Succeeded"]}),
            },
        ),
        description="Pushes invoice changes into the finance SQL database.",
    )  # premium connector + no error handling → licensing + hygiene findings
    b.add_flow("Broken flow", None, missing_json=True)  # missing JSON file → parse warning

    b.add_business_rule("Require budget when active", "abc_project")

    b.add_connection_reference("abc_dataverse", "Dataverse", "shared_commondataserviceforapps")
    b.add_connection_reference("abc_office365", "Office 365 Outlook", "shared_office365")
    b.add_connection_reference("abc_sql", "Finance SQL", "shared_sql")

    b.add_environment_variable("abc_ApiBaseUrl", "API Base URL", default="https://api.example.test",
                               description="Base URL for the finance API.")
    b.add_environment_variable("abc_ApiKey", "API Key", type_code=100000005)  # secret, no value
    b.add_environment_variable("abc_BatchSize", "Batch Size", type_code=100000001, default="50", value="100")

    b.add_plugin_assembly("Abc.Plugins", version="1.2.0.0", isolation_mode=2)
    b.add_plugin_step("Abc.Plugins.ProjectCreate: Create of abc_project",
                      assembly="Abc.Plugins", plugin_type="Abc.Plugins.ProjectCreate",
                      message="Create", primary_entity="abc_project", stage=40, mode=0, rank=1)
    b.add_plugin_step("Abc.Plugins.TaskUpdate: Update of abc_task",
                      assembly="Abc.Plugins", plugin_type="Abc.Plugins.TaskUpdate",
                      message="Update", primary_entity="abc_task", stage=20, mode=0, rank=1,
                      filtering_attributes=["abc_effort", "abc_priority"])

    b.add_web_resource("abc_/scripts/project_form.js", "Project Form Script", type_code=3)
    b.add_web_resource("abc_/styles/theme.css", "Theme Stylesheet", type_code=2)

    b.add_canvas_app("abc_fieldapp_0001", "Field Inspection App",
                     connections=["shared_commondataserviceforapps", "shared_sharepointonline"])
    b.add_custom_connector("abc_financeapi", "Finance API Connector",
                           "Custom connector to the on-prem finance API.")

    # An unknown component type docgen has no label for → generic fallback path
    b.add_root_component(9999, schema_name="abc_mystery_component")
    return b


def build_diff_v1() -> SolutionBuilder:
    b = SolutionBuilder("DiffSolution", "Diff Test Solution", version="1.0.0.0", prefix="dif",
                        publisher_unique="difpub", publisher_display="Diff Publisher")
    account = b.add_entity("dif_client", "Client", description="A client organisation.")
    account.add_attribute("dif_name", "Client Name", required="systemrequired", max_length=200, primary_name=True,
                          description="Client legal name.")
    account.add_attribute("dif_code", "Client Code", max_length=20, description="Short internal code.")
    account.add_attribute("dif_rating", "Rating", type="picklist",
                          inline_options=[(1, "Bronze"), (2, "Silver"), (3, "Gold")])
    account.add_attribute("dif_notes", "Notes", type="ntext", max_length=2000)
    contract = b.add_entity("dif_contract", "Contract", description="A signed engagement contract.")
    contract.add_attribute("dif_name", "Contract Ref", required="systemrequired", max_length=100, primary_name=True)
    contract.add_attribute("dif_clientid", "Client", type="lookup", required="recommended",
                           lookup_targets=["dif_client"])
    contract.add_attribute("dif_value", "Contract Value", type="money", max_length=None, precision=2)
    b.add_relationship_1n("dif_client_contract", "dif_client", "dif_contract", "dif_clientid")
    b.add_environment_variable("dif_Endpoint", "Endpoint", default="https://v1.example.test")
    b.add_flow(
        "Contract approval",
        make_flow_clientdata(
            trigger_connector="shared_commondataserviceforapps",
            connection_references={"shared_commondataserviceforapps": "dif_dataverse"},
            actions={"Start_approval": api_action("shared_commondataserviceforapps", "CreateRecord")},
        ),
    )
    b.add_connection_reference("dif_dataverse", "Dataverse", "shared_commondataserviceforapps")
    return b


def build_diff_v2() -> SolutionBuilder:
    b = build_diff_v1()
    b.version = "2.0.0.0"

    client = next(e for e in b.entities if e.logical == "dif_client")
    # BREAKING: attribute removed
    client.attributes = [a for a in client.attributes if a["logical"] != "dif_notes"]
    # BREAKING: requirement tightened + max_length reduced
    code = next(a for a in client.attributes if a["logical"] == "dif_code")
    code["required"] = "required"
    code["max_length"] = 10
    # BREAKING: option value removed (Bronze) + label changed
    rating = next(a for a in client.attributes if a["logical"] == "dif_rating")
    rating["inline_options"] = [(2, "Silver"), (3, "Gold"), (4, "Platinum")]

    contract = next(e for e in b.entities if e.logical == "dif_contract")
    # BREAKING: type change money -> decimal
    value = next(a for a in contract.attributes if a["logical"] == "dif_value")
    value["type"] = "decimal"
    # non-breaking: requirement tightened recommended -> required
    clientid = next(a for a in contract.attributes if a["logical"] == "dif_clientid")
    clientid["required"] = "required"

    # added entity + relationship
    invoice = b.add_entity("dif_invoice", "Invoice", description="Invoice against a contract.")
    invoice.add_attribute("dif_name", "Invoice No", required="systemrequired", max_length=60, primary_name=True)
    invoice.add_attribute("dif_contractid", "Contract", type="lookup", lookup_targets=["dif_contract"])
    b.add_relationship_1n("dif_contract_invoice", "dif_contract", "dif_invoice", "dif_contractid")

    # BREAKING: flow trigger connector changed; env var default changed (non-breaking)
    flow = next(f for f in b.flows if f["name"] == "Contract approval")
    flow["clientdata"] = make_flow_clientdata(
        trigger_name="Manual_trigger",
        trigger_connector=None,
        trigger_type="Request",
        connection_references={"shared_commondataserviceforapps": "dif_dataverse"},
        actions={"Start_approval": api_action("shared_commondataserviceforapps", "CreateRecord")},
    )
    ev = next(v for v in b.environment_variables if v["schema"] == "dif_Endpoint")
    ev["default"] = "https://v2.example.test"
    return b


FIXTURES = {
    "minimal.zip": build_minimal,
    "rich.zip": build_rich,
    "diff_v1.zip": build_diff_v1,
    "diff_v2.zip": build_diff_v2,
}


def build_all(target_dir: Path = FIXTURES_DIR) -> list[Path]:
    return [factory().build(target_dir / name) for name, factory in FIXTURES.items()]


if __name__ == "__main__":
    for path in build_all():
        print(f"built {path}")
