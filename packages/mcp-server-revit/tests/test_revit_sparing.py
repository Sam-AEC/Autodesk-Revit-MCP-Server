"""revit_sparing module: manifest, tool metadata, approval gating, argument validation and the result contract.

Nothing here talks to Revit. The scripts themselves run against a stub of the Revit API in
test_revit_sparing_scripts.py. Everything that needs a live Revit is UNVERIFIED (see the module docstring).
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
from revit_mcp_server.errors import BridgeError  # noqa: E402
from revit_mcp_server.module_registry import ModuleInstance, ModuleManifest  # noqa: E402
from revit_mcp_server.modules.revit_sparing import module as sp  # noqa: E402
from revit_mcp_server.providers.base import ProviderTool  # noqa: E402
from revit_mcp_server.providers.module_provider import ModuleProvider  # noqa: E402
from revit_mcp_server.security.approval import ApprovalGate  # noqa: E402
from revit_mcp_server.security.dispatch import run_gated_tool  # noqa: E402
from revit_mcp_server.security.read_mode import validate_read_script  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402
from revit_mcp_server.tool_metadata import enrich_tool  # noqa: E402

FIND_OUT = (
    "SUMMARY\t1 crossings (1 need a sparing, 0 already open) between 1 MEP elements and 1 hosts; 1 pairs tested\n"
    "ROW\tcrossing_id=301x101\tmep_id=301\tmep_link=\tmep_cat=pipes\tsystem=Riolering\thost_id=101\thost_link=\thost_cat=walls\t"
    "level=00\tx_mm=2000.0\ty_mm=5000.0\tz_mm=1000.0\tmep_size=dia 110\tinsul_mm=0.0\thost_t_mm=200.0\tangle_deg=0.0\t"
    "passage=perpendicular\texisting=\texisting_id=\tshape=round\tsparing_w_mm=160\tsparing_h_mm=160\tsparing_d_mm=200\tmembers=1\tmep_ids=301\n"
    "META\tcrossings\t1\nMETA\talready_open\t0\nMETA\tneed_sparing\t1\nMETA\tmep_elements\t1\nMETA\thosts\t1\nMETA\tpairs_tested\t1\n"
    "META\ttruncated\t0\nMETA\ttruncated_reason\t\nMETA\tcoordinates\tproject\nMETA\tpartial\t0\nMETA\tverified\t1\n"
    "COUNT\tfail\t0\nCOUNT\tinfo\t0\nCOUNT\trow\t1"
)
PLACE_OK = (
    "SUMMARY\t1 of 1 sparingen placed (1 new, 0 replaced), 0 crossings skipped, 1 crossings found\nMETA\tcrossings\t1\n"
    "META\toutcome\tok\nMETA\ton_error\tabort\nMETA\tchanged_ids\t5001\nMETA\tfailed_ids\t\nMETA\twarnings_dismissed\t0\n"
    "ROW\trow_type=post\tcheck=301x101: exists\tok=1\tdetail=id 5001\n"
    "ROW\trow_type=item\tkind=sparing\tid=5001\tcrossing_id=301x101\taction=created\tmode=family\thost_id=101\tw_mm=160\th_mm=160\td_mm=200\tstatus=Voorstel\n"
    "COUNT\tfail\t0"
)
PLACE_ARGS: Dict[str, Any] = {"tag": "SPA-L00", "mode": "family", "family_name": "Sparing", "type_name": "Standaard",
                              "size_parameters": {"width": "b", "height": "h", "depth": "d"}}
FIND_ARGS: Dict[str, Any] = {"categories": ["pipes"], "level": "00"}


class FakeRevit:
    def __init__(self, write_output: str = PLACE_OK, read_output: str = FIND_OUT) -> None:
        self.write_output, self.read_output = write_output, read_output
        self.calls: List[tuple] = []

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return {"success": True, "output": self.read_output if arguments.get("mode") == "read" else self.write_output}

    def call_is_read_only(self, name: str, arguments: Dict[str, Any]) -> bool:
        return arguments.get("mode") == "read"


def manifest() -> Dict[str, Any]:
    return json.loads((sp.MODULE_DIR / "module.json").read_text(encoding="utf-8"))


def wire(tmp_path, monkeypatch, revit=None):
    inst = ModuleInstance(ModuleManifest(**manifest()), sp.MODULE_DIR)
    monkeypatch.setattr(inst.code_module, "_server_in_mock_mode", lambda: False)
    modules = SimpleNamespace(get_all_modules=lambda: [inst], config=SimpleNamespace(allow_python_host=False))
    gate = ApprovalGate(tmp_path, "ask_first")
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


WS: List[WorkspaceMonitor] = []


@pytest.fixture()
def module(monkeypatch, tmp_path):
    monkeypatch.setattr(sp, "_server_in_mock_mode", lambda: False)
    WS[:] = [WorkspaceMonitor([tmp_path])]
    return sp.RevitSparingModule()


class Canned:
    def __init__(self, write: str = PLACE_OK, read: str = FIND_OUT) -> None:
        self.write, self.read = write, read
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        self.calls.append(args)
        return {"success": True, "output": self.read if args["mode"] == "read" else self.write}


def place(module, ex, **changes):
    args = {**PLACE_ARGS, **changes}
    return module.place(approved_executor=ex, workspace=WS[0], **{k: v for k, v in args.items() if v is not None})


def find(module, ex, **args):
    return module.find(tool_executor=ex, workspace=WS[0], **args)


# --------------------------------------------------------------------------- #
# Manifest, metadata and the shipped files
# --------------------------------------------------------------------------- #
def test_public_tool_names_and_gate_flags(tmp_path, monkeypatch):
    provider, *_ = wire(tmp_path, monkeypatch)
    tools = {t.name: t for t in provider.get_capabilities()}
    assert {"revit_sparing_find", "revit_sparing_place"} <= set(tools)
    assert tools["revit_sparing_find"].is_mutating is False and tools["revit_sparing_place"].is_mutating is True
    commands = {c["mcp_tool"]: c for c in manifest()["commands"]}
    assert commands["revit_sparing_place"]["requires_plan"] is True and commands["revit_sparing_place"]["destructive"] is False


def _undocumented(schema: Any, path: str = "root") -> List[str]:
    missing: List[str] = []
    if isinstance(schema, dict):
        for key, prop in (schema.get("properties") or {}).items():
            if not isinstance(prop, dict) or not prop.get("description"):
                missing.append(f"{path}.{key}")
            missing.extend(_undocumented(prop, f"{path}.{key}"))
        if isinstance(schema.get("items"), dict):
            missing.extend(_undocumented(schema["items"], path + "[]"))
    return missing


def test_every_parameter_is_documented_short_and_matches_the_code():
    import inspect

    data = manifest()
    assert len(data["description"]) < 900
    for cmd in data["commands"]:
        assert _undocumented(cmd["input_schema"], cmd["mcp_tool"]) == []
        assert 80 < len(cmd["title"]) < 520
        for prop in cmd["input_schema"]["properties"].values():
            assert len(prop["description"]) < 400
        method = getattr(sp.RevitSparingModule, cmd["id"])
        params = set(inspect.signature(method).parameters) - {"self", "workspace", "tool_executor", "approved_executor", "_"}
        assert set(cmd["input_schema"]["properties"]) == params, cmd["id"]
    titles = {c["mcp_tool"]: c["title"] for c in data["commands"]}
    assert "revit_check_clashes" in titles["revit_sparing_find"] and "revit_check_intersections" in titles["revit_sparing_find"]
    assert "revit_sparing_place" in titles["revit_sparing_find"] and "revit_sparing_find" in titles["revit_sparing_place"]


def test_tool_metadata_marks_place_gated_and_find_read_only(tmp_path, monkeypatch):
    provider, *_ = wire(tmp_path, monkeypatch)
    for tool in provider.get_capabilities():
        if not tool.name.startswith("revit_sparing_"):
            continue
        assert isinstance(tool, ProviderTool)
        enriched = enrich_tool("module", tool)
        if tool.name == "revit_sparing_place":
            assert enriched.annotations.readOnlyHint is False and "plan_id" in enriched.inputSchema["properties"]
        else:
            assert enriched.annotations.readOnlyHint is True and "plan_id" not in enriched.inputSchema["properties"]


def test_module_files_have_no_conflict_markers():
    paths = list(sp.MODULE_DIR.rglob("*")) + [Path(__file__), Path(__file__).with_name("test_revit_sparing_scripts.py"),
                                                Path(__file__).with_name("revit_sparing_stub.py")]
    for path in sorted(paths):
        if path.is_file() and path.suffix in {".py", ".json", ".ipy"}:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                assert not re.match(r"^(<{7}|={7}|>{7})( |$)", line), f"{path.name}:{number}"


def test_scripts_are_python27_safe_and_find_stays_read_only():
    scripts = sorted(sp.SCRIPT_DIR.glob("*.ipy"))
    assert {p.name for p in scripts} == {"_sparing_detect.ipy", "_sparing_place_lib.ipy", "find.ipy", "place.ipy"}
    for path in scripts:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            assert not isinstance(node, (ast.JoinedStr, ast.AnnAssign, ast.NamedExpr)), f"{path.name}: f-string, annotation or walrus"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.returns is None and all(a.annotation is None for a in node.args.args), f"{path.name}: type hint"
    for name in sp.SCRIPTS:
        compile(sp.build_script(name, {"tag": "x'\nraise Exception('oops')"}), name, "exec")
    validate_read_script(sp.build_script("find.ipy", sp.detection_args()))
    validate_read_script((sp.SCRIPT_DIR / "_sparing_detect.ipy").read_text(encoding="utf-8"))
    assert "Transaction" in sp.build_script("place.ipy", {})


def test_docstring_says_unverified_and_lists_follow_ups():
    doc = sp.__doc__ or ""
    assert "UNVERIFIED" in doc and "Follow-ups" in doc and "discipline models" in doc


# --------------------------------------------------------------------------- #
# Approval gating
# --------------------------------------------------------------------------- #
def test_place_refuses_without_a_plan_id(tmp_path, monkeypatch):
    provider, gate, registry, revit = wire(tmp_path, monkeypatch)
    with pytest.raises(BridgeError, match="plan_id"):
        asyncio.run(run_gated_tool(registry, gate, "revit_sparing_place", dict(PLACE_ARGS)))
    assert revit.calls == []


def test_place_refuses_a_plan_that_is_not_approved(tmp_path, monkeypatch):
    provider, gate, registry, revit = wire(tmp_path, monkeypatch)
    plan = gate.create_plan([{"tool": "revit_sparing_place", "arguments": dict(PLACE_ARGS)}], [{}])
    with pytest.raises(BridgeError, match="pending"):
        asyncio.run(run_gated_tool(registry, gate, "revit_sparing_place", {**PLACE_ARGS, "plan_id": plan["plan_id"]}))
    assert revit.calls == []


def test_find_needs_no_plan_and_runs_in_read_mode(tmp_path, monkeypatch):
    provider, gate, registry, revit = wire(tmp_path, monkeypatch)
    result = asyncio.run(run_gated_tool(registry, gate, "revit_sparing_find", dict(FIND_ARGS)))
    assert result["ok"] is True and result["totals"]["crossings"] == 1
    assert [c[1]["mode"] for c in revit.calls] == ["read"]
    validate_read_script(revit.calls[0][1]["script"])


def test_approved_plan_runs_the_write_script_once(tmp_path, monkeypatch):
    provider, gate, registry, revit = wire(tmp_path, monkeypatch)
    pid = approved(gate, "revit_sparing_place", PLACE_ARGS)
    result = asyncio.run(run_gated_tool(registry, gate, "revit_sparing_place", {**PLACE_ARGS, "plan_id": pid}))
    assert result["ok"] is True and result["changed_ids"] == [5001], result
    assert [c[1]["mode"] for c in revit.calls] == ["write"]
    assert gate.load_plan(pid)["actions"][0]["state"] == "executed"
    with pytest.raises(BridgeError):
        asyncio.run(run_gated_tool(registry, gate, "revit_sparing_place", {**PLACE_ARGS, "plan_id": pid}))


def test_a_rolled_back_place_is_booked_as_failed(tmp_path, monkeypatch):
    out = "SUMMARY\tfailed\nFAIL\tSTEP_FAILED\tSparing 301x101: Revit did not commit (element ids: 301,101)\nMETA\toutcome\trolled_back\nMETA\tfailed_ids\t301,101\nCOUNT\tfail\t1"
    provider, gate, registry, revit = wire(tmp_path, monkeypatch, revit=FakeRevit(write_output=out))
    pid = approved(gate, "revit_sparing_place", PLACE_ARGS)
    result = asyncio.run(run_gated_tool(registry, gate, "revit_sparing_place", {**PLACE_ARGS, "plan_id": pid}))
    assert result["ok"] is False and result["kind"] == "rolled_back" and result["element_ids"] == [301, 101]
    assert result["changed_ids"] == [] and "rolled back" in result["summary"]
    assert gate.load_plan(pid)["actions"][0]["state"] == "failed"


# --------------------------------------------------------------------------- #
# Argument validation: refused before anything is sent
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("args,needle", [
    ({"categories": ["sprinklers"]}, "unknown category"),
    ({"categories": "pipes"}, "must be a list"),
    ({"host_categories": ["doors"]}, "unknown category"),
    ({"ids": [1.5]}, "integer"),
    ({"ids": "301"}, "list"),
    ({"clearance_mm": -1}, "clearance_mm must be between"),
    ({"clearance_mm": True}, "finite number"),
    ({"round_to_mm": 0}, "round_to_mm must be between"),
    ({"merge_tolerance_mm": float("nan")}, "finite"),
    ({"max_pairs": 0}, "max_pairs"),
    ({"max_elements": 50000}, "max_elements"),
    ({"time_budget_s": 60}, "time_budget_s"),
    ({"include_links": "yes"}, "true or false"),
    ({"level": "a|b"}, "not allow"),
    ({"limit": 0}, "limit"),
    ({"offset": -1}, "offset"),
])
def test_find_rejects_bad_arguments(module, args, needle):
    ex = Canned()
    result = find(module, ex, **args)
    assert result["ok"] is False and result["kind"] == "invalid_input" and needle in result["message"], result
    assert ex.calls == []


@pytest.mark.parametrize("changes,needle", [
    ({"tag": ""}, "tag is required"),
    ({"tag": "café"}, "tag is required"),
    ({"mode": "void"}, "mode must be one of"),
    ({"mode": None}, "mode is required"),
    ({"family_name": ""}, "family_name is required"),
    ({"type_name": None}, "type_name is required"),
    ({"size_parameters": None}, "size_parameters is required"),
    ({"size_parameters": {"width": "b"}}, "width and height, or diameter"),
    ({"size_parameters": {"breedte": "b"}}, "unknown keys"),
    ({"mode": "opening"}, "belong to mode 'family'"),
    ({"status_value": "Voorstel"}, "needs status_parameter"),
    ({"crossing_ids": ["301x101; drop"]}, "not a crossing_id"),
    ({"crossing_ids": "301x101"}, "list"),
    ({"max_sparings": 501}, "max_sparings"),
    ({"on_error": "retry"}, "on_error must be one of"),
    ({"dry_run": "true"}, "true or false"),
    ({"clearance_mm": 1000}, "clearance_mm"),
])
def test_place_rejects_bad_arguments(module, changes, needle):
    ex = Canned()
    result = place(module, ex, **changes)
    assert result["ok"] is False and result["kind"] == "invalid_input" and needle in result["message"], result
    assert ex.calls == []


def test_defaults_reach_the_script(module):
    ex = Canned()
    find(module, ex)
    script = ex.calls[0]["script"]
    args = sp.detection_args()
    assert args["categories"] == ["pipes", "ducts", "conduits", "cabletrays"] and args["host_categories"] == ["walls", "floors"]
    assert (args["clearance_mm"], args["round_to_mm"], args["include_links"]) == (25.0, 10.0, False)
    assert "ARGS = " + sp.py2_literal(args) in script
    ex = Canned()
    place(module, ex, status_parameter="Sparing status", categories=["Pipe", "cable_trays"])
    script = ex.calls[0]["script"]
    assert "u'status_value': u'Voorstel'" in script and "u'sparing_family': u'Sparing'" in script
    assert "u'categories': [u'pipes', u'cabletrays']" in script and "u'dry_run': False" in script


# --------------------------------------------------------------------------- #
# Result contract
# --------------------------------------------------------------------------- #
def test_find_result_is_compact_summary_first(module):
    result = find(module, Canned())
    assert list(result)[:5] == ["ok", "tool", "verified", "summary", "totals"] and list(result)[-1] == "rows"
    row = result["rows"][0]
    assert row["sparing_w_mm"] == 160 and row["mep_id"] == 301 and row["existing_id"] is None
    assert result["totals"] == {"crossings": 1, "need_sparing": 1, "already_open": 0, "mep_elements": 1, "hosts": 1,
                                "pairs_tested": 1, "parallel_in_host": 0, "skipped_elements": 0, "truncated": False,
                                "coordinates": "project"}


def test_find_truncated_is_partial_and_unverified(module):
    out = FIND_OUT.replace("META\ttruncated\t0", "META\ttruncated\t1").replace("META\ttruncated_reason\t", "META\ttruncated_reason\tmax_pairs")
    out = out.replace("META\tverified\t1", "META\tverified\t0").replace("META\tpartial\t0", "META\tpartial\t1")
    result = find(module, Canned(read=out))
    assert result["verified"] is False and result["limits"]["partial"] is True and result["limits"]["truncated"] is True
    assert result["totals"]["truncated_reason"] == "max_pairs"


def test_place_refusal_from_the_script_is_not_ok(module):
    out = "SUMMARY\t\nMETA\toutcome\tmissing_parameter\nMETA\tchanged_ids\t\nFAIL\tMISSING_PARAMETER\tfamily 'Sparing': 'b' does not exist. Instance parameters it has: Breedte\nCOUNT\tfail\t1"
    result = place(module, Canned(write=out))
    assert result["ok"] is False and result["kind"] == "missing_parameter" and "Breedte" in result["message"]
    assert "Nothing was changed" in result["hint"] and result["changed_ids"] == []


def test_place_post_check_failure_is_never_ok(module):
    out = PLACE_OK.replace("check=301x101: exists\tok=1", "check=301x101: b\tok=0")
    result = place(module, Canned(write=out))
    assert result["ok"] is False and result["kind"] == "post_check_failed"


def test_mock_mode_and_missing_bridge(module, monkeypatch):
    assert place(module, None)["kind"] == "no_bridge"
    assert find(module, None)["kind"] == "no_bridge"
    monkeypatch.setattr(sp, "_server_in_mock_mode", lambda: True)
    result = find(module, Canned())
    assert result["mock"] is True and result["verified"] is False
    assert place(module, Canned())["post_check"]["ok"] is None
