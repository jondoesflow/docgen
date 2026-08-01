"""Canonical snapshot schema for a parsed Dynamics 365 CE / Power Platform solution.

The snapshot is the single source of truth for every renderer: parse writes it,
render/check/diff read it. All collections are lists of keyed models; the key
field of each model is what `snapshot.io.canonicalise` sorts by and what the
diff engine matches on. Value fields deliberately stay plain (str/int/bool)
rather than strict enums so that unusual real-world exports degrade to odd
values plus a parse warning, never a crash.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class DocgenModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------


class ParseWarning(DocgenModel):
    """Anything the parser could not fully understand. Nothing is silently dropped."""

    code: str  # e.g. unknown_component, unparsed_element, missing_flow_json, component_error
    context: str = ""  # file name and/or xpath-ish location
    message: str = ""


# ---------------------------------------------------------------------------
# Option sets
# ---------------------------------------------------------------------------


class Option(DocgenModel):
    value: int
    label: str = ""
    description: str | None = None


class OptionSet(DocgenModel):
    name: str  # key
    display_name: str | None = None
    is_global: bool = False
    option_set_type: str | None = None  # picklist, boolean, state, status
    options: list[Option] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Entities and their children
# ---------------------------------------------------------------------------


class Attribute(DocgenModel):
    logical_name: str  # key
    display_name: str | None = None
    schema_name: str | None = None
    type: str = ""  # raw D365 attribute type, e.g. nvarchar, picklist, lookup, money
    requirement_level: str = "none"  # normalised: none | recommended | required | system_required
    description: str | None = None
    is_custom: bool = False
    max_length: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    precision: int | None = None
    option_set_name: str | None = None  # reference to a global option set
    local_option_set: OptionSet | None = None  # inline (local) option set
    lookup_targets: list[str] = Field(default_factory=list)
    is_secured: bool = False
    is_calculated: bool = False
    is_rollup: bool = False
    audit_enabled: bool = False


class Relationship(DocgenModel):
    schema_name: str  # key
    type: str = "one_to_many"  # one_to_many | many_to_many
    referenced_entity: str = ""  # the "one" side (or first entity for N:N)
    referencing_entity: str = ""  # the "many" side (or second entity for N:N)
    referencing_attribute: str | None = None  # lookup attribute on the referencing entity
    cascade_delete: str | None = None  # e.g. Cascade, RemoveLink, Restrict
    is_custom: bool = False


class Form(DocgenModel):
    name: str
    form_id: str = ""  # part of sort key; forms may share names
    form_type: str = ""  # main, quickcreate, card, quickview...
    state: str | None = None


class View(DocgenModel):
    name: str
    saved_query_id: str = ""
    view_type: str = ""  # public, advanced find, associated, quick find...
    is_default: bool = False
    columns: list[str] = Field(default_factory=list)


class BusinessRule(DocgenModel):
    name: str  # key
    scope: str | None = None
    state: str | None = None
    primary_entity: str | None = None


class Entity(DocgenModel):
    logical_name: str  # key
    display_name: str | None = None
    display_collection_name: str | None = None
    description: str | None = None
    ownership_type: str | None = None  # UserOwned | OrganizationOwned | ...
    is_custom: bool = False
    is_activity: bool = False
    primary_name_attribute: str | None = None
    attributes: list[Attribute] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    forms: list[Form] = Field(default_factory=list)
    views: list[View] = Field(default_factory=list)
    business_rules: list[BusinessRule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


class RolePrivilege(DocgenModel):
    name: str  # key, e.g. prvCreateAccount
    level: str = "none"  # none | user | business_unit | parent_child | organization


class SecurityRole(DocgenModel):
    name: str  # key
    role_id: str | None = None
    description: str | None = None
    privileges: list[RolePrivilege] = Field(default_factory=list)


class FieldPermission(DocgenModel):
    entity: str = ""
    attribute: str = ""
    can_read: bool = False
    can_create: bool = False
    can_update: bool = False


class FieldSecurityProfile(DocgenModel):
    name: str  # key
    profile_id: str | None = None
    description: str | None = None
    attribute_permissions: list[FieldPermission] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Cloud flows
# ---------------------------------------------------------------------------


class FlowTrigger(DocgenModel):
    name: str = ""
    type: str = ""  # e.g. OpenApiConnectionWebhook, Request, Recurrence
    kind: str | None = None  # e.g. the operationId / trigger kind when present
    connector: str | None = None  # api name, e.g. shared_commondataserviceforapps


class FlowAction(DocgenModel):
    path: str  # key — slash-joined nesting path, e.g. "Scope_Try/Get_items"
    name: str = ""
    type: str = ""  # e.g. OpenApiConnection, Compose, If, Scope, Foreach
    connector: str | None = None
    operation_id: str | None = None
    run_after_statuses: list[str] = Field(default_factory=list)  # e.g. ["Succeeded"], ["Failed", "TimedOut"]


class CloudFlow(DocgenModel):
    unique_name: str  # key (workflow unique name / file stem)
    display_name: str | None = None
    description: str | None = None
    state: str | None = None  # Draft | Activated
    trigger: FlowTrigger | None = None
    actions: list[FlowAction] = Field(default_factory=list)
    connectors_used: list[str] = Field(default_factory=list)
    connection_reference_names: list[str] = Field(default_factory=list)
    has_error_scope: bool = False  # any action running after Failed/TimedOut


# ---------------------------------------------------------------------------
# Deployment configuration
# ---------------------------------------------------------------------------


class ConnectionReference(DocgenModel):
    logical_name: str  # key
    display_name: str | None = None
    connector_id: str | None = None  # full /providers/... id
    api_name: str | None = None  # derived short name, e.g. shared_sharepointonline


class EnvironmentVariable(DocgenModel):
    schema_name: str  # key
    display_name: str | None = None
    description: str | None = None
    type: str = ""  # string, number, boolean, json, secret, data source
    default_value: str | None = None
    current_value: str | None = None
    is_secret: bool = False


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------


class PluginAssembly(DocgenModel):
    name: str  # key
    version: str | None = None
    isolation_mode: str | None = None  # sandbox | none
    culture: str | None = None
    public_key_token: str | None = None


class PluginStep(DocgenModel):
    name: str  # key
    message: str | None = None  # Create, Update, Delete...
    primary_entity: str | None = None
    stage: str | None = None  # pre_validation | pre_operation | post_operation
    mode: str | None = None  # sync | async
    rank: int | None = None
    filtering_attributes: list[str] = Field(default_factory=list)
    assembly_name: str | None = None
    plugin_type_name: str | None = None
    state: str | None = None


# ---------------------------------------------------------------------------
# Inventory-level components
# ---------------------------------------------------------------------------


class WebResource(DocgenModel):
    name: str  # key
    display_name: str | None = None
    type: str = ""  # js, html, css, png, xml, silverlight...
    description: str | None = None


class CustomConnector(DocgenModel):
    name: str  # key
    display_name: str | None = None
    description: str | None = None


class CanvasApp(DocgenModel):
    name: str  # key
    display_name: str | None = None
    connections: list[str] = Field(default_factory=list)  # connector api names, inventory only


class GenericComponent(DocgenModel):
    """Catch-all for solution components docgen has no specialised parser for."""

    schema_name_or_id: str  # key
    component_type: int | None = None  # RootComponent type code where known
    type_label: str | None = None  # human label where the type code is recognised
    source: str = ""  # which file it came from
    raw_summary: dict[str, str] = Field(default_factory=dict)  # flat scalars only


# ---------------------------------------------------------------------------
# Solution metadata + snapshot root
# ---------------------------------------------------------------------------


class Publisher(DocgenModel):
    unique_name: str = ""
    display_name: str | None = None
    prefix: str | None = None
    option_value_prefix: int | None = None


class SolutionMeta(DocgenModel):
    unique_name: str = ""
    display_name: str | None = None
    version: str = ""
    managed: bool = False
    publisher: Publisher = Field(default_factory=Publisher)
    root_component_count: int = 0


class Snapshot(DocgenModel):
    schema_version: str = SCHEMA_VERSION
    generated_at: str = ""  # ISO 8601; zeroed in golden-test comparisons
    docgen_version: str = ""
    source_file: str = ""  # basename of the zip that was parsed
    solution: SolutionMeta = Field(default_factory=SolutionMeta)
    entities: list[Entity] = Field(default_factory=list)
    global_option_sets: list[OptionSet] = Field(default_factory=list)
    security_roles: list[SecurityRole] = Field(default_factory=list)
    field_security_profiles: list[FieldSecurityProfile] = Field(default_factory=list)
    cloud_flows: list[CloudFlow] = Field(default_factory=list)
    connection_references: list[ConnectionReference] = Field(default_factory=list)
    environment_variables: list[EnvironmentVariable] = Field(default_factory=list)
    plugin_assemblies: list[PluginAssembly] = Field(default_factory=list)
    plugin_steps: list[PluginStep] = Field(default_factory=list)
    web_resources: list[WebResource] = Field(default_factory=list)
    custom_connectors: list[CustomConnector] = Field(default_factory=list)
    canvas_apps: list[CanvasApp] = Field(default_factory=list)
    other_components: list[GenericComponent] = Field(default_factory=list)
    warnings: list[ParseWarning] = Field(default_factory=list)
