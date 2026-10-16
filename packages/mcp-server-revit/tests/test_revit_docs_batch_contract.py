"""Manifest, schema strictness, approval gate and script-source rules of the revit_docs documentation batch."""
from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Dict, List

import pytest

from helpers import human_approve  # noqa: F401 - used through test_revit_docs.approved
from revit_mcp_server.errors import BridgeError
from revit_mcp_server.modules.revit_docs import module as docs
from revit_mcp_server.security.dispatch import run_gated_tool
from revit_mcp_server.security.read_mode import validate_read_script
from test_revit_checks import py2_problems
from test_revit_docs import approved, wire

WRITE = {
    "revit_place_views": "place_views",
    "revit_set_view_templates": "apply_view_template",
    "revit_make_view_template": "make_view_template",
    "revit_align_crop": "align_crop",
    "revit_add_revision": "add_revision",
    "revit_add_revision_clouds": "add_revision_clouds",
    "revit_issue_revision": "issue_revision",
    "revit_update_sheets": "update_sheets",
}
READ = {
    "revit_list_view_templates": "list_view_templates",
    "revit_list_revisions": "list_revisions",
    "revit_sheet_index": "sheet_index",
}
SAMPLE: Dict[str, Dict[str, Any]] = {
    "revit_place_views": {"sheet": "A101", "views": [{"view_id": 1}]},
    "revit_set_view_templates": {"template": "T", "views": [{"view_id": 1}]},
    "revit_make_view_template": {"view": {"view_id": 1}, "name": "T"},
    "revit_align_crop": {"reference": {"view_id": 1}, "views": [{"view_id": 2}]},
    "revit_add_revision": {"description": "R"},
    "revit_add_revision_clouds": {"revision_number": "1", "view": {"view_id": 1}, "element_ids": [5]},
    "revit_issue_revision": {"revision_number": "1", "issue": True},
    "revit_update_sheets": {"sheets": [{"number": "A1", "new_name": "x"}]},
    "revit_list_view_templates": {},
    "revit_list_revisions": {},
    "revit_sheet_index": {},
}
NEW = {**WRITE, **READ}


def manifest() -> Dict[str, Any]:
    return json.loads((docs.MODULE_DIR / "module.json").read_text(encoding="utf-8"))


def commands() -> Dict[str, Dict[str, Any]]:
    return {c["mcp_tool"]: c for c in manifest()["commands"]}


def test_every_new_command_is_in_the_manifest_with_the_right_gate_flags():
    cmds = commands()
    for tool, method in NEW.items():
        assert cmds[tool]["id"] == method and hasattr(docs.RevitDocsModule, method)
        assert 150 < len(cmds[tool]["title"]) < 900, tool
    for tool in WRITE:
        assert cmds[tool]["is_mutating"] is True and cmds[tool]["requires_plan"] is True and cmds[tool]["destructive"] is False, tool
        assert cmds[tool]["input_schema"]["properties"]["dry_run"]["default"] is False
        assert "approved plan" in cmds[tool]["input_schema"]["properties"]["dry_run"]["description"]
    for tool in READ:
        assert cmds[tool]["is_mutating"] is False and "requires_plan" not in cmds[tool], tool
        assert "dry_run" not in cmds[tool]["input_schema"]["properties"] and "Read-only" in cmds[tool]["title"]
    assert len(manifest()["description"]) < 1200


def _strict(schema: Dict[str, Any], path: str) -> List[str]:
    problems: List[str] = []
    kind = schema.get("type")
    if kind == "object":
        if schema.get("additionalProperties") is not False:
            problems.append(f"{path}: object without additionalProperties false")
        for name, prop in (schema.get("properties") or {}).items():
            if not prop.get("description"):
                problems.append(f"{path}.{name}: no description")
            problems += _strict(prop, f"{path}.{name}")
        for req in schema.get("required", []):
            if req not in schema.get("properties", {}):
                problems.append(f"{path}: required {req} is not a property")
    elif kind == "array":
        if "maxItems" not in schema:
            problems.append(f"{path}: array without maxItems")
        problems += _strict(schema.get("items") or {"type": "?"}, f"{path}[]")
    elif kind == "string":
        if "enum" not in schema and "maxLength" not in schema:
            problems.append(f"{path}: string without maxLength or enum")
    elif kind in ("integer", "number"):
        if "minimum" not in schema:
            problems.append(f"{path}: number without minimum")
    elif kind != "boolean":
        problems.append(f"{path}: unknown or missing type {kind!r}")
    return problems


@pytest.mark.parametrize("tool", sorted(NEW))
def test_new_input_schemas_are_strict_and_match_the_method_parameters(tool):
    schema = commands()[tool]["input_schema"]
    assert _strict(schema, tool) == []
    params = set(inspect.signature(getattr(docs.RevitDocsModule, NEW[tool])).parameters)
    assert set(schema["properties"]) <= params, set(schema["properties"]) - params
    # the plumbing parameters are the only method parameters the schema does not offer
    assert params - set(schema["properties"]) <= {"self", "arguments", "workspace", "tool_executor", "approved_executor", "_"}


@pytest.mark.parametrize("tool", sorted(NEW))
def test_a_misspelt_argument_is_refused_not_ignored(tool):
    args = {**SAMPLE[tool], "dryrun": True}
    result = getattr(docs.RevitDocsModule(), NEW[tool])(arguments=args, **args)
    assert result["ok"] is False and result["kind"] == "invalid_input" and "dryrun" in result["message"]


@pytest.mark.parametrize("tool,args,text", [
    ("revit_place_views", {"sheet": "A1", "views": []}, "1 to 60"),
    ("revit_place_views", {"sheet": "A1", "views": [{"view_id": 1, "view_name": "x"}]}, "exactly one"),
    ("revit_place_views", {"sheet": "A1", "views": [{"view_id": 1, "x_mm": 5}]}, "both x_mm and y_mm"),
    ("revit_place_views", {"sheet": "A1", "views": [{"view_id": 1, "color": "red"}]}, "unknown field"),
    ("revit_place_views", {"sheet": "A1", "views": [{"view_id": 1}], "layout": "row", "columns": 2}, "only goes with layout grid"),
    ("revit_place_views", {"sheet": "A1", "views": [{"view_id": 1}], "margin_mm": 900}, "between 0 and 300"),
    ("revit_place_views", {"sheet": "A1", "views": [{"view_id": 1}], "dry_run": "false"}, "true or false"),
    ("revit_set_view_templates", {"views": [{"view_id": 1}]}, "exactly one of template"),
    ("revit_set_view_templates", {"template": "T", "template_id": 4, "views": [{"view_id": 1}]}, "exactly one of template"),
    ("revit_set_view_templates", {"template": "T", "views": [{"view_id": 0}]}, "positive"),
    ("revit_make_view_template", {"view": {}, "name": "T"}, "exactly one"),
    ("revit_make_view_template", {"view": {"view_id": 1}, "name": "T:x"}, "does not allow"),
    ("revit_align_crop", {"reference": {"view_id": 1}, "views": [{"view_id": 2}], "align_crop_box": False}, "nothing to do"),
    ("revit_align_crop", {"reference": {"view_id": 1}, "views": [{"view_id": 2}], "annotation_crop": "sometimes"}, "one of"),
    ("revit_add_revision", {"description": "   "}, "required"),
    ("revit_add_revision", {"description": "x", "visibility": "loud"}, "one of"),
    ("revit_add_revision_clouds", {"view": {"view_id": 1}, "element_ids": [5]}, "exactly one of revision_id"),
    ("revit_add_revision_clouds", {"revision_id": 3, "revision_number": "1", "view": {"view_id": 1}, "element_ids": [5]}, "exactly one of revision_id"),
    ("revit_add_revision_clouds", {"revision_id": 3, "view": {"view_id": 1}}, "element_ids and/or bbox_m"),
    ("revit_add_revision_clouds", {"revision_id": 3, "view": {"view_id": 1}, "bbox_m": {"min": [0, 0, 0], "max": [-1, 1, 1]}}, "below"),
    ("revit_add_revision_clouds", {"revision_id": 3, "view": {"view_id": 1}, "element_ids": [0]}, "positive"),
    ("revit_issue_revision", {"revision_id": 3}, "nothing to do"),
    ("revit_issue_revision", {"revision_id": 3, "sheets": ["A1"], "issued_by": "me"}, "only go with issue true"),
    ("revit_update_sheets", {"sheets": []}, "1 to 200"),
    ("revit_update_sheets", {"sheets": [{"number": "A1", "new_number": "A2"}], "on_error": "maybe"}, "one of"),
])
def test_bad_input_is_refused_before_anything_is_sent_to_revit(tool, args, text):
    calls: List[Any] = []

    def executor(name, arguments):
        calls.append(name)
        return {}

    result = getattr(docs.RevitDocsModule(), NEW[tool])(approved_executor=executor, tool_executor=executor, **args)
    assert result["ok"] is False and result["kind"] == "invalid_input" and text in result["message"], result
    assert calls == []


@pytest.mark.parametrize("tool", sorted(WRITE))
def test_a_write_tool_needs_an_approved_plan_and_uses_one_vetted_nested_call(tool, tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch)
    args = SAMPLE[tool]
    with pytest.raises(Exception, match="(?i)plan|approv"):
        asyncio.run(run_gated_tool(registry, gate, tool, dict(args)))
    assert not revit.calls
    pid = approved(gate, tool, args)
    result = asyncio.run(run_gated_tool(registry, gate, tool, {**args, "plan_id": pid}))
    assert result["ok"] is True, result
    assert len(revit.calls) == 1 and revit.calls[0][0] == "revit_execute_python" and revit.calls[0][1]["mode"] == "write"
    assert gate.load_plan(pid)["actions"][0]["state"] == "executed"


@pytest.mark.parametrize("tool", sorted(WRITE))
def test_a_typo_through_the_real_provider_never_reaches_revit(tool, tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch)
    args = {**SAMPLE[tool], "dryrun": True}
    pid = approved(gate, tool, args)
    try:
        result = asyncio.run(run_gated_tool(registry, gate, tool, {**args, "plan_id": pid}))
    except BridgeError as exc:  # the schema check of the provider may refuse first
        result = {"ok": False, "message": str(exc)}
    assert result["ok"] is False and not revit.calls


@pytest.mark.parametrize("tool", sorted(READ))
def test_read_tools_run_in_read_mode_without_a_plan(tool, tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch, raw={"success": True, "output": "SUMMARY\tok\nCOUNT\tfail\t0\nCOUNT\tinfo\t0\nCOUNT\trow\t0"})
    result = asyncio.run(run_gated_tool(registry, gate, tool, dict(SAMPLE[tool])))
    assert result["ok"] is True, result
    assert len(revit.calls) == 1 and revit.calls[0][1]["mode"] == "read"
    validate_read_script(revit.calls[0][1]["script"])


@pytest.mark.parametrize("script", sorted(docs.USES_COMMON))
def test_every_new_script_is_ascii_and_ironpython_2_safe(script):
    text = docs.build_script(script, {"x": "a'b\nc"}, write=script.removesuffix(".ipy") in set(WRITE.values()))
    text.encode("ascii")
    compile(text, script, "exec")
    assert py2_problems(text) == [], script


def test_the_shared_helper_file_is_ascii_py2_safe_and_read_mode_clean():
    text = (docs.SCRIPT_DIR / docs.DOCS_COMMON).read_text(encoding="utf-8")
    text.encode("ascii")
    validate_read_script(text)
    assert py2_problems("from Autodesk.Revit.DB import *\n" + text) == []


def test_read_scripts_pass_the_read_mode_check_and_write_scripts_do_not():
    for script in ("list_view_templates.ipy", "list_revisions.ipy", "sheet_index.ipy"):
        validate_read_script(docs.build_script(script, {}, write=False))
    with pytest.raises(Exception):
        validate_read_script(docs.build_script("place_views.ipy", {}, write=True))
