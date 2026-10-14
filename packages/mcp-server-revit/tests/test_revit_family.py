from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from helpers import human_approve
from revit_mcp_server.module_registry import ModuleInstance, ModuleManifest
from revit_mcp_server.modules.revit_family import module as fam
from revit_mcp_server.providers.module_provider import ModuleProvider
from revit_mcp_server.security.approval import ApprovalGate
from revit_mcp_server.security.dispatch import run_gated_tool
from revit_mcp_server.security.workspace import WorkspaceMonitor

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = "C:\\ProgramData\\Autodesk\\RVT 2024\\Family Templates\\English\\Metric Electrical Equipment.rft"
PANEL = {"name": "AMB2_Panel", "category": "elec_eq", "w": 0.5, "d": 0.15, "h": 0.7,
         "ports": [{"pos": [0, 0.08, 0.3], "dir": "+y", "kind": "elec", "system": "power", "label": "feed"}]}
HEAT = {"name": "AMB2_Heat", "category": "mech", "w": 0.6, "d": 0.6, "h": 1.8,
        "ports": [{"pos": [0.32, -0.2, 1.6], "dir": "+x", "kind": "pipe", "system": "hsup", "dia_mm": 40, "flow": "out"},
                  {"pos": [0.32, 0.2, 1.6], "dir": "+x", "kind": "pipe", "system": "hret", "dia_mm": 40, "flow": "in"},
                  {"pos": [0.0, 0.0, 1.85], "dir": "+z", "kind": "duct", "system": "supply", "dia_mm": 100}]}


def build_output(families: List[Dict[str, Any]], *, outcome: str = "ok", ids: Optional[Dict[str, int]] = None, extra_lines: str = "") -> str:
    ids = ids or {f["name"]: 501 + 10 * i for i, f in enumerate(families)}
    lines = [f"SUMMARY\t{len(families)} of {len(families)} families made", f"META\toutcome\t{outcome}", "META\ton_error\tabort",
             "META\tchanged_ids\t" + ",".join(str(i) for i in ids.values()), "META\twarnings_dismissed\t1",
             "INFO\tREVIT_WARNING_DISMISSED\tFamily has an unused reference plane"]
    for f in families:
        lines.append(f"ROW\trow_type=item\tkind=family\tid={ids[f['name']]}\tname={f['name']}\tcategory={f['category']}\ttemplate={TEMPLATE}\t"
                     f"template_kind=category\tfile=C:\\ws\\{f['name']}.rfa\tbytes=1000\tports={len(f['ports'])}\ttypes=1\tstatus=created")
        lines.append(f"ROW\trow_type=post\tcheck=category:{f['name']}\tok=1\tdetail=category in the project")
        lines.append(f"ROW\trow_type=post\tcheck=family_loaded:{f['name']}\tok=1\tdetail=family id {ids[f['name']]}")
    lines.append(extra_lines)
    lines.append("COUNT\tfail\t0")
    return "\n".join(line for line in lines if line)


DOMAINS = {"pipe": "DomainPiping", "duct": "DomainHvac", "elec": "DomainElectrical"}
LABELS = {"mech": "Mechanical Equipment", "elec_eq": "Electrical Equipment"}


def probe_output(spec: Dict[str, Any], family_id: int, *, nested: int = 0, category: Optional[str] = None, fail: str = "", skip_connectors: int = 0) -> str:
    lines = [f"SUMMARY\t{spec['name']}: {LABELS[spec['category']]}, 1 types, 0 instances, {nested} nested, {len(spec['ports'])} connectors, {1 if fail else 0} problems",
             f"ROW\tkind=family\tfamily=Family '{spec['name']}'\tname={spec['name']}\tcategory={category or LABELS[spec['category']]}\tid={family_id}\ttypes=1\tinstances=0"]
    for i in range(nested):
        lines.append(f"ROW\tkind=nested\tfamily=Family '{spec['name']}'\tname=Pole : Pole\tcategory=Generic Models\twhere=(0, 0, 0) m")
    for p in spec["ports"][skip_connectors:]:
        lines.append(f"ROW\tkind=connector\tfamily=Family '{spec['name']}'\tscope=family\tdomain={DOMAINS[p['kind']]}\tsystem=X\tsize=dia 40 mm\tflow=Out\tdir=1,0,0\torigin=0,0,0")
    if fail:
        lines.append(f"FAIL\t{fail}")
    lines.append(f"COUNT\tfail\t{1 if fail else 0}")
    return "\n".join(lines)


class World:
    """The module wired like the server: manifest, provider, approval gate, and a fake Revit that answers write and read scripts."""

    def __init__(self, tmp_path, monkeypatch, mode="ask_first"):
        self.tmp_path = tmp_path
        self.inst = ModuleInstance(ModuleManifest(**json.loads((fam.MODULE_DIR / "module.json").read_text(encoding="utf-8"))), fam.MODULE_DIR)
        monkeypatch.setattr(self.inst.code_module, "_server_in_mock_mode", lambda: False)
        monkeypatch.setattr(self.inst.code_module.revit_module(), "_server_in_mock_mode", lambda: False)
        modules = SimpleNamespace(get_all_modules=lambda: [self.inst], config=SimpleNamespace(allow_python_host=False))
        self.gate = ApprovalGate(tmp_path, mode)
        self.calls: List[Any] = []
        self.build_text = build_output([PANEL])
        self.probes: Dict[int, Any] = {}
        self.build_raw: Any = None
        world = self

        class FakeRevit:
            async def execute_tool(self, name, arguments):
                world.calls.append((name, arguments))
                if arguments.get("mode") == "write":
                    return world.build_raw if world.build_raw is not None else {"success": True, "output": world.build_text}
                found = re.search(r"'ids': \[(\d+)\]", arguments["script"])
                answer = world.probes.get(int(found.group(1))) if found else None
                if isinstance(answer, Exception):
                    raise answer
                return {"success": True, "output": answer if answer is not None else "SUMMARY\tnothing"}

            def call_is_read_only(self, name, arguments):
                return arguments.get("mode") == "read"

        self.revit = FakeRevit()
        self.provider = ModuleProvider(modules, WorkspaceMonitor([tmp_path]))
        capabilities = {tool.name: tool for tool in self.provider.get_capabilities()}
        capabilities["revit_execute_python"] = SimpleNamespace(is_mutating=True)
        self.capabilities = capabilities
        self.registry = SimpleNamespace(
            lookup_tool=lambda name: capabilities.get(name),
            lookup_tool_provider=lambda name: self.provider if name in capabilities and name != "revit_execute_python" else self.revit,
            get_provider=lambda name: SimpleNamespace(gate=self.gate) if name == "approval" else None,
        )
        self.provider.tool_registry = self.registry

    def args(self, *specs, **extra) -> Dict[str, Any]:
        return {"specs": list(specs) or [PANEL], "output_dir": str(self.tmp_path / "families"), **extra}

    def approve(self, arguments):
        plan = self.gate.create_plan([{"tool": "revit_make_family", "arguments": arguments}], [{}])
        human_approve(self.gate, plan["plan_id"])
        return plan["plan_id"]

    def run(self, arguments, *, approved: bool = True):
        if approved:
            arguments = {**arguments, "plan_id": self.approve(arguments)}
        return asyncio.run(run_gated_tool(self.registry, self.gate, "revit_make_family", arguments))

    def writes(self):
        return [c for c in self.calls if c[1].get("mode") == "write"]

    def reads(self):
        return [c for c in self.calls if c[1].get("mode") == "read"]


@pytest.fixture(autouse=True)
def _not_in_mock_mode(monkeypatch):
    monkeypatch.setattr(fam, "_server_in_mock_mode", lambda: False)


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch)
    w.probes[501] = probe_output(PANEL, 501)
    return w


# ----- manifest and registration ---------------------------------------------- #
def test_public_tool_name_and_write_flags(world):
    assert "revit_make_family" in world.capabilities and not any(n.startswith("revit_family_") for n in world.capabilities)
    cmd = world.inst.manifest.commands[0]
    assert cmd.mcp_tool == "revit_make_family" and cmd.is_mutating and cmd.requires_plan and not cmd.destructive
    assert world.capabilities["revit_make_family"].is_mutating is True


def test_every_parameter_is_documented_and_descriptions_are_short():
    manifest = json.loads((fam.MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    schema = manifest["commands"][0]["input_schema"]
    missing: List[str] = []

    def walk(node: Dict[str, Any], path: str) -> None:
        for key, prop in (node.get("properties") or {}).items():
            where = f"{path}.{key}"
            if not str(prop.get("description", "")).strip():
                missing.append(where)
            if len(str(prop.get("description", ""))) > 520:
                missing.append(where + " (too long)")
            if prop.get("type") == "object":
                walk(prop, where)
            if prop.get("type") == "array" and isinstance(prop.get("items"), dict) and prop["items"].get("type") == "object":
                walk(prop["items"], where + "[]")

    walk(schema, "input")
    assert not missing
    assert schema["required"] == ["specs", "output_dir"]
    spec = schema["properties"]["specs"]["items"]
    assert set(spec["properties"]) == fam.SPEC_KEYS and set(spec["properties"]["ports"]["items"]["properties"]) == fam.PORT_KEYS
    assert len(manifest["description"]) < 400
    assert "revit_execute_python" in schema["properties"]["specs"]["description"]


def test_no_conflict_markers_in_the_module():
    for path in [*fam.MODULE_DIR.rglob("*.py"), *fam.MODULE_DIR.rglob("*.ipy"), *fam.MODULE_DIR.rglob("*.json")]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^(<<<<<<<|>>>>>>>|=======$)", text, re.M), path


# ----- approval gating -------------------------------------------------------- #
def test_the_write_is_approval_gated(world):
    arguments = world.args()
    with pytest.raises(Exception, match="(?i)plan|approv"):
        asyncio.run(run_gated_tool(world.registry, world.gate, "revit_make_family", arguments))
    assert world.calls == []
    # Even a call to the provider itself, outside the gate, cannot reach Revit.
    result = asyncio.run(world.provider.execute_tool("revit_make_family", arguments))
    assert result["ok"] is False and world.calls == []


def test_an_approved_plan_runs_one_write_and_one_probe_and_is_booked_executed(world):
    arguments = world.args()
    pid = world.approve(arguments)
    result = asyncio.run(run_gated_tool(world.registry, world.gate, "revit_make_family", {**arguments, "plan_id": pid}))
    assert result["ok"] is True and result["verified"] is True
    assert [c[0] for c in world.calls] == ["revit_execute_python", "revit_execute_python"]
    assert len(world.writes()) == 1 and len(world.reads()) == 1
    assert world.gate.load_plan(pid)["actions"][0]["state"] == "executed"
    # the same approved plan cannot be used twice
    with pytest.raises(Exception):
        asyncio.run(run_gated_tool(world.registry, world.gate, "revit_make_family", {**arguments, "plan_id": pid}))


def test_look_only_mode_refuses_before_revit(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, mode="look_only")
    with pytest.raises(Exception, match="Look only"):
        asyncio.run(run_gated_tool(w.registry, w.gate, "revit_make_family", w.args()))
    assert w.calls == []


def test_auto_mode_needs_no_plan(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, mode="auto")
    w.probes[501] = probe_output(PANEL, 501)
    assert w.run(w.args(), approved=False)["ok"] is True


# ----- the result contract ---------------------------------------------------- #
def test_success_result_reports_template_changed_ids_post_check_and_probe_verdict(world):
    result = world.run(world.args())
    assert result["ok"] is True and result["changed_ids"] == [501]
    assert result["template"] == TEMPLATE and result["templates"] == [TEMPLATE]
    assert result["rows"][0]["template"] == TEMPLATE and result["rows"][0]["template_kind"] == "category" and result["rows"][0]["id"] == 501
    post = result["post_check"]
    assert post["ok"] is True and post["failed"] == 0 and post["checked"] >= 6
    names = {c["check"] for c in post["checks"]}
    assert {"probe_ran:AMB2_Panel", "probe_nested_instances:AMB2_Panel", "probe_category:AMB2_Panel", "probe_connectors:AMB2_Panel", "probe_fails:AMB2_Panel", "category:AMB2_Panel"} <= names
    verdict = result["probe"][0]
    assert verdict["verdict"] == "PASS" and verdict["nested_instances"] == 0 and verdict["category"] == "Electrical Equipment" and verdict["category_ok"] is True
    assert len(verdict["connectors"]) == 1 and verdict["connectors"][0]["domain"] == "DomainElectrical"
    assert result["post_check"]["probe"] == result["probe"]
    assert result["warnings_dismissed"] == 1 and any("REVIT_WARNING_DISMISSED" in i for i in result["info"])
    assert result["outcome"] == "ok" and result["on_error"] == "abort"


def test_the_probe_is_the_existing_tool_run_by_id_in_read_mode_with_the_nested_guard_on(world):
    world.run(world.args())
    script = world.reads()[0][1]["script"]
    assert "revit_probe_family" in script and "'ids': [501]" in script and "'deep': True" in script and "'allow_nested': False" in script
    assert world.reads()[0][1]["mode"] == "read"


def test_the_write_script_gets_the_checked_spec_template_and_paths(world, tmp_path):
    world.run(world.args(HEAT, on_error="skip", replace=True, template_path=str(tmp_path / "t.rft")))
    script = world.writes()[0][1]["script"]
    out_dir = str((tmp_path / "families").resolve()).replace("\\", "\\\\")
    assert "u'AMB2_Heat'" in script and "u'hsup'" in script and "u'skip'" in script and "replace': True" in script
    assert out_dir in script
    assert str((tmp_path / "t.rft").resolve()).replace("\\", "\\\\") in script
    compile(script, "built", "exec")


def test_probe_finding_a_nested_instance_makes_the_call_fail_but_keeps_the_ids(world):
    world.probes[501] = probe_output(PANEL, 501, nested=1, fail="FAMILY_NESTED: Family 'AMB2_Panel' contains a nested instance Pole : Pole")
    result = world.run(world.args())
    assert result["ok"] is False and result["kind"] == "post_check_failed"
    assert result["changed_ids"] == [501]
    assert result["post_check"]["ok"] is False and result["post_check"]["failed"] >= 2
    assert result["probe"][0]["verdict"] == "FAIL" and result["probe"][0]["nested_instances"] == 1
    assert "FAMILY_NESTED" in result["message"] or any("nested" in f for f in result["fails"])
    assert result["summary"].startswith("FAILED")


def test_probe_with_the_wrong_category_or_missing_connectors_fails(world):
    world.probes[501] = probe_output(PANEL, 501, category="Generic Models", skip_connectors=1)
    result = world.run(world.args())
    failed = {c["check"] for c in result["post_check"]["checks"] if not c["ok"]}
    assert result["ok"] is False and {"probe_category:AMB2_Panel", "probe_connectors:AMB2_Panel"} <= failed


def test_a_localised_category_name_passes_when_the_script_verified_the_category_by_id(world):
    world.probes[501] = probe_output(PANEL, 501, category="Elektrische apparatuur")
    result = world.run(world.args())
    assert result["ok"] is True and result["probe"][0]["category"] == "Elektrische apparatuur"


def test_a_probe_that_cannot_run_is_a_failed_check_never_a_silent_pass(world):
    world.probes[501] = RuntimeError("Revit is busy")
    result = world.run(world.args())
    assert result["ok"] is False and result["kind"] == "post_check_failed" and result["changed_ids"] == [501]
    check = next(c for c in result["post_check"]["checks"] if c["check"] == "probe_ran:AMB2_Panel")
    assert check["ok"] is False and "Revit is busy" in check["detail"]
    assert result["probe"][0]["verdict"] == "UNVERIFIED"


def test_a_failed_script_post_check_is_never_ok_true(world):
    world.build_text = build_output([PANEL]) + "\nROW\trow_type=post\tcheck=types:AMB2_Panel\tok=0\tdetail=0 type(s)\nFAIL\tPOST_CHECK_FAILED\ttypes:AMB2_Panel: 0 type(s)\nCOUNT\tfail\t1"
    result = world.run(world.args())
    assert result["ok"] is False and result["post_check"]["ok"] is False


def test_template_not_found_is_a_loud_refusal_with_nothing_changed_and_no_probe(world):
    message = "no family template found for category 'elec_eq' (looked for a file name with 'electrical equipment' or 'generic model'; Revit reports no family template folder). Pass template_path"
    world.build_text = f"SUMMARY\tx\nFAIL\tTEMPLATE_NOT_FOUND\t{message}\nMETA\toutcome\ttemplate_not_found\nMETA\tchanged_ids\t\nCOUNT\tfail\t1"
    result = world.run(world.args())
    assert result["ok"] is False and result["kind"] == "template_not_found" and result["changed_ids"] == []
    assert "no family template found" in result["message"] and "template_path" in result["hint"]
    assert world.reads() == []


def test_a_rolled_back_call_reports_nothing_changed_and_skips_the_probe(world):
    world.build_text = ("SUMMARY\tx\nFAIL\tSTEP_FAILED\tBuild family 'AMB2_Heat': connector size\nMETA\toutcome\trolled_back\nMETA\ton_error\tabort\n"
                        "META\tchanged_ids\t\nMETA\tfailed_ids\t\nCOUNT\tfail\t1")
    result = world.run(world.args())
    assert result["ok"] is False and result["kind"] == "rolled_back" and result["changed_ids"] == []
    assert "rolled back" in result["summary"] and world.reads() == []


def test_skip_mode_partial_failure_keeps_what_worked_and_probes_only_that(world):
    text = build_output([PANEL]) + "\nFAIL\tSTEP_FAILED\tBuild family 'AMB2_Heat': flow direction not set\nCOUNT\tfail\t1"
    world.build_text = text.replace("META\toutcome\tok", "META\toutcome\tpartial_failure")
    result = world.run(world.args(HEAT, PANEL, on_error="skip"))
    assert result["ok"] is False and result["kind"] == "partial_failure" and result["changed_ids"] == [501]
    assert len(world.reads()) == 1 and [v["family"] for v in result["probe"]] == ["AMB2_Panel"]


def test_two_families_are_probed_one_by_one(world):
    world.build_text = build_output([HEAT, PANEL], ids={"AMB2_Heat": 601, "AMB2_Panel": 501})
    world.probes[601] = probe_output(HEAT, 601)
    result = world.run(world.args(HEAT, PANEL))
    assert result["ok"] is True and [v["family"] for v in result["probe"]] == ["AMB2_Heat", "AMB2_Panel"]
    assert len(world.reads()) == 2 and result["changed_ids"] == [601, 501]


def test_script_error_and_bridge_errors_are_structured(world):
    world.build_raw = {"success": False, "error": "SyntaxError in line 3"}
    result = world.run(world.args())
    assert result["ok"] is False and result["kind"] == "script_error" and "SyntaxError" in result["message"]
    world.build_raw = {"success": True, "output": "ERROR\tscript_exception\tRuntimeError: boom\nMETA\toutcome\trolled_back\nCOUNT\tfail\t0"}
    result = world.run(world.args())
    assert result["ok"] is False and result["kind"] == "script_exception" and result["post_check"] is None and world.reads() == []


def test_running_receipt_is_passed_through_and_not_probed(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch)
    w.build_raw = {"status": "running", "request_id": "11223344-5566-7788-99aa-bbccddeeff00"}
    result = w.run(w.args())
    assert result["status"] == "running" and result["verified"] is False and w.reads() == []


def test_mock_mode_never_looks_like_a_pass(world, monkeypatch):
    monkeypatch.setattr(world.inst.code_module, "_server_in_mock_mode", lambda: True)
    result = world.inst.code_module.RevitFamilyModule().make_family(**world.args(), workspace=WorkspaceMonitor([world.tmp_path]), approved_executor=lambda *a: pytest.fail("must not call Revit"))
    assert result["mock"] is True and result["verified"] is False and result["changed_ids"] == []


def test_fail_lines_cannot_be_turned_into_success():
    parsed = fam.parse_script_output("SUMMARY\tx\nFAIL\tPOST\tfailed\nMETA\toutcome\tok\nCOUNT\tfail\t1")
    assert fam._finish_write("revit_make_family", parsed, 1, None)["ok"] is False


# ----- guards before anything reaches Revit ------------------------------------ #
def direct(world_or_path, **kwargs):
    """Call the module directly with an executor that fails the test when Revit would be reached."""
    root = world_or_path.tmp_path if isinstance(world_or_path, World) else world_or_path
    reached: List[Any] = []
    module = fam.RevitFamilyModule()
    args = {"output_dir": str(root / "families"), "specs": [PANEL]}
    args.update(kwargs)
    result = module.make_family(workspace=WorkspaceMonitor([root]), approved_executor=lambda *a: reached.append(a), **args)
    return result, reached


@pytest.mark.parametrize("spec,fragment", [
    # category guard
    (dict(PANEL, category="mech"), "needs at least one pipe or duct port"),
    (dict(HEAT, category="elec_eq"), "takes elec connectors, but the ports include duct/pipe"),
    (dict(HEAT, category="plumb"), "takes pipe/elec connectors, but the ports include duct"),
    (dict(HEAT, category="air"), "takes duct/elec connectors, but the ports include pipe"),
    (dict(HEAT, category="light"), "takes elec connectors"),
    (dict(HEAT, category="elec_fx"), "takes elec connectors"),
    (dict(HEAT, category="mech", ports=[]), "needs at least one pipe or duct port"),
    (dict(HEAT, category="plumb", ports=[HEAT["ports"][2]]), "takes pipe/elec connectors"),
])
def test_category_guard_refuses_a_category_that_does_not_fit_the_ports(tmp_path, spec, fragment):
    result, reached = direct(tmp_path, specs=[spec])
    assert result["ok"] is False and result["kind"] == "category_mismatch" and fragment in result["message"]
    assert reached == []


def test_category_guard_accepts_the_fitting_combinations(tmp_path):
    ok = [dict(HEAT), dict(PANEL), dict(PANEL, category="light"), dict(PANEL, category="elec_fx"),
          dict(HEAT, category="plumb", ports=HEAT["ports"][:2]), dict(HEAT, category="air", ports=[HEAT["ports"][2]]),
          dict(HEAT, category="mech", ports=HEAT["ports"][:1] + PANEL["ports"]), dict(PANEL, ports=[], name="Empty")]
    for i, spec in enumerate(ok):
        assert fam.validate_spec(spec, i)["category"] == spec["category"]


def test_the_electrical_alias_is_accepted_and_normalised():
    spec = dict(PANEL, ports=[dict(PANEL["ports"][0], kind="electrical")])
    assert fam.validate_spec(spec, 0)["ports"][0]["kind"] == "elec"


@pytest.mark.parametrize("mutate,fragment", [
    (lambda s: s.update(name=""), "name is required"),
    (lambda s: s.update(name="a/b"), "not allowed in a file name"),
    (lambda s: s.update(name="C:\\evil"), "not allowed in a file name"),
    (lambda s: s.update(name="x" * 101), "longer than 100"),
    (lambda s: s.update(name="dot."), "must not end with a dot"),
    (lambda s: s.update(category="boiler"), "category must be one of"),
    (lambda s: s.update(category=None), "category must be one of"),
    (lambda s: s.update(w=0), "w must be greater than 0"),
    (lambda s: s.update(d=-1), "d must be greater than 0"),
    (lambda s: s.update(h=float("nan")), "h must be a finite number"),
    (lambda s: s.update(h="tall"), "h must be a finite number"),
    (lambda s: s.update(w=500), "out of range"),
    (lambda s: s.update(w=None), "w must be a finite number"),
    (lambda s: s.update(colour="red"), "unknown keys: colour"),
    (lambda s: s.update(ports="none"), "ports must be a list"),
    (lambda s: s.update(ports=[1]), "must be an object"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], bogus=1)]), "unknown keys: bogus"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], kind="gas")]), "kind must be one of"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], dir="up")]), "dir must be one of"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], pos=[0, 0])]), "pos must be a list of 3 numbers"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], pos=[0, 0, "x"])]), "pos must be a finite number"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], system="steam")]), "system must be one of"),
    (lambda s: s.update(ports=[{k: v for k, v in HEAT["ports"][0].items() if k != "dia_mm"}]), "dia_mm is required"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], dia_mm=0)]), "dia_mm must be greater than 0"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], dia_mm=100000)]), "dia_mm is out of range"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], flow="sideways")]), "flow must be one of"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], label="caf\u00e9")]), "label must be"),
    (lambda s: s.update(ports=[HEAT["ports"][0], HEAT["ports"][0]]), "repeats ports[0]"),
    (lambda s: s.update(ports=[dict(HEAT["ports"][0], pos=[i / 100, 0, 1]) for i in range(41)]), "at most 40"),
    (lambda s: s.update(category="elec_eq", ports=[dict(PANEL["ports"][0], dia_mm=40)]), "dia_mm does not apply"),
    (lambda s: s.update(category="elec_eq", ports=[dict(PANEL["ports"][0], flow="in")]), "flow does not apply"),
])
def test_bad_specs_are_rejected_before_revit(tmp_path, mutate, fragment):
    spec = json.loads(json.dumps(HEAT))
    mutate(spec)
    result, reached = direct(tmp_path, specs=[spec])
    assert result["ok"] is False and result["kind"] in ("invalid_input", "category_mismatch") and fragment in result["message"], result
    assert reached == [] and "Nothing was sent to Revit" in result["hint"]


@pytest.mark.parametrize("kwargs,fragment", [
    ({"specs": None}, "specs must be a list"),
    ({"specs": []}, "specs must be a list"),
    ({"specs": "x"}, "specs must be a list"),
    ({"specs": [dict(PANEL, name="n%d" % i) for i in range(6)]}, "at most 5 families"),
    ({"specs": [PANEL, dict(PANEL, name="amb2_PANEL")]}, "repeats the name"),
    ({"on_error": "ignore"}, "on_error must be one of"),
    ({"output_dir": ""}, "output_dir is required"),
    ({"output_dir": None}, "output_dir is required"),
    ({"template_path": "t.txt"}, "must be the path of a .rft"),
    ({"template_path": 5}, "must be the path of a .rft"),
])
def test_bad_call_arguments_are_rejected_before_revit(tmp_path, kwargs, fragment):
    result, reached = direct(tmp_path, **kwargs)
    assert result["ok"] is False and result["kind"] == "invalid_input" and fragment in result["message"], result
    assert reached == []


def test_a_second_bad_spec_in_a_batch_stops_the_whole_call(tmp_path):
    result, reached = direct(tmp_path, specs=[PANEL, dict(HEAT, w=-1)])
    assert result["ok"] is False and "specs[1] 'AMB2_Heat'" in result["message"] and reached == []


# ----- path sandbox ------------------------------------------------------------ #
def test_output_dir_outside_the_workspace_is_refused(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    result, reached = direct(ws, output_dir=str(tmp_path / "elsewhere"))
    assert result["ok"] is False and result["kind"] == "path_outside_workspace" and reached == []
    assert "workspace" in result["hint"]


def test_output_dir_with_dotdot_escape_is_refused(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    result, reached = direct(ws, output_dir=str(ws / ".." / "escape"))
    assert result["kind"] == "path_outside_workspace" and reached == []


def test_template_path_outside_the_workspace_is_refused(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    result, reached = direct(ws, template_path=str(tmp_path / "Metric Generic Model.rft"))
    assert result["ok"] is False and result["kind"] == "path_outside_workspace" and reached == []


def test_template_path_inside_the_workspace_is_passed_on_and_no_workspace_means_no_write(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    result, reached = direct(ws, template_path=str(ws / "mine.rft"))
    assert len(reached) == 1                              # validation passed; the (fake) executor was reached once
    module = fam.RevitFamilyModule()
    result = module.make_family(specs=[PANEL], output_dir=str(ws), workspace=None, approved_executor=lambda *a: pytest.fail("no workspace, no write"))
    assert result["kind"] == "path_outside_workspace" and "no workspace is configured" in result["message"]


def test_without_an_approved_executor_a_write_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(fam, "_server_in_mock_mode", lambda: False)
    result = fam.RevitFamilyModule().make_family(specs=[PANEL], output_dir=str(tmp_path), workspace=WorkspaceMonitor([tmp_path]), approved_executor=None)
    assert result["ok"] is False and result["kind"] == "no_bridge"


# ----- the villa2 recipe data -------------------------------------------------- #
def test_every_family_of_the_villa2_recipe_passes_the_guards():
    specs = json.loads((ROOT / "docs" / "recipes" / "villa2" / "m1_specs.json").read_text(encoding="utf-8"))
    assert len(specs) == 21
    for i, spec in enumerate(specs):
        clean = fam.validate_spec(spec, i)
        assert clean["name"] == spec["name"] and len(clean["ports"]) == len(spec["ports"])
    assert [s["category"] for s in specs if s["category"] == "elec_eq"] and fam.py2_literal(specs[0]).startswith("{")


def test_py2_literal_strings_are_unicode_literals_and_numbers_must_be_finite():
    assert fam.py2_literal("caf\u00e9 'x'") == "u'caf\\u00e9 \\'x\\''"
    with pytest.raises(ValueError):
        fam.py2_literal(float("inf"))
