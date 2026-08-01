"""Milestone 4 parser assertions: flows, security, plugins, connections, inventory."""

from pathlib import Path

import pytest

from docgen.parsers import parse_solution


@pytest.fixture(scope="module")
def rich(built_fixtures):
    return parse_solution(built_fixtures / "rich.zip")


def test_cloud_flows(rich):
    flows = {f.display_name: f for f in rich.cloud_flows}
    assert set(flows) == {"Notify PM on project creation", "Sync invoices to SQL", "Broken flow"}

    notify = flows["Notify PM on project creation"]
    assert notify.trigger is not None
    assert notify.trigger.connector == "shared_commondataserviceforapps"
    assert notify.has_error_scope is True  # Catch_scope runs after Failed/TimedOut
    paths = {a.path for a in notify.actions}
    assert "Try_scope/Get_project_manager" in paths and "Catch_scope/Log_failure" in paths
    assert "shared_office365" in notify.connectors_used
    assert set(notify.connection_reference_names) == {"abc_dataverse", "abc_office365"}

    sync = flows["Sync invoices to SQL"]
    assert sync.has_error_scope is False
    assert "shared_sql" in sync.connectors_used

    broken = flows["Broken flow"]
    assert broken.actions == [] and broken.trigger is None
    assert any(w.code == "missing_flow_json" for w in rich.warnings)


def test_business_rules_attached(rich):
    project = next(e for e in rich.entities if e.logical_name == "abc_project")
    assert [b.name for b in project.business_rules] == ["Require budget when active"]
    assert project.business_rules[0].scope == "All Forms"


def test_security_roles(rich):
    roles = {r.name: r for r in rich.security_roles}
    assert set(roles) == {"Project Manager", "Project Member"}
    pm = roles["Project Manager"]
    create = next(p for p in pm.privileges if p.name == "prvCreateabc_project")
    assert create.level == "organization"
    delete = next(p for p in pm.privileges if p.name == "prvDeleteabc_project")
    assert delete.level == "business_unit"


def test_field_security_profiles(rich):
    profile = rich.field_security_profiles[0]
    assert profile.name == "HR Restricted"
    perm = profile.attribute_permissions[0]
    assert (perm.entity, perm.attribute) == ("abc_employee", "abc_salary")
    assert perm.can_read is True and perm.can_create is False


def test_connection_references_and_env_vars(rich):
    refs = {c.logical_name: c for c in rich.connection_references}
    assert refs["abc_sql"].api_name == "shared_sql"
    variables = {v.schema_name: v for v in rich.environment_variables}
    assert variables["abc_ApiKey"].is_secret is True
    assert variables["abc_ApiKey"].default_value is None
    assert variables["abc_BatchSize"].type == "number"
    assert variables["abc_BatchSize"].current_value == "100"


def test_plugins(rich):
    assembly = rich.plugin_assemblies[0]
    assert assembly.name == "Abc.Plugins"
    assert assembly.version == "1.2.0.0"
    assert assembly.isolation_mode == "sandbox"
    steps = {s.plugin_type_name: s for s in rich.plugin_steps}
    task_step = steps["Abc.Plugins.TaskUpdate"]
    assert task_step.stage == "pre_operation" and task_step.mode == "sync"
    assert task_step.filtering_attributes == ["abc_effort", "abc_priority"]


def test_inventory_components(rich):
    assert [w.type for w in rich.web_resources] == ["js", "css"]  # sorted by name: scripts/ < styles/
    app = rich.canvas_apps[0]
    assert app.connections == ["shared_commondataserviceforapps", "shared_sharepointonline"]
    assert rich.custom_connectors[0].name == "abc_financeapi"


def test_only_true_unknowns_remain_generic(rich):
    """After M4 every parsed family is claimed; only the mystery component remains."""
    assert [g.schema_name_or_id for g in rich.other_components] == ["abc_mystery_component"]
