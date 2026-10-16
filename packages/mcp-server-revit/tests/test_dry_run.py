"""dry_run of the write tools of revit_docs, revit_family and revit_mep.

A dry run does the whole call inside the TransactionGroup exactly as normal, then ALWAYS rolls the group back and reports
dry_run true, committed false and would_change. It never leaves a model change, a family file or an export file behind,
and it is approval-gated like any write. The scripts run against the stubs of the Revit API (tests/revit_mep_stub.py with
its undo journal, tests/revit_api_stub.py for families), not against Revit: live behaviour is UNVERIFIED.
"""
from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import revit_api_stub as stub  # noqa: E402
import revit_mep_stub as rs  # noqa: E402
from helpers import human_approve  # noqa: E402
from revit_mcp_server.check_contract import parse_script_output  # noqa: E402
from revit_mcp_server.errors import BridgeError  # noqa: E402
from revit_mcp_server.module_registry import ModuleInstance, ModuleManifest  # noqa: E402
from revit_mcp_server.modules.revit_docs import module as docs  # noqa: E402
from revit_mcp_server.modules.revit_family import module as fam  # noqa: E402
from revit_mcp_server.modules.revit_mep import module as mep  # noqa: E402
from revit_mcp_server.providers.module_provider import ModuleProvider  # noqa: E402
from revit_mcp_server.security.approval import ApprovalGate  # noqa: E402
from revit_mcp_server.security.dispatch import run_gated_tool  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402
from test_revit_mep_scripts import Env, build_scene, r_bend, r_straight, route_args  # noqa: E402

WRITE_TOOLS = {
    "revit_docs": ("revit_make_view", "revit_make_sheet", "revit_make_schedule", "revit_export", "revit_place_views",
                   "revit_apply_view_template", "revit_make_view_template", "revit_align_crop", "revit_add_revision",
                   "revit_add_revision_clouds", "revit_issue_revision", "revit_update_sheets"),
    "revit_family": ("revit_make_family",),
    "revit_mep": ("revit_mep_route", "revit_mep_connect", "revit_mep_circuit", "revit_mep_hanger_place"),
}
MODULE_DIRS = {"revit_docs": docs.MODULE_DIR, "revit_family": fam.MODULE_DIR, "revit_mep": mep.MODULE_DIR}


# --------------------------------------------------------------------------- #
# Manifests
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("module_id", sorted(WRITE_TOOLS))
def test_every_write_tool_documents_dry_run_and_read_tools_do_not_take_it(module_id):
    data = json.loads((MODULE_DIRS[module_id] / "module.json").read_text(encoding="utf-8"))
    seen = set()
    for cmd in data["commands"]:
        props = cmd["input_schema"]["properties"]
        if cmd["is_mutating"]:
            seen.add(cmd["mcp_tool"])
            spec = props["dry_run"]
            assert spec["type"] == "boolean" and spec["default"] is False
            assert "approved plan" in spec["description"] and len(spec["description"]) > 80
        else:
            assert "dry_run" not in props
    assert seen == set(WRITE_TOOLS[module_id])


# --------------------------------------------------------------------------- #
# The shared Runner (revit_docs/_write_prelude.ipy, also used by revit_mep)
# --------------------------------------------------------------------------- #
def load_prelude(names, env):
    path = docs.SCRIPT_DIR / "_write_prelude.ipy"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), env)
    return env


class Group:
    def __init__(self, doc, title):
        self.calls: List[str] = []
        self.started = False

    def Start(self):
        self.started = True

    def HasStarted(self):
        return self.started

    def RollBack(self):
        self.calls.append("rollback")
        return "rolled_back"

    def Assimilate(self):
        self.calls.append("assimilate")
        return "committed"


def runner_env(dry_run: Any):
    records: List[tuple] = []
    env = {"TransactionStatus": SimpleNamespace(Committed="committed", RolledBack="rolled_back"), "TransactionGroup": Group,
           "doc": None, "RUN": [None], "meta": lambda *a: records.append(("meta",) + a),
           "fail": lambda *a: records.append(("fail",) + a), "info": lambda *a: None}
    if dry_run is not None:
        env["ARGS"] = {"dry_run": dry_run}
    load_prelude({"Runner", "StepError", "dry_run_requested"}, env)
    return env, records


def metas(records):
    return {r[1]: r[2] for r in records if r[0] == "meta"}


def test_runner_dry_run_always_rolls_back_and_reports_what_would_change():
    env, records = runner_env(True)
    run = env["Runner"]("t", "abort")
    run.changed.extend([12, 13])
    run.close()
    assert run.group.calls == ["rollback"] and run.outcome == "ok" and run.changed == []
    m = metas(records)
    assert m["dry_run"] == 1 and m["committed"] == 0 and m["changed_ids"] == "" and m["would_change_ids"] == "12,13"


def test_runner_dry_run_in_skip_mode_reports_the_partial_outcome_but_still_rolls_back():
    env, records = runner_env(True)
    run = env["Runner"]("t", "skip")
    run.changed.append(5)
    run.failed_steps.append("step 2")
    run.close()
    assert run.group.calls == ["rollback"] and run.outcome == "partial_failure"
    assert metas(records)["would_change_ids"] == "5"


def test_runner_without_dry_run_still_assimilates():
    for value in (None, False):
        env, records = runner_env(value)
        run = env["Runner"]("t", "abort")
        run.changed.append(7)
        run.close()
        assert run.group.calls == ["assimilate"] and metas(records)["changed_ids"] == "7"
        assert "dry_run" not in metas(records)


# --------------------------------------------------------------------------- #
# revit_mep against the stub with an undo journal: the model is unchanged after a dry run
# --------------------------------------------------------------------------- #
@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(mep, "_server_in_mock_mode", lambda: False)
    revit_module = sys.modules[mep._revit_module_class().__module__]
    monkeypatch.setattr(revit_module, "_server_in_mock_mode", lambda: False)
    with rs.installed_mep(monkeypatch) as world:
        yield Env(world, build_scene(world), tmp_path)


def test_route_dry_run_does_all_the_work_then_leaves_the_model_unchanged(env):
    before = env.w.snapshot()
    result = env.route(**route_args(r_bend(), dry_run=True))
    assert result["ok"] is True, result
    assert result["dry_run"] is True and result["committed"] is False and result["changed_ids"] == []
    would = result["would_change"]
    assert would["outcome"] == "ok" and would["element_count"] == 5  # 3 pipes and 2 elbows, as in the real run
    assert result["post_check"]["ok"] is True and result["post_check"]["checked"] > 0  # the checks ran inside the group
    assert result["summary"].startswith("DRY RUN, nothing was changed")
    assert "dry_run false" in result["hint"]
    # the undo journal is empty again and the model is as it was
    assert env.w.snapshot() == before and env.w.journal == [] and env.owned() == []
    assert not env.s["hp"].MEPModel.ConnectorManager.Connectors[0].IsConnected
    log = env.w.txn_log
    assert log[0][0] == "group_start" and log[-1][0] == "group_rollback"
    assert not any(kind == "group_assimilate" for kind, _ in log)
    assert [n for kind, n in log if kind == "commit"] == ["Route r2"]  # the step itself committed inside the group
    assert env.bridge.modes == ["write"]  # no system report on rolled-back elements
    assert result["system_report"]["ran"] is False


def test_a_dry_run_and_then_the_real_run_give_the_same_pieces(env):
    dry = env.route(**route_args(r_bend(), dry_run=True))
    real = env.route(**route_args(r_bend()))
    assert real["ok"] is True and real["dry_run"] is False and real["committed"] is True
    assert len(real["changed_ids"]) == dry["would_change"]["element_count"]
    assert len(env.owned()) == 5


def test_dry_run_reports_a_failure_a_real_run_would_hit_and_changes_nothing(env):
    before = env.w.snapshot()
    env.w.fail_on["create_pipe"] = lambda n: n == 2
    a = r_straight("a")
    b = r_straight("b", **{"from": {"mark": "RAD"}, "to": {"mark": "MAN", "sort": "y", "index": 0}})
    result = env.route(**route_args(a, b, dry_run=True))
    assert result["ok"] is False and result["kind"] == "rolled_back" and result["dry_run"] is True
    assert "Revit refused create_pipe" in result["message"] and result["changed_ids"] == []
    assert env.w.snapshot() == before and env.w.journal == []


def test_dry_run_in_skip_mode_says_what_would_be_kept(env):
    env.w.fail_on["create_pipe"] = lambda n: n == 2
    a = r_straight("a")
    b = r_straight("b", **{"from": {"mark": "RAD"}, "to": {"mark": "MAN", "sort": "y", "index": 0}})
    result = env.route(**route_args(a, b, on_error="skip", dry_run=True))
    assert result["ok"] is False and result["kind"] == "partial_failure"
    assert result["would_change"]["element_count"] == 1 and result["changed_ids"] == []
    assert env.owned() == [] and env.w.journal == []


def test_connect_and_circuit_dry_runs_leave_nothing(env):
    before = env.w.snapshot()
    circuit = env.circuit(tag="MEP1", dry_run=True, circuits=[
        {"id": "C1", "name": "C1 Lighting", "panel": {"mark": "PANEL"}, "elements": [{"mark": "LT1"}, {"mark": "LT2"}]}])
    assert circuit["ok"] is True and circuit["dry_run"] is True and circuit["would_change"]["element_count"] == 1, circuit
    assert not [e for e in env.w.elements if isinstance(e, rs.StubElectricalSystem)]
    assert env.s["lt1"].circuits == [] and env.w.snapshot() == before and env.w.journal == []


def test_dry_run_must_be_a_real_boolean(env):
    result = env.route(**route_args(r_straight(), dry_run="false"))
    assert result["ok"] is False and result["kind"] == "invalid_input" and "dry_run" in result["message"]
    assert env.bridge.modes == []


def test_a_dry_run_that_reports_a_commit_is_never_ok():
    out = ("SUMMARY\tbuilt\nMETA\toutcome\tok\nMETA\tchanged_ids\t12\nMETA\tcommitted\t1\n"
           "ROW\trow_type=post\tcheck=x\tok=1\tdetail=y\nCOUNT\tfail\t0")
    for module in (docs, mep):
        result = module._finish_write("t", parse_script_output(out), 1, None, dry_run=True)
        assert result["ok"] is False and result["kind"] == "dry_run_not_honoured" and result["changed_ids"] == []
    result = fam._finish_write("t", parse_script_output(out), 1, None, dry_run=True)
    assert result["ok"] is False and result["kind"] == "dry_run_not_honoured"


# --------------------------------------------------------------------------- #
# revit_family: nothing on disk, nothing loaded
# --------------------------------------------------------------------------- #
PANEL = {"name": "AMB2_Panel", "category": "elec_eq", "w": 0.5, "d": 0.15, "h": 0.7,
         "ports": [{"pos": [0, 0.08, 0.3], "dir": "+y", "kind": "elec", "system": "power", "label": "feed"}]}


def family_setup(tmp_path):
    templates = tmp_path / "Family Templates"
    templates.mkdir()
    (templates / "Metric Electrical Equipment.rft").write_bytes(b"RFT")
    app = stub.FakeApp(str(templates))
    return app, stub.ProjectDoc(app), tmp_path / "families"


def test_family_dry_run_builds_and_checks_but_writes_no_file_and_loads_nothing(tmp_path, monkeypatch):
    app, doc, out = family_setup(tmp_path)
    args = {"specs": [fam.validate_spec(PANEL, 0)], "output_dir": str(out), "template_path": "", "replace": False,
            "on_error": "abort", "dry_run": True}
    with stub.install_family_write_api(monkeypatch):
        parsed = parse_script_output(stub.run_script(fam.build_script("make_family.ipy", args, write=True), doc, app))
    assert parsed.meta["outcome"] == "ok" and parsed.meta["dry_run"] == "1" and parsed.meta["committed"] == "0", parsed.fails
    assert not out.exists() and app.saved == {} and doc.load_calls == []
    assert [e for e in doc.elements if isinstance(e, stub.Family)] == []
    assert [fd.closed for fd in app.family_docs] == [True] and app.family_docs[0].saved_to is None
    assert doc.group_log == ["RolledBack"]
    row = next(r for r in parsed.rows if r.get("kind") == "family")
    assert row["status"] == "would_create" and row["would_write"] == str(out / "AMB2_Panel.rfa")
    assert any(r.get("check") == "connectors_built:AMB2_Panel" and r["ok"] == "1" for r in parsed.rows)


def test_family_dry_run_result_skips_the_probe_and_names_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fam, "_server_in_mock_mode", lambda: False)
    app, doc, out = family_setup(tmp_path)
    calls: List[str] = []

    def bridge(name: str, args: Dict[str, Any]) -> Any:
        calls.append(args["mode"])
        with stub.install_family_write_api(monkeypatch):
            return {"success": True, "output": stub.run_script(args["script"], doc, app)}

    result = fam.RevitFamilyModule().make_family(specs=[PANEL], output_dir=str(out), dry_run=True,
                                                 workspace=WorkspaceMonitor([tmp_path]), approved_executor=bridge)
    assert result["ok"] is True and result["dry_run"] is True and result["committed"] is False, result
    assert result["changed_ids"] == [] and result["probe"] == [] and calls == ["write"]
    assert result["would_change"]["files"] == [str(out / "AMB2_Panel.rfa")]
    assert any("PROBE_SKIPPED" in i for i in result["info"]) and not out.exists()


# --------------------------------------------------------------------------- #
# revit_docs: export never exports, the module plumbs dry_run into the script
# --------------------------------------------------------------------------- #
def export_env(tmp_path, args):
    made: List[str] = []
    exported: List[Any] = []
    records: List[tuple] = []

    class Directory:
        Exists = staticmethod(lambda p: Path(p).is_dir())
        CreateDirectory = staticmethod(lambda p: made.append(p))

    env = {
        "ARGS": args, "doc_meta": lambda: None, "Directory": Directory,
        "File": SimpleNamespace(Exists=lambda p: Path(p).is_file()),
        "IoPath": SimpleNamespace(Combine=lambda a, b: str(Path(a) / b)),
        "doc": SimpleNamespace(Export=lambda *a: exported.append(a) or True),
        "meta": lambda *a: records.append(("meta",) + a), "item": lambda pairs: records.append(("item", dict(pairs))),
        "summary": lambda text: records.append(("summary", text)), "refuse": lambda *a: records.append(("refuse",) + a),
    }
    path = docs.SCRIPT_DIR / "export.ipy"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), env)
    load_prelude({"dry_run_requested"}, env)
    return env, made, exported, records


def test_export_dry_run_reports_the_target_and_writes_nothing(tmp_path):
    folder = tmp_path / "out"
    args = {"format": "ifc", "folder": str(folder), "name": "model", "ext": "ifc", "dry_run": True}
    env, made, exported, records = export_env(tmp_path, args)
    env["main"]()
    assert made == [] and exported == [] and not folder.exists()
    rows = [r[1] for r in records if r[0] == "item"]
    assert rows == [{"kind": "would_write", "path": str(folder / "model.ifc"), "would_write": str(folder / "model.ifc"), "bytes": 0, "exists": 0}]
    m = {r[1]: r[2] for r in records if r[0] == "meta"}
    assert m["dry_run"] == 1 and m["committed"] == 0 and m["outcome"] == "ok"


def test_export_dry_run_still_refuses_an_existing_file(tmp_path):
    (tmp_path / "model.ifc").write_bytes(b"old")
    args = {"format": "ifc", "folder": str(tmp_path), "name": "model", "ext": "ifc", "dry_run": True, "overwrite": False}
    env, made, exported, records = export_env(tmp_path, args)
    env["main"]()
    assert [r[1] for r in records if r[0] == "refuse"] == ["file_exists"] and made == [] and exported == []


def test_export_module_result_of_a_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(docs, "_server_in_mock_mode", lambda: False)
    target = tmp_path / "set.pdf"
    seen: List[str] = []
    out = ("SUMMARY\tpdf export would write %s; nothing was exported\nMETA\tdry_run\t1\nMETA\tcommitted\t0\nMETA\tchanged_ids\t\n"
           "META\twould_change_ids\t\nMETA\toutcome\tok\nROW\trow_type=item\tkind=would_write\tpath=%s\twould_write=%s\tbytes=0\texists=0\n"
           "COUNT\tfail\t0\nCOUNT\trow\t1") % (target, target, target)

    def bridge(name, args):
        seen.append(args["script"])
        return {"success": True, "output": out}

    result = docs.RevitDocsModule().export(format="pdf", path=str(target), all_sheets=True, dry_run=True,
                                           workspace=WorkspaceMonitor([tmp_path]), approved_executor=bridge)
    assert result["ok"] is True and result["dry_run"] is True and result["committed"] is False, result
    assert result["path"] == str(target) and result["files"] == [] and result["exists"] is False
    assert result["would_change"]["files"] == [str(target)] and "'dry_run': True" in seen[0]
    assert not target.exists()


@pytest.mark.parametrize("tool,args", [
    ("revit_make_view", {"kind": "3d", "name": "Review", "tag": "DOC"}),
    ("revit_make_sheet", {"number": "A1", "name": "Plans", "tag": "DOC"}),
    ("revit_make_schedule", {"name": "Doors", "tag": "DOC", "category": "Doors", "fields": ["Mark"]}),
])
def test_docs_write_tools_pass_dry_run_to_the_script(tool, args, monkeypatch):
    monkeypatch.setattr(docs, "_server_in_mock_mode", lambda: False)
    seen: List[str] = []

    def bridge(name, a):
        seen.append(a["script"])
        return {"success": True, "output": "SUMMARY\tx\nMETA\toutcome\tok\nMETA\tdry_run\t1\nMETA\tcommitted\t0\nMETA\tchanged_ids\t\nMETA\twould_change_ids\t9\nCOUNT\tfail\t0"}

    method = getattr(docs.RevitDocsModule(), tool.replace("revit_", ""))
    result = method(dry_run=True, approved_executor=bridge, workspace=None, **args)
    assert result["ok"] is True and result["dry_run"] is True and result["would_change"]["element_ids_in_trial"] == [9]
    assert "'dry_run': True" in seen[0]
    plain = method(approved_executor=bridge, workspace=None, **args)
    assert "'dry_run': False" in seen[1] and plain["dry_run"] is False


# --------------------------------------------------------------------------- #
# Gating: a dry run is approval-gated like any write
# --------------------------------------------------------------------------- #
def wire(tmp_path, monkeypatch, module_dir, output):
    inst = ModuleInstance(ModuleManifest(**json.loads((module_dir / "module.json").read_text(encoding="utf-8"))), module_dir)
    monkeypatch.setattr(inst.code_module, "_server_in_mock_mode", lambda: False)
    gate = ApprovalGate(tmp_path, "ask_first")

    class FakeRevit:
        def __init__(self):
            self.calls = []

        async def execute_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return {"success": True, "output": output}

        def call_is_read_only(self, name, arguments):
            return arguments.get("mode") == "read"

    revit = FakeRevit()
    provider = ModuleProvider(SimpleNamespace(get_all_modules=lambda: [inst], config=SimpleNamespace(allow_python_host=False)),
                              WorkspaceMonitor([tmp_path]))
    capabilities = {tool.name: tool for tool in provider.get_capabilities()}
    capabilities["revit_execute_python"] = SimpleNamespace(is_mutating=True)
    registry = SimpleNamespace(
        lookup_tool=lambda name: capabilities.get(name),
        lookup_tool_provider=lambda name: provider if name in capabilities and name != "revit_execute_python" else revit,
        get_provider=lambda name: SimpleNamespace(gate=gate) if name == "approval" else None,
    )
    provider.tool_registry = registry
    return gate, registry, revit


DRY_OUT = "SUMMARY\tx\nMETA\toutcome\tok\nMETA\tdry_run\t1\nMETA\tcommitted\t0\nMETA\tchanged_ids\t\nMETA\twould_change_ids\t3\nCOUNT\tfail\t0"


def test_a_dry_run_without_a_plan_is_refused_and_with_an_approved_plan_it_runs(tmp_path, monkeypatch):
    gate, registry, revit = wire(tmp_path, monkeypatch, docs.MODULE_DIR, DRY_OUT)
    args = {"kind": "3d", "name": "Review", "tag": "DOC", "dry_run": True}
    with pytest.raises(BridgeError, match="plan_id"):
        asyncio.run(run_gated_tool(registry, gate, "revit_make_view", dict(args)))
    assert revit.calls == []
    plan = gate.create_plan([{"tool": "revit_make_view", "arguments": args}], [{}])
    human_approve(gate, plan["plan_id"])
    result = asyncio.run(run_gated_tool(registry, gate, "revit_make_view", {**args, "plan_id": plan["plan_id"]}))
    assert result["ok"] is True and result["dry_run"] is True and result["changed_ids"] == []
    assert [c[1]["mode"] for c in revit.calls] == ["write"]
    assert gate.load_plan(plan["plan_id"])["actions"][0]["state"] == "executed"
