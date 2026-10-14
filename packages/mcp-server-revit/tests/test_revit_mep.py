"""revit_mep module: manifest, tool metadata, approval gating, argument validation and the result contract.

Nothing here talks to Revit. The scripts themselves are exercised against a stub of the Revit API in
test_revit_mep_scripts.py. Everything that needs a live Revit is UNVERIFIED (see the module docstring).
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
from revit_mcp_server.modules.revit_mep import module as mep  # noqa: E402
from revit_mcp_server.providers.base import ProviderTool  # noqa: E402
from revit_mcp_server.providers.module_provider import ModuleProvider  # noqa: E402
from revit_mcp_server.security.approval import ApprovalGate  # noqa: E402
from revit_mcp_server.security.dispatch import run_gated_tool  # noqa: E402
from revit_mcp_server.security.read_mode import validate_read_script  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402
from revit_mcp_server.tool_metadata import enrich_tool  # noqa: E402

MUTATING = ("revit_mep_route", "revit_mep_connect", "revit_mep_circuit")
READ_ONLY = ("revit_mep_check_elements",)

WRITE_OK = (
    "SUMMARY\t1 of 1 routes built\nMETA\toutcome\tok\nMETA\ton_error\tabort\nMETA\tchanged_ids\t12,13\nMETA\treport_ids\t12,13\nMETA\tfree_end_ids\t\n"
    "ROW\trow_type=post\tcheck=route r1: pieces exist\tok=1\tdetail=2 pieces\n"
    "ROW\trow_type=item\tkind=pipe\tid=12\troute=r1\tsize=dia 32 mm\tlength_mm=1500.0\nCOUNT\tfail\t0"
)
REPORT_CLEAN = "SUMMARY\t1 systems, 0 open ends\nINFO\tSYS_UNASSIGNED\t2 members belong to no system\nCOUNT\tfail\t0\nCOUNT\tinfo\t1"

ROUTE_ARGS: Dict[str, Any] = {
    "kind": "pipe", "tag": "MEP1", "system": "hsup", "type_name": "PEX",
    "routes": [{"id": "r1", "level": "L0", "run_height_m": 0.08, "size": {"diameter_mm": 32},
                "from": {"mark": "HP", "sort": "y"}, "to": {"mark": "MAN", "diameter_mm": [30, 34]}}],
}
CONNECT_ARGS: Dict[str, Any] = {
    "kind": "pipe", "tag": "MEP1", "system": "hsup",
    "connections": [{"id": "c1", "a": {"mark": "HP"}, "b": {"element_id": 77}}],
}
CIRCUIT_ARGS: Dict[str, Any] = {
    "tag": "MEP1", "circuits": [{"id": "C1", "name": "C1 Lighting", "panel": {"mark": "PANEL"}, "elements": [{"mark": "LT1"}]}],
}
CHECK_ARGS: Dict[str, Any] = {"kind": "pipe", "system": "hsup", "elements": [{"mark": "HP"}]}
ARGS_OF = {"revit_mep_route": ROUTE_ARGS, "revit_mep_connect": CONNECT_ARGS, "revit_mep_circuit": CIRCUIT_ARGS,
           "revit_mep_check_elements": CHECK_ARGS}


# --------------------------------------------------------------------------- #
# Wiring: the real ModuleProvider + approval gate, with a fake Revit behind revit_execute_python
# --------------------------------------------------------------------------- #
class FakeRevit:
    """Answers revit_execute_python: a write script gets the write output, a read script the system_report output."""

    def __init__(self, write_output: str = WRITE_OK, read_output: str = REPORT_CLEAN) -> None:
        self.write_output, self.read_output = write_output, read_output
        self.calls: List[tuple] = []

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        out = self.read_output if arguments.get("mode") == "read" else self.write_output
        return {"success": True, "output": out}

    def call_is_read_only(self, name: str, arguments: Dict[str, Any]) -> bool:
        return arguments.get("mode") == "read"


def wire(tmp_path, monkeypatch, mode="ask_first", revit=None):
    manifest = ModuleManifest(**json.loads((mep.MODULE_DIR / "module.json").read_text(encoding="utf-8")))
    inst = ModuleInstance(manifest, mep.MODULE_DIR)
    monkeypatch.setattr(inst.code_module, "_server_in_mock_mode", lambda: False)
    rev_module = sys.modules[inst.code_module._revit_module_class().__module__]
    monkeypatch.setattr(rev_module, "_server_in_mock_mode", lambda: False)
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
    return provider, gate, registry, revit, inst


def approved(gate, tool, arguments):
    plan = gate.create_plan([{"tool": tool, "arguments": arguments}], [{}])
    human_approve(gate, plan["plan_id"])
    return plan["plan_id"]


@pytest.fixture()
def module(monkeypatch):
    monkeypatch.setattr(mep, "_server_in_mock_mode", lambda: False)
    rev_module = sys.modules[mep._revit_module_class().__module__]
    monkeypatch.setattr(rev_module, "_server_in_mock_mode", lambda: False)
    return mep.RevitMepModule()


class Canned:
    """A tool executor that answers write and read scripts with fixed output and records the calls."""

    def __init__(self, write: str = WRITE_OK, read: str = REPORT_CLEAN, read_exc: Exception | None = None) -> None:
        self.write, self.read, self.read_exc = write, read, read_exc
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        self.calls.append(args)
        if args["mode"] == "read":
            if self.read_exc is not None:
                raise self.read_exc
            return {"success": True, "output": self.read}
        return {"success": True, "output": self.write}


def call(module, tool: str, ex: Any, args: Dict[str, Any] | None = None, **extra: Any) -> Dict[str, Any]:
    method = {"revit_mep_route": module.route, "revit_mep_connect": module.connect, "revit_mep_circuit": module.circuit,
              "revit_mep_check_elements": module.check_elements}[tool]
    kwargs = dict(args or ARGS_OF[tool])
    kwargs.update(extra)
    if tool in MUTATING:
        return method(approved_executor=ex, workspace=WorkspaceMonitor([Path(".")]), **kwargs)
    return method(tool_executor=ex, workspace=WorkspaceMonitor([Path(".")]), **kwargs)


# --------------------------------------------------------------------------- #
# Manifest and tool metadata
# --------------------------------------------------------------------------- #
def manifest() -> Dict[str, Any]:
    return json.loads((mep.MODULE_DIR / "module.json").read_text(encoding="utf-8"))


def test_public_tool_names_and_gate_flags(tmp_path, monkeypatch):
    provider, *_ = wire(tmp_path, monkeypatch)
    tools = {t.name: t for t in provider.get_capabilities()}
    assert set(MUTATING + READ_ONLY) <= set(tools)
    assert not any(n.startswith("revit_mep_mep") or n.startswith("revit_mep_revit") for n in tools)
    for name in MUTATING:
        assert tools[name].is_mutating is True
    for name in READ_ONLY:
        assert tools[name].is_mutating is False
    commands = {c["mcp_tool"]: c for c in manifest()["commands"]}
    for name in MUTATING:
        assert commands[name]["requires_plan"] is True and commands[name]["destructive"] is False


def _undocumented(schema: Any, path: str = "root") -> List[str]:
    """Every property of the input schema, nested ones included, needs a description."""
    missing: List[str] = []
    if isinstance(schema, dict):
        for key, prop in (schema.get("properties") or {}).items():
            if not isinstance(prop, dict) or not prop.get("description"):
                missing.append(f"{path}.{key}")
            missing.extend(_undocumented(prop, f"{path}.{key}"))
        if isinstance(schema.get("items"), dict):
            missing.extend(_undocumented(schema["items"], path + "[]"))
    return missing


def test_every_parameter_is_documented_and_descriptions_are_short():
    data = manifest()
    assert len(data["description"]) < 900
    for cmd in data["commands"]:
        assert _undocumented(cmd["input_schema"], cmd["mcp_tool"]) == []
        assert 80 < len(cmd["title"]) < 520, cmd["mcp_tool"]
        for prop in cmd["input_schema"]["properties"].values():
            assert len(prop["description"]) < 700
        # the description says when to use a sibling instead
        assert "revit_" in cmd["title"]


def test_descriptions_name_the_sibling_tools():
    titles = {c["mcp_tool"]: c["title"] for c in manifest()["commands"]}
    assert "revit_mep_connect" in titles["revit_mep_route"]
    assert "revit_mep_route" in titles["revit_mep_connect"]
    assert "revit_probe_family" in titles["revit_mep_check_elements"]


def test_tool_metadata_marks_write_tools_gated_and_the_check_read_only(tmp_path, monkeypatch):
    provider, *_ = wire(tmp_path, monkeypatch)
    for tool in provider.get_capabilities():
        if not tool.name.startswith("revit_mep_"):
            continue
        assert isinstance(tool, ProviderTool)
        enriched = enrich_tool("module", tool)
        if tool.name in MUTATING:
            assert enriched.annotations.readOnlyHint is False
            assert "plan_id" in enriched.description
            assert "plan_id" in enriched.inputSchema["properties"]
        else:
            assert enriched.annotations.readOnlyHint is True
            assert "plan_id" not in enriched.inputSchema["properties"]
        assert enriched.annotations.destructiveHint is False or tool.name in MUTATING


def test_module_files_have_no_conflict_markers():
    for path in sorted(mep.MODULE_DIR.rglob("*")):
        if path.is_file() and path.suffix in {".py", ".json", ".ipy"}:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                assert not re.match(r"^(<{7}|={7}|>{7})( |$)", line), f"{path.name}:{number}"


def test_scripts_are_python27_safe_and_the_read_script_stays_read_only():
    scripts = sorted(mep.SCRIPT_DIR.glob("*.ipy"))
    assert {p.name for p in scripts} >= {"route.ipy", "connect.ipy", "circuit.ipy", "check_elements.ipy", "_mep_guard.ipy", "_mep_write.ipy"}
    for path in scripts:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            assert not isinstance(node, (ast.JoinedStr, ast.AnnAssign, ast.NamedExpr)), f"{path.name}: f-string, annotation or walrus"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.returns is None and all(a.annotation is None for a in node.args.args), f"{path.name}: type hint"
    for name, (write, _) in mep.SCRIPTS.items():
        compile(mep.build_script(name, {"kind": "pipe", "tag": "x'\nraise Exception('oops')"}), name, "exec")
        if not write:
            validate_read_script(mep.build_script(name, {"kind": "pipe", "elements": []}))
    # the shared guard file must be usable from a read script
    validate_read_script((mep.SCRIPT_DIR / "_mep_guard.ipy").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Approval gating
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tool", MUTATING)
def test_mutating_tools_refuse_without_a_plan_id(tmp_path, monkeypatch, tool):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch)
    with pytest.raises(BridgeError, match="plan_id"):
        asyncio.run(run_gated_tool(registry, gate, tool, dict(ARGS_OF[tool])))
    assert revit.calls == []


@pytest.mark.parametrize("tool", MUTATING)
def test_mutating_tools_refuse_a_plan_that_is_not_approved(tmp_path, monkeypatch, tool):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch)
    plan = gate.create_plan([{"tool": tool, "arguments": dict(ARGS_OF[tool])}], [{}])
    with pytest.raises(BridgeError, match="pending"):
        asyncio.run(run_gated_tool(registry, gate, tool, {**ARGS_OF[tool], "plan_id": plan["plan_id"]}))
    assert revit.calls == []


def test_read_tool_needs_no_plan_and_runs_in_read_mode(tmp_path, monkeypatch):
    out = "SUMMARY\t1 elements checked for a piping system (SupplyHydronic): 0 would be refused\nROW\tkind=element\telement_id=5\tverdict=ok\nCOUNT\tfail\t0\nCOUNT\trow\t1"
    revit = FakeRevit(write_output=out, read_output=out)
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch, revit=revit)
    result = asyncio.run(run_gated_tool(registry, gate, "revit_mep_check_elements", dict(CHECK_ARGS)))
    assert result["ok"] is True and result["would_be_refused"] == 0
    assert [c[1]["mode"] for c in revit.calls] == ["read"]
    validate_read_script(revit.calls[0][1]["script"])


@pytest.mark.parametrize("tool", MUTATING)
def test_approved_plan_runs_the_write_script_and_then_the_system_report(tmp_path, monkeypatch, tool):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch)
    pid = approved(gate, tool, ARGS_OF[tool])
    result = asyncio.run(run_gated_tool(registry, gate, tool, {**ARGS_OF[tool], "plan_id": pid}))
    assert result["ok"] is True, result
    modes = [c[1]["mode"] for c in revit.calls]
    assert modes[0] == "write"
    assert modes[1:] == ([] if tool == "revit_mep_circuit" else ["read"])
    assert all(c[0] == "revit_execute_python" for c in revit.calls)
    assert gate.load_plan(pid)["actions"][0]["state"] == "executed"
    # the nested read call is the existing revit_system_report script, not a rewrite
    if tool != "revit_mep_circuit":
        assert "system_report: no piping or duct members matched" in revit.calls[1][1]["script"]


def test_one_approval_cannot_be_replayed(tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch)
    pid = approved(gate, "revit_mep_route", ROUTE_ARGS)
    args = {**ROUTE_ARGS, "plan_id": pid}
    asyncio.run(run_gated_tool(registry, gate, "revit_mep_route", args))
    with pytest.raises(BridgeError):
        asyncio.run(run_gated_tool(registry, gate, "revit_mep_route", args))


def test_a_failed_script_is_booked_as_a_failed_action(tmp_path, monkeypatch):
    out = "SUMMARY\tfailed\nFAIL\tSTEP_FAILED\tRevit did not commit\nMETA\toutcome\trolled_back\nCOUNT\tfail\t1"
    revit = FakeRevit(write_output=out)
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch, revit=revit)
    pid = approved(gate, "revit_mep_route", ROUTE_ARGS)
    result = asyncio.run(run_gated_tool(registry, gate, "revit_mep_route", {**ROUTE_ARGS, "plan_id": pid}))
    assert result["ok"] is False and result["changed_ids"] == []
    assert gate.load_plan(pid)["actions"][0]["state"] == "failed"
    assert [c[1]["mode"] for c in revit.calls] == ["write"]  # no report after a rollback


# --------------------------------------------------------------------------- #
# Argument validation: refused before anything is sent
# --------------------------------------------------------------------------- #
def _route(**changes: Any) -> Dict[str, Any]:
    args = json.loads(json.dumps(ROUTE_ARGS))
    for key, value in changes.items():
        if key.startswith("r_"):
            args["routes"][0][key[2:]] = value
        else:
            args[key] = value
    return args


@pytest.mark.parametrize("args,needle", [
    (_route(kind="plumbing"), "kind must be one of"),
    (_route(tag=""), "tag is required"),
    (_route(tag="café"), "tag is required"),
    (_route(system=""), "system is required"),
    (_route(system="nonsense"), "unknown system"),
    (_route(routes=[]), "1 to 25"),
    (_route(type_name=""), "type_name"),
    (_route(r_id="bad id!"), "routes[0].id"),
    (_route(r_level=""), "level is required"),
    (_route(r_size={}), "needs diameter_mm"),
    (_route(r_size={"diameter_mm": -5}), "greater than 0"),
    (_route(r_size={"width_mm": 300, "height_mm": 200}), "pipe is round"),
    (_route(r_size={"diameter_mm": 32, "width_mm": 300}), "not both"),
    (_route(r_run_height_m=None), "run_height_m is required"),
    (_route(r_to=None), "exactly one of to"),
    (_route(r_to={"mark": "MAN"}, r_branch_to={"route": "t"}), "exactly one of to"),
    (_route(r_to={"element_id": 1, "mark": "x"}), "exactly one of element_id or mark"),
    (_route(r_to={"point_m": [1, 2]}), "list of 3 numbers"),
    (_route(r_to={"mark": "MAN", "near_m": [0, 0, 0]}), "near_m belongs to revit_mep_connect"),
    (_route(r_to={"mark": "MAN", "sort": "w"}), "sort must be one of"),
    (_route(r_to={"mark": "MAN", "diameter_mm": [40, 30]}), "low, high"),
    (_route(r_to={"mark": "MAN", "colour": "red"}), "unknown keys"),
    (_route(r_via=[{"x_m": 1}]), "y_m must be a finite number"),
    (_route(r_via="x"), "list of at most 20"),
    (_route(r_bogus=1), "unknown keys"),
    (_route(transition_m=0), "transition_m"),
    (_route(on_error="ignore"), "on_error must be one of"),
])
def test_route_inputs_are_refused_before_anything_is_sent(module, args, needle):
    ex = Canned()
    result = call(module, "revit_mep_route", ex, args)
    assert result["ok"] is False and result["kind"] == "invalid_input", result
    assert needle in result["message"]
    assert ex.calls == []


def test_branch_inputs():
    module_obj = mep.RevitMepModule()
    base = _route(r_to=None, r_run_height_m=None)
    for bad, needle in [
        ({"route": "t", "element_ids": [1]}, "exactly one of route or element_ids"),
        ({}, "exactly one of route or element_ids"),
        ({"route": "t", "fitting": "weld"}, "fitting must be one of"),
        ({"element_ids": []}, "exactly one of route or element_ids"),
    ]:
        args = json.loads(json.dumps(base))
        args["routes"][0]["branch_to"] = bad
        result = module_obj.route(approved_executor=Canned(), **args)
        assert result["kind"] == "invalid_input" and needle in result["message"], (bad, result)
    args = json.loads(json.dumps(base))
    args["routes"][0].update(branch_to={"route": "t"}, run_height_m=0.1)
    assert "runs at the height of its trunk" in module_obj.route(approved_executor=Canned(), **args)["message"]
    args["routes"][0].pop("run_height_m")
    args["routes"][0]["via"] = [{"x_m": 1, "y_m": 2}]
    assert "no via points" in module_obj.route(approved_executor=Canned(), **args)["message"]


@pytest.mark.parametrize("tool,args,needle", [
    ("revit_mep_connect", {**CONNECT_ARGS, "kind": "elec"}, "kind must be one of"),
    ("revit_mep_connect", {**CONNECT_ARGS, "connections": []}, "1 to 50"),
    ("revit_mep_connect", {**CONNECT_ARGS, "connections": [{"id": "c", "a": {"mark": "x"}}]}, "needs a and b"),
    ("revit_mep_connect", {**CONNECT_ARGS, "connections": [{"id": "c", "a": {"mark": "x"}, "b": {"mark": "y"}, "joint": "weld"}]}, "joint must be one of"),
    ("revit_mep_connect", {**CONNECT_ARGS, "tolerance_mm": 0}, "tolerance_mm"),
    ("revit_mep_connect", {**CONNECT_ARGS, "connections": [{"id": "c", "a": {"point_m": [0, 0, 0]}, "b": {"mark": "y"}}]}, "needs exactly one of element_id or mark"),
    ("revit_mep_circuit", {**CIRCUIT_ARGS, "circuits": []}, "1 to 50"),
    ("revit_mep_circuit", {**CIRCUIT_ARGS, "circuits": [{"id": "C", "elements": [{"mark": "L"}]}]}, "panel is required"),
    ("revit_mep_circuit", {**CIRCUIT_ARGS, "circuits": [{"id": "C", "panel": {"mark": "P"}, "elements": []}]}, "1 to 200"),
    ("revit_mep_circuit", {**CIRCUIT_ARGS, "circuits": [{"id": "C", "panel": {"mark": "P", "sort": "x"}, "elements": [{"mark": "L"}]}]}, "connector filters"),
    ("revit_mep_circuit", {**CIRCUIT_ARGS, "circuits": [{"id": "C", "name": "a|b", "panel": {"mark": "P"}, "elements": [{"mark": "L"}]}]}, "characters Revit does not allow"),
    ("revit_mep_check_elements", {**CHECK_ARGS, "kind": "gas"}, "kind must be one of"),
    ("revit_mep_check_elements", {**CHECK_ARGS, "elements": []}, "1 to 200"),
])
def test_other_inputs_are_refused_before_anything_is_sent(module, tool, args, needle):
    ex = Canned()
    result = call(module, tool, ex, args)
    assert result["ok"] is False and result["kind"] == "invalid_input", result
    assert needle in result["message"]
    assert ex.calls == []


@pytest.mark.parametrize("tool,args", [
    ("revit_mep_route", _route(kind="duct", system="hsup")),
    ("revit_mep_route", _route(kind="pipe", system="supply")),
    ("revit_mep_route", _route(kind="pipe", system="PowerCircuit")),
    ("revit_mep_connect", {**CONNECT_ARGS, "kind": "duct", "system": "SupplyHydronic"}),
    ("revit_mep_circuit", {**CIRCUIT_ARGS, "system": "cold"}),
    ("revit_mep_circuit", {**CIRCUIT_ARGS, "system": "SupplyAir"}),
    ("revit_mep_check_elements", {**CHECK_ARGS, "kind": "duct"}),
    ("revit_mep_check_elements", {**CHECK_ARGS, "kind": "elec"}),
])
def test_a_system_of_the_wrong_domain_is_refused_with_a_clear_error(module, tool, args):
    ex = Canned()
    result = call(module, tool, ex, args)
    assert result["ok"] is False and result["kind"] == "domain_mismatch", result
    assert "never placed" in result["message"] and result["hint"].endswith("Nothing was changed.")
    assert ex.calls == []


def test_short_system_keys_and_revit_names_mean_the_same(module):
    for key, name in [("hsup", "SupplyHydronic"), ("HRET", "ReturnHydronic"), ("cold", "DomesticColdWater"), ("SanItary", "Sanitary")]:
        assert mep.normalize_system(key, "pipe") == name
    for key, name in [("supply", "SupplyAir"), ("OtherAir", "OtherAir"), ("outdoor", "OtherAir")]:
        assert mep.normalize_system(key, "duct") == name
    assert mep.normalize_system("power", "elec") == "PowerCircuit"
    # every key of docs/recipes/villa2/m1_specs.json maps to a Revit system of its own domain
    specs = json.loads((Path(__file__).resolve().parents[3] / "docs" / "recipes" / "villa2" / "m1_specs.json").read_text(encoding="utf-8"))
    kinds = {"pipe": "pipe", "duct": "duct", "elec": "elec"}
    seen = set()
    for family in specs:
        for port in family["ports"]:
            seen.add((kinds[port["kind"]], port["system"]))
    assert len(seen) >= 10
    for kind, key in seen:
        assert mep.normalize_system(key, kind) in mep.REVIT_SYSTEMS[kind]


# --------------------------------------------------------------------------- #
# Seams: no bridge, mock mode, running receipt, bridge errors
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tool", MUTATING + READ_ONLY)
def test_without_an_executor_the_tool_says_so(module, tool):
    method = {"revit_mep_route": module.route, "revit_mep_connect": module.connect, "revit_mep_circuit": module.circuit,
              "revit_mep_check_elements": module.check_elements}[tool]
    result = method(**ARGS_OF[tool])
    assert result["ok"] is False and result["kind"] == "no_bridge"


@pytest.mark.parametrize("tool", MUTATING + READ_ONLY)
def test_mock_mode_never_looks_like_a_pass(monkeypatch, tool):
    monkeypatch.setattr(mep, "_server_in_mock_mode", lambda: True)
    ex = Canned()
    result = call(mep.RevitMepModule(), tool, ex)
    assert result["mock"] is True and result["verified"] is False and "UNVERIFIED" in result["summary"]
    assert ex.calls == []


def test_running_receipt_is_not_a_result(module):
    class Running(Canned):
        def __call__(self, name, args):
            return {"status": "running", "request_id": "11223344-5566-7788-99aa-bbccddeeff00"}

    result = call(module, "revit_mep_route", Running())
    assert result["status"] == "running" and result["verified"] is False and result["changed_ids"] == []


@pytest.mark.parametrize("message,kind", [
    ("plan_id required: approval", "approval_required"),
    ("request timed out after 30 s", "timeout_running"),
    ("connection refused", "bridge_error"),
])
def test_bridge_errors_are_classified(module, message, kind):
    def broken(name, args):
        raise RuntimeError(message)

    assert call(module, "revit_mep_route", broken)["kind"] == kind


def test_script_error_and_unparsable_output(module):
    result = call(module, "revit_mep_route", lambda n, a: {"success": False, "error": "SyntaxError in line 3"})
    assert result["kind"] == "script_error" and "Check the model" in result["hint"]
    result = call(module, "revit_mep_route", lambda n, a: {"success": True, "output": "hello"})
    assert result["kind"] == "unparsable_output"
    result = call(module, "revit_mep_route", lambda n, a: {"success": True, "output": "ERROR\tscript_exception\tNameError: x"})
    assert result["kind"] == "script_exception" and result["changed_ids"] == []


# --------------------------------------------------------------------------- #
# The result contract: changed_ids, post_check, verified
# --------------------------------------------------------------------------- #
def test_success_carries_changed_ids_post_check_and_verified(module):
    ex = Canned()
    result = call(module, "revit_mep_route", ex)
    assert result["ok"] is True and result["verified"] is True
    assert result["changed_ids"] == [12, 13]
    names = [c["check"] for c in result["post_check"]["checks"]]
    assert mep.SYSTEM_CHECK_NAME in names and result["post_check"]["failed"] == 0
    assert result["system_report"]["ran"] is True
    assert result["rows"][0]["id"] == 12 and result["rows"][0]["length_mm"] == 1500.0
    # the report ran on exactly the changed ids
    assert "ARGS = {u'ids': [12, 13]" in ex.calls[1]["script"] or "[12, 13]" in ex.calls[1]["script"]


def test_a_failed_post_check_in_the_script_is_never_ok(module):
    out = WRITE_OK.replace("ok=1", "ok=0") + "\nFAIL\tPOST_CHECK_FAILED\troute r1: sizes as requested: wanted 32 mm, found 28.0 mm"
    result = call(module, "revit_mep_route", Canned(write=out.replace("outcome\tok", "outcome\tpost_check_failed")))
    assert result["ok"] is False and result["kind"] == "post_check_failed"
    assert result["post_check"]["ok"] is False and result["post_check"]["failed"] == 1
    assert result["changed_ids"] == [12, 13]  # the model changed: say what
    assert "POST_CHECK_FAILED" in result["message"]


def test_fail_lines_cannot_be_turned_into_success():
    parsed = parse_script_output("SUMMARY\tx\nFAIL\tPOST\tfailed\nMETA\toutcome\tok\nCOUNT\tfail\t1")
    assert mep._finish_write("revit_mep_route", parsed, 1, None)["ok"] is False


def test_rolled_back_reports_no_changes_and_the_failing_ids(module):
    out = ("SUMMARY\tfailed\nFAIL\tSTEP_FAILED\tRoute r2: Revit refused create_pipe (call 5) (element ids: 41,42)\n"
           "META\toutcome\trolled_back\nMETA\tchanged_ids\t\nMETA\tfailed_ids\t41,42\nCOUNT\tfail\t1")
    ex = Canned(write=out)
    result = call(module, "revit_mep_route", ex)
    assert result["ok"] is False and result["kind"] == "rolled_back"
    assert result["changed_ids"] == [] and result["element_ids"] == [41, 42]
    assert "Revit refused" in result["message"] and "rolled back" in result["summary"]
    assert len(ex.calls) == 1  # no system report after a rollback


def test_partial_failure_keeps_what_worked(module):
    out = ("SUMMARY\t1 of 2 routes built\nFAIL\tSTEP_FAILED\tRoute r2: nope (element ids: 7)\nMETA\toutcome\tpartial_failure\nMETA\ton_error\tskip\n"
           "META\tchanged_ids\t12,13\nMETA\tfailed_ids\t7\nCOUNT\tfail\t1")
    ex = Canned(write=out)
    result = call(module, "revit_mep_route", ex, on_error="skip")
    assert result["ok"] is False and result["kind"] == "partial_failure"
    assert result["changed_ids"] == [12, 13] and result["element_ids"] == [7] and result["on_error"] == "skip"
    assert len(ex.calls) == 1


def test_guard_refusal_is_ok_false_with_the_element_and_changes_nothing(module):
    out = ("SUMMARY\t\nFAIL\tCATEGORY_MISMATCH\troute r1, from: GEN (id 9, category Generic Models) is not a piping element\n"
           "META\toutcome\tcategory_mismatch\nMETA\tchanged_ids\t\nMETA\tfailed_ids\t9\nCOUNT\tfail\t1")
    result = call(module, "revit_mep_route", Canned(write=out))
    assert result["ok"] is False and result["kind"] == "category_mismatch"
    assert result["changed_ids"] == [] and result["element_ids"] == [9]
    assert "not a piping element" in result["message"] and "revit_mep_check_elements" in result["hint"]


def test_revit_warnings_are_listed_not_hidden(module):
    out = WRITE_OK + "\nINFO\tREVIT_WARNING_DISMISSED\tPipe is slightly off axis\nMETA\twarnings_dismissed\t3"
    result = call(module, "revit_mep_route", Canned(write=out))
    assert result["ok"] is True and result["warnings_dismissed"] == 3
    assert any("slightly off axis" in i for i in result["info"])


# --------------------------------------------------------------------------- #
# revit_system_report as the post-check
# --------------------------------------------------------------------------- #
def test_open_end_found_by_the_system_report_fails_a_route(module):
    report = "SUMMARY\t1 systems, 1 open ends\nFAIL\tSYS_OPEN_END\tPipeCurves 12 (curve) in x: open end at (1, 2, 3) m, dia 32 mm\nCOUNT\tfail\t1\nCOUNT\tinfo\t0"
    result = call(module, "revit_mep_route", Canned(read=report))
    assert result["ok"] is False and result["kind"] == "post_check_failed"
    assert result["changed_ids"] == [12, 13]
    failed = [c for c in result["post_check"]["checks"] if not c["ok"]]
    assert failed and failed[0]["check"] == mep.SYSTEM_CHECK_NAME and "SYS_OPEN_END" in failed[0]["detail"]
    assert result["outcome"] == "post_check_failed"


def test_equipment_ports_and_islands_do_not_fail_a_route(module):
    report = ("SUMMARY\tx\nFAIL\tSYS_PORT_UNCONNECTED\tMechanicalEquipment 5 port left open\n"
              "FAIL\tSYS_ISLANDS\tx: 2 separate groups\nCOUNT\tfail\t2\nCOUNT\tinfo\t0")
    result = call(module, "revit_mep_route", Canned(read=report))
    assert result["ok"] is True
    assert len(result["system_report"]["not_counted"]) == 2


def test_flow_and_size_mismatches_fail_a_route(module):
    report = "SUMMARY\tx\nFAIL\tSYS_SIZE_MISMATCH\tPipeCurves 12 (dia 32 mm) is connected to Equipment 5 (dia 28 mm)\nCOUNT\tfail\t1"
    assert call(module, "revit_mep_route", Canned(read=report))["ok"] is False
    report = "SUMMARY\tx\nFAIL\tSYS_FLOW_MISMATCH\tboth Out\nCOUNT\tfail\t1"
    assert call(module, "revit_mep_route", Canned(read=report))["kind"] == "post_check_failed"


def test_report_lines_beyond_the_page_count_as_problems(module):
    report = "SUMMARY\tx\nFAIL\tSYS_ISLANDS\tx\nCOUNT\tfail\t900"
    result = call(module, "revit_mep_route", Canned(read=report))
    assert result["ok"] is False and "were not shown" in result["post_check"]["checks"][0]["detail"]


def test_a_system_report_that_cannot_run_leaves_the_call_unverified(module):
    result = call(module, "revit_mep_route", Canned(read_exc=RuntimeError("bridge down")))
    assert result["ok"] is True and result["verified"] is False
    assert any("UNVERIFIED" in i and "bridge down" in i for i in result["info"])
    assert result["system_report"]["ran"] is False
    assert not any(c["check"] == mep.SYSTEM_CHECK_NAME for c in result["post_check"]["checks"])


def test_a_partial_system_report_is_unverified_not_passed(module):
    report = "SUMMARY\tPARTIAL: 1 systems\nMETA\tpartial\t1\nCOUNT\tfail\t0"
    result = call(module, "revit_mep_route", Canned(read=report))
    assert result["verified"] is False and result["ok"] is True


def test_connect_lists_open_ends_but_only_counts_mismatches(module):
    write = ("SUMMARY\t1 of 1 connections made\nMETA\toutcome\tok\nMETA\tchanged_ids\t5,6,90\nMETA\treport_ids\t6,90\n"
             "ROW\trow_type=post\tcheck=connection c1: the two connectors are joined\tok=1\tdetail=joined directly\n"
             "ROW\trow_type=item\tkind=connection\tid=\tconnection=c1\ta_id=5\tb_id=6\tjoint=direct\tstatus=connected\nCOUNT\tfail\t0")
    read = ("SUMMARY\t1 systems, 1 open ends\nFAIL\tSYS_OPEN_END\tPipeCurves 6 (curve) in x: open end at (1, 2, 3) m, dia 32 mm\n"
            "ROW\tkind=open_end\tsystem=x\telement_id=6\tcategory=Pipes\trole=curve\tsize=dia 32 mm\tx_m=1.0\ty_m=2.0\tz_m=3.0\n"
            "COUNT\tfail\t1\nCOUNT\trow\t1")
    ex = Canned(write=write, read=read)
    result = call(module, "revit_mep_connect", ex)
    assert result["ok"] is True, result
    assert result["open_ends"][0]["element_id"] == 6 and result["open_ends"][0]["x_m"] == 1.0
    assert result["changed_ids"] == [5, 6, 90]
    assert "[6, 90]" in ex.calls[1]["script"]  # the report ran on the pipes and fittings, not on the equipment
    mismatch = read.replace("SYS_OPEN_END", "SYS_SIZE_MISMATCH")
    assert call(module, "revit_mep_connect", Canned(write=write, read=mismatch))["ok"] is False


def test_circuit_does_not_run_a_system_report(module):
    write = ("SUMMARY\t1 of 1 circuits made\nMETA\toutcome\tok\nMETA\tchanged_ids\t30\n"
             "ROW\trow_type=item\tkind=circuit\tid=30\tcircuit=C1\tname=C1\tpanel_id=4\telements=2\tcircuit_number=1\tpanel_name=P\nCOUNT\tfail\t0")
    ex = Canned(write=write)
    result = call(module, "revit_mep_circuit", ex)
    assert result["ok"] is True and result["changed_ids"] == [30] and len(ex.calls) == 1
    assert result["rows"][0]["elements"] == 2 and result["rows"][0]["panel_id"] == 4


def test_check_elements_counts_what_would_be_refused(module):
    read = ("SUMMARY\t2 elements checked\nFAIL\tCATEGORY_MISMATCH\tGEN is not a piping element\n"
            "ROW\tkind=element\telement_id=5\tverdict=ok\nROW\tkind=element\telement_id=9\tverdict=category_mismatch\tmessage=GEN\n"
            "COUNT\tfail\t1\nCOUNT\trow\t2")
    result = call(module, "revit_mep_check_elements", Canned(read=read, write=read))
    assert result["ok"] is True and result["would_be_refused"] == 1 and result["counts"]["fails"] == 1
    assert result["changed_ids"] == []
