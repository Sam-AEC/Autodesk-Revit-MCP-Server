"""revit_params module: manifest, tool metadata, approval gating, argument validation and the result contract.

Nothing here talks to Revit. The scripts run against a stub of the Revit API in test_revit_params_scripts.py.
Everything that needs a live Revit is UNVERIFIED (see the module docstring).
"""
from __future__ import annotations

import ast
import asyncio
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import human_approve  # noqa: E402
from revit_mcp_server.check_contract import parse_script_output  # noqa: E402
from revit_mcp_server.errors import BridgeError  # noqa: E402
from revit_mcp_server.module_registry import ModuleInstance, ModuleManifest  # noqa: E402
from revit_mcp_server.modules.revit_params import module as params  # noqa: E402
from revit_mcp_server.providers.module_provider import ModuleProvider  # noqa: E402
from revit_mcp_server.security.approval import ApprovalGate  # noqa: E402
from revit_mcp_server.security.dispatch import run_gated_tool  # noqa: E402
from revit_mcp_server.security.read_mode import validate_read_script  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402
from revit_mcp_server.tool_metadata import enrich_tool  # noqa: E402

SET, GET = "revit_set_parameters", "revit_get_parameters"
SET_ARGS: Dict[str, Any] = {"items": [{"id": 12, "params": {"Mark": "A-01", "Height": {"value": 2400, "unit": "mm"}}}]}
GET_ARGS: Dict[str, Any] = {"items": [{"selector": {"category": "Walls"}, "params": ["Mark"]}]}
WRITE_OK = (
    "SUMMARY\t2 parameter value(s) set on 1 element(s)\nMETA\toutcome\tok\nMETA\ton_error\tabort\nMETA\tchanged_ids\t12\n"
    "ROW\trow_type=post\tcheck=readback:12\tok=1\tdetail=2 value(s) read back as written\n"
    "ROW\trow_type=item\tkind=param\tid=12\telement_id=12\tscope=instance\tparam=Mark\tstorage=String\tunit=text\told=\tnew=A-01\t"
    "read_back=A-01\told_raw=\tnew_raw=A-01\tstatus=set\treason=\n"
    "ROW\trow_type=item\tkind=param\tid=12\telement_id=12\tscope=instance\tparam=Height\tstorage=Double\tunit=mm\told=3000.0\t"
    "new=2400.0\tread_back=2400.0\told_raw=9.84251968503937\tnew_raw=7.874015748031496\tstatus=set\treason=\n"
    "COUNT\tfail\t0\nCOUNT\trow\t3"
)
READ_OK = "SUMMARY\t1 element(s) read\nROW\tkind=param\tid=12\telement_id=12\tparam=Mark\tvalue=A\tread_only=0\twritable=1\nCOUNT\tfail\t0\nCOUNT\trow\t1"


class FakeRevit:
    def __init__(self, write_output: str = WRITE_OK, read_output: str = READ_OK) -> None:
        self.write_output, self.read_output = write_output, read_output
        self.calls: List[tuple] = []

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return {"success": True, "output": self.read_output if arguments.get("mode") == "read" else self.write_output}

    def call_is_read_only(self, name: str, arguments: Dict[str, Any]) -> bool:
        return arguments.get("mode") == "read"


def manifest() -> Dict[str, Any]:
    return json.loads((params.MODULE_DIR / "module.json").read_text(encoding="utf-8"))


def wire(tmp_path, monkeypatch, mode="ask_first", revit=None):
    inst = ModuleInstance(ModuleManifest(**manifest()), params.MODULE_DIR)
    monkeypatch.setattr(inst.code_module, "_server_in_mock_mode", lambda: False)
    modules = SimpleNamespace(get_all_modules=lambda: [inst], config=SimpleNamespace(allow_python_host=False))
    gate = ApprovalGate(tmp_path, mode)
    revit = revit or FakeRevit()
    provider = ModuleProvider(modules, WorkspaceMonitor([tmp_path]))
    capabilities = {tool.name: tool for tool in provider.get_capabilities()}
    capabilities["revit_execute_python"] = SimpleNamespace(is_mutating=True)
    registry = SimpleNamespace(
        lookup_tool=lambda name: capabilities.get(name),
        lookup_tool_provider=lambda name: provider if name in capabilities and name != "revit_execute_python" else revit,
        get_provider=lambda name: SimpleNamespace(gate=gate) if name == "approval" else None,
    )
    provider.tool_registry = registry
    return provider, gate, registry, revit


def approved(gate, tool, arguments):
    plan = gate.create_plan([{"tool": tool, "arguments": arguments}], [{}])
    human_approve(gate, plan["plan_id"])
    return plan["plan_id"]


@pytest.fixture()
def module(monkeypatch):
    monkeypatch.setattr(params, "_server_in_mock_mode", lambda: False)
    return params.RevitParamsModule()


class Canned:
    def __init__(self, write: str = WRITE_OK, read: str = READ_OK) -> None:
        self.write, self.read = write, read
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        self.calls.append(args)
        return {"success": True, "output": self.read if args["mode"] == "read" else self.write}


# --------------------------------------------------------------------------- #
# Manifest and tool metadata
# --------------------------------------------------------------------------- #
def test_public_tool_names_and_gate_flags(tmp_path, monkeypatch):
    provider, *_ = wire(tmp_path, monkeypatch)
    tools = {t.name: t for t in provider.get_capabilities()}
    assert tools[SET].is_mutating is True and tools[GET].is_mutating is False
    commands = {c["mcp_tool"]: c for c in manifest()["commands"]}
    assert commands[SET]["requires_plan"] is True and commands[SET]["destructive"] is False
    assert "requires_plan" not in commands[GET]


def _undocumented(schema: Any, path: str = "root") -> List[str]:
    missing: List[str] = []
    if isinstance(schema, dict):
        for key, prop in (schema.get("properties") or {}).items():
            if not isinstance(prop, dict) or not prop.get("description"):
                missing.append(f"{path}.{key}")
            missing.extend(_undocumented(prop, f"{path}.{key}"))
        for sub in ("items", "additionalProperties"):
            if isinstance(schema.get(sub), dict):
                missing.extend(_undocumented(schema[sub], f"{path}[{sub}]"))
    return missing


def test_every_parameter_is_documented_and_descriptions_name_the_sibling():
    data = manifest()
    assert len(data["description"]) < 900
    for cmd in data["commands"]:
        assert _undocumented(cmd["input_schema"], cmd["mcp_tool"]) == []
        assert 80 < len(cmd["title"]) < 700, cmd["mcp_tool"]
    titles = {c["mcp_tool"]: c["title"] for c in data["commands"]}
    assert GET in titles[SET] and SET in titles[GET]
    assert "never creates parameters" in titles[SET].lower()


def test_tool_metadata_marks_the_write_tool_gated_and_the_read_tool_read_only(tmp_path, monkeypatch):
    provider, *_ = wire(tmp_path, monkeypatch)
    for tool in provider.get_capabilities():
        if tool.name not in (SET, GET):
            continue
        enriched = enrich_tool("module", tool)
        if tool.name == SET:
            assert enriched.annotations.readOnlyHint is False and "plan_id" in enriched.inputSchema["properties"]
        else:
            assert enriched.annotations.readOnlyHint is True and "plan_id" not in enriched.inputSchema["properties"]


def test_module_files_have_no_conflict_markers():
    for path in sorted(params.MODULE_DIR.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json", ".ipy"}:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                assert not re.match(r"^(<{7}|={7}|>{7})( |$)", line), f"{path.name}:{number}"


def test_scripts_are_python27_safe_and_the_read_script_stays_read_only():
    for path in sorted(params.SCRIPT_DIR.glob("*.ipy")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            assert not isinstance(node, (ast.JoinedStr, ast.AnnAssign, ast.NamedExpr)), f"{path.name}: f-string, annotation or walrus"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.returns is None and all(a.annotation is None for a in node.args.args), f"{path.name}: type hint"
    nasty = {"items": [{"ids": [1], "params": {"x'\nraise Exception('oops')": {"value": "y", "unit": "text"}}}]}
    for name in params.SCRIPTS:
        compile(params.build_script(name, nasty), name, "exec")
    validate_read_script(params.build_script("get_parameters.ipy", {"items": []}))
    assert "class Runner" not in params.build_script("get_parameters.ipy", {"items": []})


# --------------------------------------------------------------------------- #
# Approval gating
# --------------------------------------------------------------------------- #
def test_the_write_tool_refuses_without_a_plan_id(tmp_path, monkeypatch):
    provider, gate, registry, revit = wire(tmp_path, monkeypatch)
    with pytest.raises(BridgeError, match="plan_id"):
        asyncio.run(run_gated_tool(registry, gate, SET, json.loads(json.dumps(SET_ARGS))))
    with pytest.raises(BridgeError, match="plan_id"):
        asyncio.run(run_gated_tool(registry, gate, SET, {**json.loads(json.dumps(SET_ARGS)), "dry_run": True}))
    assert revit.calls == []


def test_the_write_tool_refuses_a_plan_that_is_not_approved(tmp_path, monkeypatch):
    provider, gate, registry, revit = wire(tmp_path, monkeypatch)
    plan = gate.create_plan([{"tool": SET, "arguments": SET_ARGS}], [{}])
    with pytest.raises(BridgeError, match="pending"):
        asyncio.run(run_gated_tool(registry, gate, SET, {**SET_ARGS, "plan_id": plan["plan_id"]}))
    assert revit.calls == []


def test_the_read_tool_runs_without_a_plan_in_read_mode(tmp_path, monkeypatch):
    provider, gate, registry, revit = wire(tmp_path, monkeypatch)
    result = asyncio.run(run_gated_tool(registry, gate, GET, json.loads(json.dumps(GET_ARGS))))
    assert result["ok"] is True and result["truncated"] is False
    assert [c[1]["mode"] for c in revit.calls] == ["read"]
    validate_read_script(revit.calls[0][1]["script"])


def test_an_approved_plan_runs_the_write_script_once(tmp_path, monkeypatch):
    provider, gate, registry, revit = wire(tmp_path, monkeypatch)
    pid = approved(gate, SET, SET_ARGS)
    result = asyncio.run(run_gated_tool(registry, gate, SET, {**SET_ARGS, "plan_id": pid}))
    assert result["ok"] is True, result
    assert [c[1]["mode"] for c in revit.calls] == ["write"]
    assert gate.load_plan(pid)["actions"][0]["state"] == "executed"
    with pytest.raises(BridgeError):
        asyncio.run(run_gated_tool(registry, gate, SET, {**SET_ARGS, "plan_id": pid}))


# --------------------------------------------------------------------------- #
# Argument validation (nothing is sent to Revit)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("items,needle", [
    (None, "items must be a list"),
    ([{"params": {"Mark": "A"}}], "exactly one of id, ids or selector"),
    ([{"id": 1, "ids": [2], "params": {"Mark": "A"}}], "exactly one of id, ids or selector"),
    ([{"selector": {"name": "Basic"}, "params": {"Mark": "A"}}], "needs a category or a tag"),
    ([{"selector": {"category": "Walls", "colour": "red"}, "params": {"Mark": "A"}}], "selector must be an object"),
    ([{"id": 1, "params": {}}], "1 to 50 parameter names"),
    ([{"id": 1, "params": {"H": {"value": 2, "unit": "inch"}}}], "unit must be one of"),
    ([{"id": 1, "params": {"H": {"value": "tall", "unit": "mm"}}}], "finite number"),
    ([{"id": 1, "params": {"H": 2.5}}], "give a unit"),
    ([{"id": 1, "params": {"H": {"value": 1, "unit": "bool"}}}], "true or false"),
    ([{"id": 1, "params": {"H": {"value": 0, "unit": "elementid"}}}], "element name or a positive integer id"),
    ([{"id": 1, "params": {"H": [1, 2]}}], "number, true/false or text"),
    ([{"id": 1, "scope": "family", "params": {"H": 1}}], "scope must be one of"),
    ([{"id": 1, "params": {"H": 1}, "extra": 1}], "unknown keys"),
    ([{"ids": list(range(1, 400)), "params": {"H": 1}}, {"ids": list(range(400, 600)), "params": {"H": 1}}], "at most 500 elements"),
])
def test_bad_set_arguments_never_reach_revit(module, items, needle):
    ex = Canned()
    result = module.set_parameters(items=items, approved_executor=ex, workspace=None)
    assert result["ok"] is False and result["kind"] == "invalid_input" and needle in result["message"], result
    assert ex.calls == []


def test_bad_flags_and_read_arguments_never_reach_revit(module):
    ex = Canned()
    assert module.set_parameters(items=SET_ARGS["items"], dry_run="yes", approved_executor=ex)["kind"] == "invalid_input"
    assert module.set_parameters(items=SET_ARGS["items"], on_error="ignore", approved_executor=ex)["kind"] == "invalid_input"
    assert module.get_parameters(items=GET_ARGS["items"], max_elements=5000, tool_executor=ex)["kind"] == "invalid_input"
    assert module.get_parameters(items=GET_ARGS["items"], time_budget_s=60, tool_executor=ex)["kind"] == "invalid_input"
    assert module.get_parameters(items=[{"id": 1, "params": "Mark"}], tool_executor=ex)["kind"] == "invalid_input"
    assert ex.calls == []


def test_values_and_units_reach_the_script_as_checked_literals(module):
    ex = Canned()
    module.set_parameters(items=[{"selector": {"category": "Walls", "level": "L0"}, "scope": "type", "params": {
        "Mark": "A", "Fire": True, "Count": 3.0, "H": {"value": 2400, "unit": "mm"}, "Mat": {"value": "Brick", "unit": "elementid"}}}],
        approved_executor=ex)
    script = ex.calls[0]["script"]
    assert ex.calls[0]["mode"] == "write"
    assert "u'Fire': {u'value': True, u'unit': u'bool'}" in script
    assert "u'Count': {u'value': 3, u'unit': u''}" in script
    assert "u'H': {u'value': 2400.0, u'unit': u'mm'}" in script
    assert "u'scope': u'type'" in script and "'dry_run': False" in script


# --------------------------------------------------------------------------- #
# The result contract
# --------------------------------------------------------------------------- #
def test_a_good_result_lists_old_new_and_a_revert(module):
    result = module.set_parameters(items=SET_ARGS["items"], approved_executor=Canned())
    assert result["ok"] is True and result["changed_ids"] == [12] and result["values"] == {"set": 2}
    revert = result["revert"]["items"]
    assert revert == [{"id": 12, "scope": "instance", "params": {"Mark": {"value": "", "unit": "text"},
                                                                 "Height": {"value": pytest.approx(3000.0), "unit": "mm"}}}]


def test_a_refused_call_is_never_ok():
    out = ("SUMMARY\tx\nFAIL\tPARAMETER_REFUSED\t1 element(s) cannot be written\nMETA\toutcome\tparameter_refused\nMETA\tchanged_ids\t\n"
           "META\tfailed_ids\t12\nROW\trow_type=item\tkind=param\tid=12\tstatus=refused\treason=read-only\nCOUNT\tfail\t1")
    result = params._finish_write(SET, parse_script_output(out), 1, None)
    assert result["ok"] is False and result["kind"] == "parameter_refused" and result["element_ids"] == [12]
    assert result["revert"]["items"] == [] and "Nothing was changed" in result["summary"]


def test_a_failed_read_back_is_never_ok():
    out = ("SUMMARY\tx\nMETA\toutcome\tok\nMETA\tchanged_ids\t12\nROW\trow_type=post\tcheck=readback:12\tok=0\tdetail=bad\nCOUNT\tfail\t0")
    result = params._finish_write(SET, parse_script_output(out), 1, None)
    assert result["ok"] is False and result["kind"] == "post_check_failed"


def test_mock_mode_is_unverified(monkeypatch):
    monkeypatch.setattr(params, "_server_in_mock_mode", lambda: True)
    m = params.RevitParamsModule()
    assert m.get_parameters(items=GET_ARGS["items"], tool_executor=Canned())["verified"] is False
    result = m.set_parameters(items=SET_ARGS["items"], approved_executor=Canned())
    assert result["verified"] is False and result["post_check"]["ok"] is None
