"""The revit_params scripts executed under CPython against a stub of the Revit API with an undo journal.

This proves the scripts' control flow (selection, unit conversion, refusals, one transaction per element, read-back,
rollback, dry run) and the line protocol. It does NOT prove that Revit accepts the same calls: that is UNVERIFIED.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import revit_api_stub as base  # noqa: E402
import revit_mep_stub as rs  # noqa: E402
from revit_mcp_server.modules.revit_params import module as params  # noqa: E402
from revit_mcp_server.security.read_mode import validate_read_script  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402

BIC = base.BuiltInCategory
BIP = rs.BuiltInParameter
LEN, ANG, YES, TXT = "spec:length", "spec:angle", "spec:yesno", "spec:text"


class Bridge:
    """The add-in: runs the script it is handed against the stub world and records the mode."""

    def __init__(self, world: rs.World) -> None:
        self.world, self.modes = world, []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        assert name == "revit_execute_python"
        self.modes.append(args["mode"])
        if args["mode"] == "read":
            validate_read_script(args["script"])
        return {"success": True, "output": self.world.run(args["script"]), "error": ""}


def build_scene(w: rs.World) -> Dict[str, Any]:
    s: Dict[str, Any] = {"L0": w.level("L0", 0.0), "L1": w.level("L1", 10.0)}
    concrete = rs.ParamElement(w.next_id(), base.Category(-2000700, "Materials"), "Concrete")
    brick = rs.ParamElement(w.next_id(), base.Category(-2000700, "Materials"), "Brick")
    s["concrete"], s["brick"] = concrete, brick
    wall_type = rs.ParamElement(w.next_id(), base.Category(BIC.OST_Walls, "Walls"), "Basic 200", is_type=True)
    wall_type.add("Type Mark", "W1")
    wall_type.add("Width", 200 / 304.8, "Double", LEN, read_only=True)
    wall_type.add("Fire Rating", "", "String", TXT)
    s["wall_type"] = wall_type
    w.elements.extend([concrete, brick, wall_type])
    for i, (lvl, comment) in enumerate([("L0", "PH1 a"), ("L0", "PH1 b"), ("L1", "PH2 c")]):
        wall = rs.ParamElement(w.next_id(), base.Category(BIC.OST_Walls, "Walls"), "Basic 200", comments=comment,
                               level_id=s[lvl].Id.Value)
        wall.type_el = wall_type
        wall.add("Mark", "")
        wall.add("Comments", comment, bip=BIP.ALL_MODEL_INSTANCE_COMMENTS)
        wall.add("Unconnected Height", 3000 / 304.8, "Double", LEN)
        wall.add("Angle", 0.0, "Double", ANG)
        wall.add("Load Factor", 1.0, "Double", "spec:number")
        wall.add("Room Bounding", 1, "Integer", YES)
        wall.add("Count", 2, "Integer", "spec:int")
        wall.add("Structural Material", concrete.Id.Value, "ElementId", "spec:ref")
        wall.add("Area", 12.0, "Double", "spec:area", read_only=True)
        wall.add("Workset", 0, "Integer", "spec:int", bip=BIP.ELEM_PARTITION_PARAM)
        wall.add("Base Constraint", s[lvl].Id.Value, "ElementId", "spec:ref", bip=BIP.WALL_BASE_CONSTRAINT)
        w.elements.append(wall)
        s["w%d" % i] = wall
    door = rs.ParamElement(w.next_id(), base.Category(BIC.OST_Doors, "Doors"), "Door 900", level_id=s["L0"].Id.Value)
    door.add("Mark", "D1")
    door.add("Mark", "D1-shared")  # two parameters with one name
    w.elements.append(door)
    s["door"] = door
    return s


class Env:
    def __init__(self, world, scene, tmp_path):
        self.w, self.s, self.bridge = world, scene, Bridge(world)
        self.module, self.ws = params.RevitParamsModule(), WorkspaceMonitor([tmp_path])

    def set(self, **args):
        return self.module.set_parameters(approved_executor=self.bridge, workspace=self.ws, **args)

    def get(self, **args):
        return self.module.get_parameters(tool_executor=self.bridge, workspace=self.ws, **args)

    def value(self, el, name):
        return el.GetParameters(name)[0].value


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(params, "_server_in_mock_mode", lambda: False)
    with rs.installed_mep(monkeypatch) as world:
        yield Env(world, build_scene(world), tmp_path)


def rows_of(result, status=None):
    return [r for r in result["rows"] if status is None or r.get("status") == status]


# --------------------------------------------------------------------------- #
# revit_set_parameters
# --------------------------------------------------------------------------- #
def test_set_values_in_explicit_units_with_old_new_and_read_back(env):
    w0 = env.s["w0"]
    result = env.set(items=[{"id": w0.Id.Value, "params": {
        "Mark": "A-01",
        "Unconnected Height": {"value": 2.75, "unit": "m"},
        "Angle": {"value": 90, "unit": "deg"},
        "Load Factor": {"value": 1.5, "unit": "number"},
        "Room Bounding": False,
        "Count": 7,
        "Structural Material": {"value": "Brick", "unit": "elementid"},
    }}])
    assert result["ok"] is True and result["verified"] is True, result
    assert env.value(w0, "Mark") == "A-01"
    assert env.value(w0, "Unconnected Height") == pytest.approx(2.75 / 0.3048)
    assert env.value(w0, "Angle") == pytest.approx(math.pi / 2)
    assert env.value(w0, "Load Factor") == 1.5 and env.value(w0, "Room Bounding") == 0 and env.value(w0, "Count") == 7
    assert env.value(w0, "Structural Material") == env.s["brick"].Id.Value
    assert result["changed_ids"] == [w0.Id.Value] and result["committed"] is True and result["dry_run"] is False
    by = {r["param"]: r for r in rows_of(result, "set")}
    assert len(by) == 7
    assert float(by["Unconnected Height"]["old"]) == pytest.approx(3.0) and float(by["Unconnected Height"]["new"]) == pytest.approx(2.75)
    assert float(by["Unconnected Height"]["read_back"]) == pytest.approx(2.75)
    assert by["Structural Material"]["old"] == "Concrete" and by["Structural Material"]["new"] == "Brick"
    assert result["post_check"]["ok"] is True and result["post_check"]["checked"] == 1
    # one group, one transaction for the element
    log = env.w.txn_log
    assert log[0][0] == "group_start" and log[-1][0] == "group_assimilate"
    assert [n for k, n in log if k == "start"] == ["Set parameters of element %d" % w0.Id.Value]


def test_the_revert_list_puts_the_old_values_back(env):
    w0 = env.s["w0"]
    before = {n: env.value(w0, n) for n in ("Mark", "Unconnected Height", "Room Bounding", "Structural Material")}
    first = env.set(items=[{"id": w0.Id.Value, "params": {
        "Mark": "X", "Unconnected Height": {"value": 2500, "unit": "mm"}, "Room Bounding": False,
        "Structural Material": {"value": "Brick", "unit": "elementid"}}}])
    revert = first["revert"]["items"]
    assert revert and revert[0]["id"] == w0.Id.Value
    back = env.set(items=revert)
    assert back["ok"] is True, back
    after = {n: env.value(w0, n) for n in before}
    assert after["Mark"] == before["Mark"] and after["Room Bounding"] == before["Room Bounding"]
    assert after["Structural Material"] == before["Structural Material"]
    assert after["Unconnected Height"] == pytest.approx(before["Unconnected Height"])


def test_a_selector_with_category_level_and_tag(env):
    result = env.set(items=[{"selector": {"category": "Walls", "level": "L0", "tag": "PH1"}, "params": {"Mark": "P1"}}])
    assert result["ok"] is True, result
    assert sorted(result["changed_ids"]) == sorted([env.s["w0"].Id.Value, env.s["w1"].Id.Value])
    assert env.value(env.s["w2"], "Mark") == ""
    names = [n for k, n in env.w.txn_log if k == "start"]
    assert len(names) == 2  # one transaction per element


def test_type_scope_writes_each_type_once(env):
    result = env.set(items=[{"selector": {"category": "Walls"}, "scope": "type", "params": {"Type Mark": "W9"}}])
    assert result["ok"] is True, result
    assert result["changed_ids"] == [env.s["wall_type"].Id.Value]
    assert env.value(env.s["wall_type"], "Type Mark") == "W9"


def test_unchanged_values_are_not_written(env):
    result = env.set(items=[{"id": env.s["w0"].Id.Value, "params": {"Count": 2}}])
    assert result["ok"] is True and result["changed_ids"] == [] and rows_of(result, "unchanged")
    assert not [k for k, _ in env.w.txn_log if k == "start"]


@pytest.mark.parametrize("name,value,needle", [
    ("Area", {"value": 5, "unit": "number"}, "read-only"),
    ("Workset", 1, "built-in organisation parameter ELEM_PARTITION_PARAM"),
    ("Base Constraint", {"value": "L1", "unit": "elementid"}, "built-in placement parameter"),
    ("Does Not Exist", "x", "never creates parameters"),
    ("Type Mark", "W2", "use scope 'type'"),
    ("Unconnected Height", 3, "give a unit: mm"),
    ("Unconnected Height", {"value": 2.5, "unit": "deg"}, "needs an angle parameter"),
    ("Angle", {"value": 2.5, "unit": "number"}, "give deg"),
    ("Room Bounding", 3, "Yes/No parameter"),
    ("Count", {"value": True, "unit": "bool"}, "integer parameter"),
    ("Mark", {"value": "Brick", "unit": "elementid"}, "text parameter"),
    ("Structural Material", {"value": "Steel", "unit": "elementid"}, "no element named 'Steel'"),
    ("Structural Material", "Brick", "give the element's name"),
])
def test_refusals_change_nothing_and_say_why_per_element(env, name, value, needle):
    before = env.w.snapshot(), [p.value for p in env.s["w0"].Parameters]
    result = env.set(items=[{"id": env.s["w0"].Id.Value, "params": {"Mark": "OK", name: value}}])
    assert result["ok"] is False and result["kind"] == "parameter_refused", result
    refused = rows_of(result, "refused")
    assert len(refused) == 1 and refused[0]["id"] == env.s["w0"].Id.Value and needle in refused[0]["reason"], refused
    assert (env.w.snapshot(), [p.value for p in env.s["w0"].Parameters]) == before
    assert env.w.txn_log == [] and result["changed_ids"] == []


def test_two_parameters_with_one_name_are_refused(env):
    result = env.set(items=[{"id": env.s["door"].Id.Value, "params": {"Mark": "D2"}}])
    assert result["kind"] == "parameter_refused" and "will not guess" in rows_of(result, "refused")[0]["reason"]


def test_skip_mode_writes_the_others_and_lists_the_refused(env):
    w0, w1 = env.s["w0"], env.s["w1"]
    result = env.set(on_error="skip", items=[
        {"id": w0.Id.Value, "params": {"Mark": "A"}},
        {"id": w1.Id.Value, "params": {"Mark": "B", "Area": {"value": 1, "unit": "number"}}},
    ])
    assert result["ok"] is False and result["kind"] == "partial_failure", result
    assert result["changed_ids"] == [w0.Id.Value] and env.value(w0, "Mark") == "A" and env.value(w1, "Mark") == ""
    assert any("PARAM_REFUSED" in f for f in result["fails"]) and result["element_ids"] == [w1.Id.Value]
    assert env.w.txn_log[-1][0] == "group_assimilate"


def test_a_failed_write_in_abort_mode_rolls_everything_back(env):
    w0, w1 = env.s["w0"], env.s["w1"]
    w1.GetParameters("Mark")[0].refuse = True
    result = env.set(items=[{"ids": [w0.Id.Value, w1.Id.Value], "params": {"Mark": "Z"}}])
    assert result["ok"] is False and result["kind"] == "rolled_back", result
    assert env.value(w0, "Mark") == "" and env.w.journal == []
    assert env.w.txn_log[-1][0] == "group_rollback"
    assert {r["status"] for r in result["rows"]} == {"rolled_back", "failed"}
    assert "Revit refused to set 'Mark'" in result["message"]


def test_a_value_that_does_not_read_back_fails_the_post_check(env, monkeypatch):
    original = rs.NamedParam.Set

    def lossy(self, value):
        return original(self, value + "?" if isinstance(value, str) else value)

    monkeypatch.setattr(rs.NamedParam, "Set", lossy)
    result = env.set(items=[{"id": env.s["w0"].Id.Value, "params": {"Mark": "Q"}}])
    assert result["ok"] is False and result["kind"] == "rolled_back"
    failed = [c for c in result["post_check"]["checks"] if not c["ok"]]
    assert failed and "wanted Q, read back Q?" in failed[0]["detail"]
    assert env.value(env.s["w0"], "Mark") == ""


def test_conflicting_values_for_one_type_are_refused(env):
    result = env.set(items=[
        {"id": env.s["w0"].Id.Value, "scope": "type", "params": {"Type Mark": "A"}},
        {"id": env.s["w1"].Id.Value, "scope": "type", "params": {"Type Mark": "B"}},
    ])
    assert result["kind"] == "conflicting_values" and env.w.txn_log == []


def test_missing_ids_and_empty_selectors_are_refused(env):
    result = env.set(items=[{"ids": [999999], "params": {"Mark": "A"}}])
    assert result["kind"] == "element_not_found" and result["element_ids"] == [999999]
    result = env.set(items=[{"selector": {"category": "Walls", "level": "L9"}, "params": {"Mark": "A"}}])
    assert result["kind"] == "empty_selection"


def test_dry_run_reads_back_inside_the_group_then_leaves_the_model_unchanged(env):
    w0 = env.s["w0"]
    before = [p.value for p in w0.Parameters]
    result = env.set(dry_run=True, items=[{"id": w0.Id.Value, "params": {"Mark": "DRY", "Count": 9}}])
    assert result["ok"] is True and result["dry_run"] is True and result["committed"] is False, result
    assert result["changed_ids"] == [] and result["would_change"]["element_count"] == 1
    assert result["post_check"]["ok"] is True and result["post_check"]["checked"] == 1
    assert {r["status"] for r in result["rows"]} == {"would_set"} and result["revert"]["items"] == []
    assert [p.value for p in w0.Parameters] == before and env.w.journal == []
    assert env.w.txn_log[-1][0] == "group_rollback"


# --------------------------------------------------------------------------- #
# revit_get_parameters
# --------------------------------------------------------------------------- #
def test_get_named_parameters_in_the_units_the_write_tool_expects(env):
    result = env.get(items=[{"selector": {"category": "Walls", "tag": "PH1"},
                             "params": ["Unconnected Height", "Room Bounding", "Structural Material", "Workset", "Nope"]}])
    assert result["ok"] is True and result["truncated"] is False, result
    assert env.bridge.modes == ["read"]
    rows = [r for r in result["rows"] if r["kind"] == "param"]
    by = {(r["element_id"], r["param"]): r for r in rows}
    h = by[(env.s["w0"].Id.Value, "Unconnected Height")]
    assert h["unit"] == "mm" and float(h["value"]) == pytest.approx(3000.0) and h["writable"] is True
    assert by[(env.s["w0"].Id.Value, "Room Bounding")]["unit"] == "bool"
    mat = by[(env.s["w0"].Id.Value, "Structural Material")]
    assert mat["unit"] == "elementid" and mat["value"] == "Concrete" and mat["value_id"] == env.s["concrete"].Id.Value
    ws = by[(env.s["w0"].Id.Value, "Workset")]
    assert ws["writable"] is False and "ELEM_PARTITION_PARAM" in ws["reason"]
    assert len([r for r in result["rows"] if r["kind"] == "missing"]) == 2


def test_get_all_parameters_of_a_type(env):
    result = env.get(items=[{"id": env.s["w0"].Id.Value, "scope": "type"}])
    names = [r["param"] for r in result["rows"]]
    assert names == ["Fire Rating", "Type Mark", "Width"]
    width = next(r for r in result["rows"] if r["param"] == "Width")
    assert width["read_only"] is True and width["writable"] is False and width["id"] == env.s["wall_type"].Id.Value


def test_get_caps_elements_and_flags_truncated(env):
    result = env.get(max_elements=1, items=[{"selector": {"category": "Walls"}, "params": ["Mark"]}])
    assert result["ok"] is True and result["truncated"] is True and result["limits"]["partial"] is True
    assert len(result["rows"]) == 1 and any("ELEMENT_CAP" in i for i in result["info"])


def test_get_stops_at_the_time_budget(env):
    base.Stopwatch.tick = 600  # every read of the clock moves 0.6 s on
    try:
        result = env.get(time_budget_s=1, items=[{"selector": {"category": "Walls"}, "params": ["Mark"]}])
    finally:
        base.Stopwatch.tick = 0
    assert result["truncated"] is True and any("TIME_BUDGET" in i for i in result["info"])
    assert len(result["rows"]) == 1


def test_get_rows_are_paged(env):
    result = env.get(limit=2, items=[{"selector": {"category": "Walls"}}])
    assert len(result["rows"]) == 2 and result["truncated"] is True and result["limits"]["rows_total"] > 2
