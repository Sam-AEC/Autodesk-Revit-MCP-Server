"""Run the real embedded make_family script against the write-side stub of the Revit API (not against Revit)."""
from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import revit_api_stub as stub
from revit_mcp_server.check_contract import parse_script_output
from revit_mcp_server.modules.revit_family import module as fam

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = fam.SCRIPT_DIR / "make_family.ipy"

PANEL = {"name": "AMB2_Panel", "category": "elec_eq", "w": 0.5, "d": 0.15, "h": 0.7,
         "ports": [{"pos": [0, 0.08, 0.3], "dir": "+y", "kind": "elec", "system": "power", "label": "feed"}]}
HEAT = {"name": "AMB2_Heat", "category": "mech", "w": 0.6, "d": 0.6, "h": 1.8,
        "ports": [{"pos": [0.32, -0.2, 1.6], "dir": "+x", "kind": "pipe", "system": "hsup", "dia_mm": 40, "flow": "out", "label": "supply"},
                  {"pos": [0.32, 0.2, 1.6], "dir": "+x", "kind": "pipe", "system": "hret", "dia_mm": 40, "flow": "in", "label": "return"},
                  {"pos": [0.0, 0.0, 1.85], "dir": "+z", "kind": "duct", "system": "supply", "dia_mm": 100, "label": "air"}]}


def load_functions(names, env):
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SCRIPT), "exec"), env)
    return env


class Setup:
    def __init__(self, tmp_path: Path, monkeypatch: Any, templates: Optional[List[str]] = None) -> None:
        self.monkeypatch = monkeypatch
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.templates = tmp_path / "Family Templates"
        self.templates.mkdir()
        for name in templates if templates is not None else ["Metric Electrical Equipment.rft", "Metric Mechanical Equipment.rft", "Metric Generic Model.rft"]:
            (self.templates / name).write_bytes(b"RFT")
        self.out = tmp_path / "families"
        self.app = stub.FakeApp(str(self.templates))
        self.doc = stub.ProjectDoc(self.app)

    def run(self, specs: List[Dict[str, Any]], **extra: Any) -> Any:
        args = {"specs": [fam.validate_spec(s, i) for i, s in enumerate(specs)], "output_dir": str(self.out),
                "template_path": "", "replace": False, "on_error": "abort"}
        args.update(extra)
        script = fam.build_script("make_family.ipy", args, write=True)
        with stub.install_family_write_api(self.monkeypatch):
            text = stub.run_script(script, self.doc, self.app)
        return parse_script_output(text)

    def project_names(self) -> List[str]:
        return [e.Name for e in self.doc.elements if isinstance(e, stub.Family)]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    return Setup(tmp_path, monkeypatch)


def test_script_and_preludes_compile_and_inputs_stay_literals():
    for script in fam.SCRIPT_DIR.glob("*.ipy"):
        compile(script.read_text(encoding="utf-8"), str(script), "exec")
    nasty = dict(PANEL, name="x'\nraise Exception('oops')")
    built = fam.build_script("make_family.ipy", {"specs": [nasty], "output_dir": "C:\\a'b", "on_error": "abort"}, write=True)
    compile(built, "built", "exec")
    assert "raise Exception('oops')" not in built.replace("\\n", "")


def test_script_has_no_python3_only_syntax():
    source = SCRIPT.read_text(encoding="utf-8") + (fam.SCRIPT_DIR / "_write_prelude.ipy").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.JoinedStr, ast.AnnAssign, ast.Nonlocal, ast.AsyncFunctionDef))]
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and (n.returns or any(a.annotation for a in n.args.args))]


# ----- the happy path --------------------------------------------------------- #
def test_one_family_is_built_saved_loaded_and_the_family_document_is_closed(setup):
    parsed = setup.run([PANEL])
    assert parsed.meta["outcome"] == "ok" and parsed.fails == []
    assert (setup.out / "AMB2_Panel.rfa").is_file()
    assert setup.project_names() == ["AMB2_Panel"]
    assert [fd.closed for fd in setup.app.family_docs] == [True]
    assert setup.doc.group_log == ["Assimilated"]
    row = next(r for r in parsed.rows if r.get("kind") == "family")
    assert row["name"] == "AMB2_Panel" and row["template_kind"] == "category" and row["ports"] == "1" and row["status"] == "created"
    assert row["template"].endswith("Metric Electrical Equipment.rft")
    assert parsed.meta["changed_ids"].split(",")[0] == row["id"]
    assert all(r["ok"] == "1" for r in parsed.rows if r.get("row_type") == "post")


def test_the_family_gets_the_category_a_body_a_port_cube_connector_and_a_type(setup):
    setup.run([HEAT])
    fd = setup.app.family_docs[0]
    assert fd.OwnerFamily.FamilyCategory.Id.Value == int(stub.BuiltInCategory.OST_MechanicalEquipment)
    boxes = [e for e in fd.elements if isinstance(e, stub.FExtrusion)]
    assert len(boxes) == 1 + 3                       # body + one cube per port
    body = boxes[0]
    assert round(body.bbox.Max.Z * 304.8) == 1800 and round(body.bbox.Min.Z) == 0
    assert round((body.bbox.Max.X - body.bbox.Min.X) * 304.8) == 600
    conns = [e for e in fd.elements if isinstance(e, stub.FConnector)]
    assert [c.Domain for c in conns] == ["DomainPiping", "DomainPiping", "DomainHvac"]
    assert [c.ref.key for c in conns] == ["+x", "+x", "+z"]
    assert conns[0].SystemClassification == "SupplyHydronic" and conns[1].SystemClassification == "ReturnHydronic"
    assert conns[0].values["connector_diameter"] == pytest.approx(40 / 1000.0 / 0.3048)
    assert conns[0].values["pipe_flow"] == 1 and conns[1].values["pipe_flow"] == 0 and "duct_flow" not in conns[2].values
    assert fd.FamilyManager.Types.names == ["AMB2_Heat"]
    assert fd.open_txns == 0 and fd.rolled_back_txns == [] and fd.saved_to.endswith("AMB2_Heat.rfa")


def test_the_cube_is_centred_on_the_port_position(setup):
    setup.run([HEAT])
    cube = [e for e in setup.app.family_docs[0].elements if isinstance(e, stub.FExtrusion)][1]
    centre = [(cube.bbox.Min.X + cube.bbox.Max.X) / 2 * 0.3048, (cube.bbox.Min.Y + cube.bbox.Max.Y) / 2 * 0.3048, (cube.bbox.Min.Z + cube.bbox.Max.Z) / 2 * 0.3048]
    assert centre == pytest.approx([0.32, -0.2, 1.6], abs=1e-6)


def test_every_family_of_the_villa2_recipe_builds(tmp_path, monkeypatch):
    specs = json.loads((ROOT / "docs" / "recipes" / "villa2" / "m1_specs.json").read_text(encoding="utf-8"))
    for start in range(0, len(specs), fam.MAX_SPECS):
        s = Setup(tmp_path / str(start), monkeypatch)
        parsed = s.run(specs[start:start + fam.MAX_SPECS])
        assert parsed.meta["outcome"] == "ok", parsed.fails
        assert len(s.project_names()) == len(specs[start:start + fam.MAX_SPECS])


# ----- template search -------------------------------------------------------- #
def test_template_is_searched_by_category_and_excludes_hosted_ones(tmp_path, monkeypatch):
    s = Setup(tmp_path, monkeypatch, ["Metric Electrical Equipment wall based.rft", "Metric Electrical Equipment.rft", "Electrical Equipment.rft", "Metric Generic Model.rft"])
    parsed = s.run([PANEL])
    row = next(r for r in parsed.rows if r.get("kind") == "family")
    assert row["template"].endswith("Metric Electrical Equipment.rft") and row["template_kind"] == "category"


def test_generic_model_template_is_an_explicit_reported_fallback(tmp_path, monkeypatch):
    s = Setup(tmp_path, monkeypatch, ["Metric Generic Model.rft"])
    parsed = s.run([PANEL])
    row = next(r for r in parsed.rows if r.get("kind") == "family")
    assert parsed.meta["outcome"] == "ok" and row["template_kind"] == "generic"
    assert any("TEMPLATE_GENERIC" in i for i in parsed.infos)


def test_no_template_found_fails_loudly_and_changes_nothing(tmp_path, monkeypatch):
    s = Setup(tmp_path, monkeypatch, ["Metric Window.rft", "Metric Door.rft"])
    parsed = s.run([PANEL])
    assert parsed.meta["outcome"] == "template_not_found" and parsed.meta["changed_ids"] == ""
    message = parsed.fails[0]
    assert "no family template found for category 'elec_eq'" in message and "Family Templates" in message and "2 .rft files" in message
    assert "template_path" in message
    assert s.app.family_docs == [] and s.project_names() == [] and not s.out.exists()
    assert s.doc.group_log == []


def test_no_template_folder_at_all_is_said_plainly(tmp_path, monkeypatch):
    s = Setup(tmp_path, monkeypatch, [])
    s.app.FamilyTemplatePath = ""
    parsed = s.run([PANEL])
    assert parsed.meta["outcome"] == "template_not_found" and "Revit reports no family template folder" in parsed.fails[0]


def test_explicit_template_is_used_as_given_and_a_missing_one_is_refused(tmp_path, monkeypatch):
    s = Setup(tmp_path, monkeypatch, [])
    mine = tmp_path / "mine.rft"
    mine.write_bytes(b"RFT")
    parsed = s.run([PANEL], template_path=str(mine))
    row = next(r for r in parsed.rows if r.get("kind") == "family")
    assert row["template"] == str(mine) and row["template_kind"] == "explicit"
    s2 = Setup(tmp_path / "second", monkeypatch, [])
    parsed = s2.run([PANEL], template_path=str(tmp_path / "gone.rft"))
    assert parsed.meta["outcome"] == "template_not_found" and "gone.rft" in parsed.fails[0] and "does not exist" in parsed.fails[0]
    assert s2.app.family_docs == []


def test_pick_templates_prefers_metric_then_the_shortest_name():
    env = load_functions({"pick_templates"}, {"IoPath": SimpleNamespace(GetFileNameWithoutExtension=lambda p: Path(p).stem),
                                                  "TEMPLATE_SKIP": ["based", "wall"]})
    files = ["a/Plumbing Fixture.rft", "a/Metric Plumbing Fixture wall based.rft", "a/Metric Plumbing Fixture Special.rft", "a/Metric Plumbing Fixture.rft"]
    assert [Path(p).name for p in env["pick_templates"](files, ["plumbing fixture"])] == ["Metric Plumbing Fixture.rft", "Metric Plumbing Fixture Special.rft", "Plumbing Fixture.rft"]


# ----- refusals before anything changes --------------------------------------- #
def test_an_existing_family_or_file_is_refused_without_replace(setup):
    setup.run([PANEL])
    before = list(setup.doc.elements)
    again = setup.run([PANEL])
    assert again.meta["outcome"] == "file_exists" and "replace=true" in again.fails[0]
    assert setup.doc.elements == before
    (setup.out / "AMB2_Panel.rfa").unlink()
    again = setup.run([PANEL])
    assert again.meta["outcome"] == "family_exists" and "AMB2_Panel" in again.fails[0] and "replace=true" in again.fails[0]
    assert setup.doc.elements == before and not (setup.out / "AMB2_Panel.rfa").exists()


def test_replace_overwrites_the_file_and_loads_over_the_family(setup):
    setup.run([PANEL])
    parsed = setup.run([PANEL], replace=True)
    assert parsed.meta["outcome"] == "ok"
    assert next(r for r in parsed.rows if r.get("kind") == "family")["status"] == "replaced"
    assert setup.project_names() == ["AMB2_Panel"]


def test_a_family_document_as_active_document_is_refused(setup):
    setup.doc.IsFamilyDocument = True
    parsed = setup.run([PANEL])
    assert parsed.meta["outcome"] == "wrong_document" and setup.app.family_docs == []


# ----- failure handling: rollback, skip, closing family documents ------------- #
def test_abort_rolls_back_the_project_and_removes_files_written_by_the_call(setup):
    setup.app.refuse_flow = True            # PANEL (no flow) works, HEAT then fails on its flow direction
    before = list(setup.doc.elements)
    parsed = setup.run([PANEL, HEAT])
    assert parsed.meta["outcome"] == "rolled_back" and parsed.meta["changed_ids"] == ""
    assert any("STEP_FAILED" in f and "flow direction" in f and "AMB2_Heat" in f for f in parsed.fails)
    assert setup.doc.elements == before and setup.doc.group_log == ["RolledBack"]
    assert list(setup.out.glob("*.rfa")) == []
    assert all(fd.closed for fd in setup.app.family_docs) and len(setup.app.family_docs) == 2
    assert all(fd.open_txns == 0 for fd in setup.app.family_docs) and setup.doc.open_txns == 0


def test_skip_keeps_what_worked_and_lists_the_failure(setup):
    setup.app.refuse_flow = True
    parsed = setup.run([PANEL, HEAT], on_error="skip")
    assert parsed.meta["outcome"] == "partial_failure"
    assert setup.project_names() == ["AMB2_Panel"]
    assert [p.name for p in setup.out.glob("*.rfa")] == ["AMB2_Panel.rfa"]
    assert any("AMB2_Heat" in f for f in parsed.fails)
    assert all(fd.closed for fd in setup.app.family_docs)
    assert setup.doc.group_log == ["Assimilated"]
    assert len(parsed.meta["changed_ids"].split(",")) == 2        # the family and its type


def test_skip_with_nothing_that_worked_is_rolled_back_not_assimilated(setup):
    setup.app.refuse_size = True
    parsed = setup.run([HEAT], on_error="skip")
    assert parsed.meta["outcome"] == "rolled_back" and setup.doc.group_log == ["RolledBack"]
    assert "connector size" in parsed.fails[0]


def test_a_save_that_throws_still_closes_the_family_document(setup):
    setup.app.fail_save = True
    parsed = setup.run([PANEL])
    assert parsed.meta["outcome"] == "rolled_back" and "disk is full" in parsed.fails[0]
    assert [fd.closed for fd in setup.app.family_docs] == [True]
    assert list(setup.out.glob("*.rfa")) == []


def test_a_refused_load_is_a_failure_and_the_orphan_file_is_removed(setup):
    setup.app.refuse_load = True
    parsed = setup.run([PANEL])
    assert parsed.meta["outcome"] == "rolled_back" and "did not load" in parsed.fails[0]
    assert list(setup.out.glob("*.rfa")) == [] and setup.project_names() == []


def test_a_template_with_nested_instances_is_refused(setup):
    setup.app.template_nested = [stub.FamilyInstance(9, stub.Category(stub.BuiltInCategory.OST_GenericModel, "Generic Models"))]
    parsed = setup.run([PANEL])
    assert parsed.meta["outcome"] == "rolled_back" and "nested family instances" in parsed.fails[0]
    assert all(fd.closed for fd in setup.app.family_docs) and setup.project_names() == []


def test_the_project_is_not_left_in_a_changed_state_when_the_script_itself_crashes(setup, monkeypatch):
    original = stub.ProjectDoc.LoadFamily

    def boom(self, path, options):
        raise RuntimeError("Revit exploded")

    monkeypatch.setattr(stub.ProjectDoc, "LoadFamily", boom)
    before = list(setup.doc.elements)
    parsed = setup.run([PANEL])
    monkeypatch.setattr(stub.ProjectDoc, "LoadFamily", original)
    assert parsed.meta["outcome"] == "rolled_back" and setup.doc.elements == before
    assert all(fd.closed for fd in setup.app.family_docs) and list(setup.out.glob("*.rfa")) == []


def test_an_uncommitted_family_transaction_rolls_back_and_closes(setup, monkeypatch):
    real = stub.FamilyDoc.__init__

    def init(self, app, template):
        real(self, app, template)
        self.refuse_commit = True

    monkeypatch.setattr(stub.FamilyDoc, "__init__", init)
    parsed = setup.run([PANEL])
    assert parsed.meta["outcome"] == "rolled_back" and "did not commit the family" in parsed.fails[0]
    assert [fd.closed for fd in setup.app.family_docs] == [True]


def test_the_connector_count_in_the_family_document_must_match_the_ports(setup, monkeypatch):
    monkeypatch.setattr(stub.FConnector, "CreateElectricalConnector", staticmethod(lambda fd, system, ref: stub.FExtrusion(1, (0, 0, 0), (1, 1, 1))))
    parsed = setup.run([PANEL])
    assert parsed.meta["outcome"] == "rolled_back" and "0 connectors, the spec has 1 ports" in parsed.fails[0]


def test_the_runner_never_assimilates_a_group_that_committed_nothing():
    records = []
    group = SimpleNamespace(HasStarted=lambda: True, RollBack=lambda: "rolled_back", Assimilate=lambda: records.append("assimilated") or "committed")
    env = {"TransactionStatus": SimpleNamespace(Committed="committed", RolledBack="rolled_back"),
           "meta": lambda *a: None, "fail": lambda *a: None, "info": lambda *a: None}
    prelude = ast.parse((fam.SCRIPT_DIR / "_write_prelude.ipy").read_text(encoding="utf-8"))
    nodes = [n for n in prelude.body if isinstance(n, ast.ClassDef) and n.name in ("Runner", "StepError", "Abort")]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "prelude", "exec"), env)
    runner = object.__new__(env["Runner"])
    runner.closed = runner.crashed = False
    runner.failed_steps, runner.failed_ids, runner.warnings, runner.changed = ["Build family 'x'"], [], [], []
    runner.post_failed, runner.committed, runner.on_error, runner.group, runner.outcome = 0, 0, "skip", group, "ok"
    runner.close()
    assert runner.outcome == "rolled_back" and records == []


# ----- module and script together ---------------------------------------------- #
def test_module_runs_the_real_script_end_to_end_and_probes_the_result(tmp_path, monkeypatch):
    from revit_mcp_server.security.workspace import WorkspaceMonitor

    s = Setup(tmp_path / "revit", monkeypatch)
    monkeypatch.setattr(fam, "_server_in_mock_mode", lambda: False)
    monkeypatch.setattr(fam.revit_module(), "_server_in_mock_mode", lambda: False)
    probed: List[str] = []

    def executor(tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if arguments["mode"] == "write":
            with stub.install_family_write_api(monkeypatch):
                return {"success": True, "output": stub.run_script(arguments["script"], s.doc, s.app)}
        probed.append(arguments["script"])
        family = next(e for e in s.doc.elements if isinstance(e, stub.Family))
        text = "\n".join([
            "SUMMARY\tprobed",
            "ROW\tkind=family\tfamily=F\tname=%s\tcategory=Electrical Equipment\tid=%d\ttypes=1\tinstances=0" % (family.Name, family.Id.Value),
            "ROW\tkind=connector\tfamily=F\tscope=family\tdomain=DomainElectrical\tsystem=PowerCircuit\tsize=\tflow=Bidirectional\tdir=0,1,0\torigin=0,0,0",
            "COUNT\tfail\t0"])
        return {"success": True, "output": text}

    ws = WorkspaceMonitor([tmp_path])
    result = fam.RevitFamilyModule().make_family(specs=[PANEL], output_dir=str(tmp_path / "ws" / "out"), workspace=ws, approved_executor=executor)
    assert result["ok"] is True and result["verified"] is True, result
    assert (tmp_path / "ws" / "out" / "AMB2_Panel.rfa").is_file()
    assert result["rows"][0]["name"] == "AMB2_Panel" and result["template"].endswith("Metric Electrical Equipment.rft")
    assert result["changed_ids"][0] == result["rows"][0]["id"] and "'ids': [%d]" % result["rows"][0]["id"] in probed[0]
    assert result["probe"][0]["verdict"] == "PASS"
