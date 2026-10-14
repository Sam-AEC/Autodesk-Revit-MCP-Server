"""The revit_mep scripts executed under CPython against a stub of the Revit API (tests/revit_mep_stub.py).

This proves the scripts' control flow, the category guard, the ownership/replace rules, rollback (the stub keeps a real
undo journal) and the line protocol. It does NOT prove that Revit accepts the same calls: that is UNVERIFIED.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import revit_api_stub as base  # noqa: E402
import revit_mep_stub as rs  # noqa: E402
from revit_mcp_server.modules.revit_mep import module as mep  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402

M = 0.3048  # one foot in metres
BIC = base.BuiltInCategory
SUP, RET = "SupplyHydronic", "ReturnHydronic"


def port(system, origin, basis=(1.0, 0.0, 0.0), domain="DomainPiping", radius_ft=0.0525, direction="Bidirectional", **shape):
    return {"domain": domain, "system": system, "origin": origin, "basis": basis, "radius_ft": radius_ft, "direction": direction, **shape}


def build_scene(w: rs.World) -> Dict[str, Any]:
    s: Dict[str, Any] = {}
    s["L0"], s["L1"] = w.level("L0", 0.0), w.level("L1", 10.0)
    s["pex"], s["round"] = w.pipe_type("PEX"), w.duct_type("Round Duct")
    w.system_type("Hydronic Supply", SUP)
    w.system_type("Hydronic Return", RET)
    w.system_type("Supply Air", "SupplyAir", duct=True)
    s["hp"] = w.equipment("HP", BIC.OST_MechanicalEquipment, [port(SUP, (10, 0, 1)), port(RET, (10, 1, 1))])
    s["man"] = w.equipment("MAN", BIC.OST_MechanicalEquipment, [
        port(SUP, (40, 0, 1), (-1, 0, 0)), port(SUP, (40, 6, 1), (-1, 0, 0)), port(RET, (40, 1, 1), (-1, 0, 0))])
    s["rad"] = w.equipment("RAD", BIC.OST_MechanicalEquipment, [port(SUP, (25, 20, 1), (0, -1, 0))])
    s["ret_only"] = w.equipment("RETONLY", BIC.OST_MechanicalEquipment, [port(RET, (10, 30, 1))])
    s["generic"] = w.equipment("GEN", BIC.OST_GenericModel, [port(SUP, (10, 40, 1))], "Generic Models")
    s["noconn"] = w.equipment("NOC", BIC.OST_MechanicalEquipment, [])
    s["hrv"] = w.equipment("HRV", BIC.OST_MechanicalEquipment, [port("SupplyAir", (50, 0, 1), domain="DomainHvac", shape="Rectangular", width=300 / 304.8, height=200 / 304.8)])
    s["panel"] = w.equipment("PANEL", BIC.OST_ElectricalEquipment, [port("PowerCircuit", (0, 0, 4), domain="DomainElectrical")])
    for i in range(1, 4):
        s["lt%d" % i] = w.equipment("LT%d" % i, BIC.OST_LightingFixtures, [port("PowerCircuit", (i, 5, 8), domain="DomainElectrical")])
    s["socket"] = w.equipment("SO1", BIC.OST_ElectricalFixtures, [port("PowerCircuit", (9, 5, 1), domain="DomainElectrical")])
    s["genl"] = w.equipment("GENL", BIC.OST_GenericModel, [port("PowerCircuit", (9, 9, 1), domain="DomainElectrical")], "Generic Models")
    s["pipe_light"] = w.equipment("PL", BIC.OST_LightingFixtures, [port(SUP, (9, 8, 1))])
    return s


class Bridge:
    """The add-in: runs the script it is handed against the stub world and records the mode."""

    def __init__(self, world: rs.World) -> None:
        self.world, self.modes, self.scripts = world, [], []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        assert name == "revit_execute_python"
        self.modes.append(args["mode"])
        self.scripts.append(args["script"])
        return {"success": True, "output": self.world.run(args["script"]), "error": ""}


class Env:
    def __init__(self, world, scene, tmp_path):
        self.w, self.s, self.bridge = world, scene, Bridge(world)
        self.module, self.ws = mep.RevitMepModule(), WorkspaceMonitor([tmp_path])

    def route(self, **args):
        return self.module.route(approved_executor=self.bridge, workspace=self.ws, **args)

    def connect(self, **args):
        return self.module.connect(approved_executor=self.bridge, workspace=self.ws, **args)

    def circuit(self, **args):
        return self.module.circuit(approved_executor=self.bridge, workspace=self.ws, **args)

    def check(self, **args):
        return self.module.check_elements(tool_executor=self.bridge, workspace=self.ws, **args)

    def owned(self, tag="MEP1", key_prefix="mep:"):
        out = []
        for e in self.w.elements:
            ent = getattr(e, "entity", None)
            if ent is not None and ent.values["tag"] == tag and ent.values["key"].startswith(key_prefix):
                out.append(e)
        return out


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(mep, "_server_in_mock_mode", lambda: False)
    revit_module = sys.modules[mep._revit_module_class().__module__]
    monkeypatch.setattr(revit_module, "_server_in_mock_mode", lambda: False)
    with rs.installed_mep(monkeypatch) as world:
        yield Env(world, build_scene(world), tmp_path)


def route_args(*routes: Dict[str, Any], **top: Any) -> Dict[str, Any]:
    args: Dict[str, Any] = {"kind": "pipe", "tag": "MEP1", "system": "hsup", "type_name": "PEX", "routes": list(routes)}
    args.update(top)
    return args


def r_straight(rid="r1", **over):
    route = {"id": rid, "level": "L0", "run_height_m": 1 * M, "size": {"diameter_mm": 32},
             "from": {"mark": "HP", "sort": "y", "index": 0}, "to": {"mark": "MAN", "sort": "y", "index": 0}}
    route.update(over)
    return route


def r_bend(rid="r2", **over):
    return r_straight(rid, **{"to": {"mark": "MAN", "sort": "y", "index": 1}, **over})


def why(result):
    keys = ("kind", "message", "summary", "fails", "info")
    out = {k: result.get(k) for k in keys}
    out["failed_checks"] = [c for c in (result.get("post_check") or {}).get("checks", []) if not c["ok"]]
    return out


def ids_of(result):
    return sorted(result["changed_ids"])


def curves_of(env, key_prefix="mep:"):
    return [e for e in env.owned(key_prefix=key_prefix) if isinstance(e, rs.PipeLike)]


def fittings_labelled(env):
    return [label for label, _ in env.w.fittings]


# --------------------------------------------------------------------------- #
# revit_mep_route
# --------------------------------------------------------------------------- #
def test_straight_route_joins_two_connectors_with_one_pipe(env):
    result = env.route(**route_args(r_straight()))
    assert result["ok"] is True and result["verified"] is True, why(result)
    pipes = curves_of(env)
    assert len(pipes) == 1 and fittings_labelled(env) == []
    p = pipes[0]
    hp, man = env.s["hp"], env.s["man"]
    assert p.c0.IsConnected and p.c1.IsConnected
    assert hp.MEPModel.ConnectorManager.Connectors[0] in p.c0.AllRefs
    assert man.MEPModel.ConnectorManager.Connectors[0] in p.c1.AllRefs
    assert abs(p.diameter * 304.8 - 32) < 1e-6
    assert result["changed_ids"] == [p.Id.Value]
    assert env.bridge.modes == ["write", "read"]  # the existing system report ran afterwards
    names = [c["check"] for c in result["post_check"]["checks"]]
    assert mep.SYSTEM_CHECK_NAME in names and result["post_check"]["failed"] == 0
    assert result["rows"][0]["length_mm"] == pytest.approx(30 * 304.8, abs=1.0)
    assert result["rows"][0]["system"] == SUP and result["rows"][0]["route"] == "r1"
    ent = p.entity.values
    assert ent == {"tag": "MEP1", "key": "mep:r1", "kind": "pipe"}


def test_route_with_a_corner_gets_pieces_elbows_and_no_open_end(env):
    result = env.route(**route_args(r_bend()))
    assert result["ok"] is True, why(result)
    pipes = curves_of(env)
    assert len(pipes) == 3 and fittings_labelled(env) == ["elbow", "elbow"]
    assert len(result["changed_ids"]) == 5
    for p in pipes:
        assert p.c0.IsConnected and p.c1.IsConnected
    # the first and last pieces were made from the equipment connectors
    assert env.s["hp"].MEPModel.ConnectorManager.Connectors[0].IsConnected
    assert env.s["man"].MEPModel.ConnectorManager.Connectors[1].IsConnected
    assert sorted(result["changed_ids"]) == sorted(e.Id.Value for e in env.owned())
    assert result["system_report"]["ran"] is True and result["open_ends"] == []


def test_a_via_point_with_a_height_makes_a_vertical_move(env):
    route = r_straight("up", via=[{"x_m": 25 * M, "y_m": 0.0, "to_height_m": 3.0}], run_height_m=1 * M)
    route["to"] = {"mark": "MAN", "sort": "y", "index": 0}
    result = env.route(**route_args(route))
    assert result["ok"] is True, why(result)
    # a via point with a height makes a vertical move there: the path has a leg in z
    zs = {round(p.Location.Curve.p0.Z, 3) for p in curves_of(env)} | {round(p.Location.Curve.p1.Z, 3) for p in curves_of(env)}
    assert len(zs) >= 2 and any(abs(z - 3.0 / M) < 0.01 for z in zs)


def test_size_change_on_a_straight_leg_gets_a_transition(env):
    route = r_straight("t", via=[{"x_m": 20 * M, "y_m": 0.0, "size": {"diameter_mm": 25}}, {"x_m": 30 * M, "y_m": 0.0, "size": {"diameter_mm": 32}}])
    result = env.route(**route_args(route))
    assert result["ok"] is True, why(result)
    assert fittings_labelled(env) == ["transition", "transition"], fittings_labelled(env)
    sizes = sorted(round(p.diameter * 304.8) for p in curves_of(env))
    assert 25 in sizes and 32 in sizes
    assert all(c["ok"] for c in result["post_check"]["checks"])


def test_size_change_at_a_corner_moves_down_the_next_leg(env):
    corner_x = 40 * M - 0.2  # the corner sits one stub (0.2 m) in front of the target connector
    route = r_bend("tc", via=[{"x_m": corner_x, "y_m": 0.0, "size": {"diameter_mm": 25}}, {"x_m": corner_x, "y_m": 5 * M, "size": {"diameter_mm": 32}}])
    result = env.route(**route_args(route, transition_m=0.2))
    assert result["ok"] is True, why(result)
    labels = fittings_labelled(env)
    assert labels.count("elbow") == 2 and labels.count("transition") == 2, labels


def test_route_from_a_free_point_needs_a_system_type_and_may_end_open(env):
    route = {"id": "free", "level": "L0", "run_height_m": 2 * M, "size": {"diameter_mm": 40},
             "from": {"point_m": [5 * M, 5 * M, 2 * M]}, "to": {"point_m": [20 * M, 5 * M, 2 * M]}}
    result = env.route(**route_args(route))
    assert result["ok"] is True, why(result)
    p = curves_of(env)[0]
    assert (p.Location.Curve.p0.X, p.Location.Curve.p1.X) == (pytest.approx(5), pytest.approx(20))
    assert result["changed_ids"] == [p.Id.Value]
    # both ends are planned free ends: the piece is waived in the system report instead of failing it
    assert "'allow_open_ids': [%d]" % p.Id.Value in env.bridge.scripts[-1]
    assert env.bridge.modes == ["write", "read"] and result["open_ends"] == []


def test_route_from_a_free_point_without_a_system_type_is_refused(env):
    env.w.elements[:] = [e for e in env.w.elements if not isinstance(e, rs.PipingSystemType) or isinstance(e, rs.MechanicalSystemType)]
    route = {"id": "free", "level": "L0", "run_height_m": 0.5, "size": {"diameter_mm": 40},
             "from": {"point_m": [1, 1, 0.5]}, "to": {"mark": "MAN", "sort": "y", "index": 0}}
    before = env.w.snapshot()
    result = env.route(**route_args(route))
    assert result["ok"] is False and result["kind"] == "system_type_not_found"
    assert env.w.snapshot() == before and env.w.txn_log == []


def test_duct_route_with_a_rectangular_size(env):
    hrv = env.s["hrv"]
    env.w.equipment("TERM", BIC.OST_DuctTerminal, [port("SupplyAir", (60, 20, 1), (0, -1, 0), domain="DomainHvac", shape="Rectangular", width=300 / 304.8, height=200 / 304.8)])
    route = {"id": "d1", "level": "L0", "run_height_m": 1 * M, "size": {"width_mm": 300, "height_mm": 200},
             "from": {"mark": "HRV"}, "to": {"mark": "TERM"}}
    result = env.route(kind="duct", tag="MEP1", system="supply", type_name="Round Duct", routes=[route])
    assert result["ok"] is True, why(result)
    ducts = [e for e in env.owned() if isinstance(e, rs.StubDuct)]
    assert ducts and all(d.entity.values["kind"] == "duct" for d in ducts)
    assert abs(ducts[0].parameters[rs.BuiltInParameter.RBS_CURVE_WIDTH_PARAM].value * 304.8 - 300) < 1e-6
    assert hrv.MEPModel.ConnectorManager.Connectors[0].IsConnected


def test_branch_with_a_takeoff_ends_on_the_trunk(env):
    trunk = r_straight("trunk")
    branch = {"id": "br", "level": "L0", "size": {"diameter_mm": 32}, "from": {"mark": "RAD"},
              "branch_to": {"route": "trunk"}}
    result = env.route(**route_args(trunk, branch))
    assert result["ok"] is True, why(result)
    assert "takeoff" in fittings_labelled(env)
    br = [e for e in env.owned(key_prefix="mep:br") if isinstance(e, rs.PipeLike)]
    assert br and any(c.IsConnected for c in br[-1].ConnectorManager.Connectors)
    trunk_pipe = [e for e in env.owned(key_prefix="mep:trunk")][0]
    assert any(not getattr(c, "kind_curve", True) for c in trunk_pipe.ConnectorManager.Connectors)  # the tap
    assert all(c["ok"] for c in result["post_check"]["checks"])


def test_branch_with_a_tee_splits_the_trunk_and_keeps_both_halves_owned(env):
    trunk = r_straight("trunk")
    branch = {"id": "br", "level": "L0", "size": {"diameter_mm": 32}, "from": {"mark": "RAD"},
              "branch_to": {"route": "trunk", "fitting": "tee"}}
    result = env.route(**route_args(trunk, branch))
    assert result["ok"] is True, why(result)
    assert "tee" in fittings_labelled(env)
    halves = [e for e in env.owned(key_prefix="mep:trunk") if isinstance(e, rs.PipeLike)]
    assert len(halves) == 2
    assert all(h.entity.values["tag"] == "MEP1" for h in halves)
    assert len(result["changed_ids"]) == len(set(result["changed_ids"])) == len(env.owned())


def test_branch_from_a_free_point_is_a_riser(env):
    trunk = r_straight("trunk")
    riser = {"id": "riser", "level": "L0", "size": {"diameter_mm": 32}, "from": {"point_m": [25 * M, 0.0, 6 * M]},
             "branch_to": {"route": "trunk"}}
    result = env.route(**route_args(trunk, riser))
    assert result["ok"] is True, why(result)
    p = [e for e in env.owned(key_prefix="mep:riser") if isinstance(e, rs.PipeLike)][0]
    assert p.Location.Curve.p0.X == pytest.approx(p.Location.Curve.p1.X)  # vertical
    assert fittings_labelled(env) == ["takeoff"]


def test_a_tee_needs_a_trunk_made_by_this_tool(env):
    pipe = env.w.add(rs.StubPipe(900, (12, 0, 1), (30, 0, 1), SUP, 1, 1, 1))
    branch = {"id": "br", "level": "L0", "size": {"diameter_mm": 32}, "from": {"mark": "RAD"},
              "branch_to": {"element_ids": [900], "fitting": "tee"}}
    before = env.w.snapshot()
    result = env.route(**route_args(branch))
    assert result["kind"] == "tee_needs_owned_trunk" and env.w.snapshot() == before
    assert pipe in env.w.elements


def test_an_unknown_trunk_is_refused_before_changes(env):
    branch = {"id": "br", "level": "L0", "size": {"diameter_mm": 32}, "from": {"mark": "RAD"}, "branch_to": {"route": "nope"}}
    before = env.w.snapshot()
    result = env.route(**route_args(branch))
    assert result["kind"] == "trunk_not_found" and env.w.snapshot() == before


def test_two_routes_from_the_same_equipment_take_different_connectors(env):
    # both routes ask for "the first supply connector of MAN": the second one must get the next free one
    a = r_straight("a", **{"from": {"mark": "HP", "sort": "y"}, "to": {"mark": "MAN", "diameter_mm": [30, 34], "sort": "y"}})
    b = r_straight("b", **{"from": {"mark": "RAD"}, "to": {"mark": "MAN", "diameter_mm": [30, 34], "sort": "y"}})
    result = env.route(**route_args(a, b))
    assert result["ok"] is True, why(result)
    man_ports = [c for c in env.s["man"].MEPModel.ConnectorManager.Connectors if c.sys == SUP]
    assert all(c.IsConnected for c in man_ports)


def test_rerun_replaces_only_what_the_tool_made(env):
    first = env.route(**route_args(r_bend()))
    assert first["ok"] is True
    foreign = env.w.add(rs.StubPipe(901, (0, 50, 1), (5, 50, 1), SUP, 1, 1, 1))
    count = len(env.w.elements)
    second = env.route(**route_args(r_bend()))
    assert second["ok"] is True, second
    assert len(env.w.elements) == count  # same number of elements: the old pieces went, new ones came
    assert foreign in env.w.elements
    assert not set(first["changed_ids"]) & set(second["changed_ids"])
    assert sorted(second["changed_ids"]) == sorted(e.Id.Value for e in env.owned())
    assert "replaced" in second["summary"]
    assert all(c.IsConnected for c in env.s["man"].MEPModel.ConnectorManager.Connectors[1:2])


def test_replacement_that_would_delete_a_foreign_element_is_refused_and_changes_nothing(env):
    first = env.route(**route_args(r_bend()))
    victim = env.w.add(rs.StubPipe(902, (0, 60, 1), (5, 60, 1), SUP, 1, 1, 1))
    env.w.cascade[first["changed_ids"][0]] = [victim.Id.Value]
    before = env.w.snapshot()
    result = env.route(**route_args(r_bend()))
    assert result["ok"] is False and result["kind"] == "rolled_back"
    assert "foreign dependent" in result["message"] and victim.Id.Value in result["element_ids"]
    assert result["changed_ids"] == [] and env.w.snapshot() == before
    assert victim in env.w.elements


def test_a_tool_never_deletes_elements_it_did_not_tag(env):
    env.route(**route_args(r_bend()))
    stray = env.w.add(rs.StubPipe(903, (0, 70, 1), (5, 70, 1), SUP, 1, 1, 1))
    env.route(**route_args(r_bend()))
    assert stray in env.w.elements and stray.entity is None


# ---- the category guard -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mark,code,needle", [
    ("GEN", "category_mismatch", "not a piping element"),
    ("NOC", "no_connectors", "no pipe, duct or electrical connectors"),
    ("HRV", "domain_mismatch", "only in the Hvac domain"),
    ("RETONLY", "system_mismatch", "no piping connector of system SupplyHydronic"),
    ("PL", "category_mismatch", "not a piping element"),
    ("PANEL", "category_mismatch", "not a piping element"),
])
def test_guard_refuses_a_family_that_is_not_mep_for_the_system(env, mark, code, needle):
    before = env.w.snapshot()
    result = env.route(**route_args(r_straight(**{"from": {"mark": mark}})))
    assert result["ok"] is False and result["kind"] == code, result
    assert needle in result["message"] and mark in result["message"]
    assert result["changed_ids"] == []
    assert result["element_ids"], "the refused element is named"
    assert env.w.snapshot() == before
    assert env.w.txn_log == [], "no transaction may start before the guard has passed"
    assert env.bridge.modes == ["write"]


def test_guard_checks_every_route_and_reports_all_of_them(env):
    bad_a = r_straight("a", **{"from": {"mark": "GEN"}})
    bad_b = r_straight("b", **{"to": {"mark": "NOC"}})
    result = env.route(**route_args(r_straight("ok"), bad_a, bad_b))
    assert result["kind"] == "category_mismatch" and len(result["fails"]) == 2
    assert env.owned() == [] and env.w.txn_log == []


def test_guard_refuses_a_duct_family_in_a_pipe_route_and_a_pipe_family_in_a_circuit(env):
    r = env.route(**route_args(r_straight(**{"to": {"mark": "HRV"}})))
    assert r["kind"] == "domain_mismatch"
    c = env.circuit(tag="MEP1", circuits=[{"id": "C", "panel": {"mark": "PANEL"}, "elements": [{"mark": "PL"}]}])
    assert c["kind"] == "domain_mismatch" and "only in the Piping domain" in c["message"]
    assert env.owned() == []


def test_guard_refuses_a_connector_that_is_already_connected(env):
    env.route(**route_args(r_straight("first")))
    result = env.route(**route_args(r_straight("second", **{"from": {"mark": "HP", "sort": "y", "index": 0}})))
    # HP supply is connected now; asking for it again must not silently reuse or place anything
    assert result["ok"] is False and result["kind"] == "no_free_connector", why(result)
    assert [e for e in env.owned(key_prefix="mep:second")] == []


def test_missing_things_are_named(env):
    r = env.route(**route_args(r_straight(**{"from": {"mark": "NOPE"}})))
    assert r["kind"] == "element_not_found" and "NOPE" in r["message"]
    r = env.route(**route_args(r_straight(level="L9")))
    assert r["kind"] == "level_not_found" and "L9" in r["message"]
    r = env.route(**route_args(r_straight(), type_name="Copper"))
    assert r["kind"] == "type_not_found" and "PEX" in r["message"]
    r = env.route(**route_args(r_straight(**{"to": {"mark": "MAN", "diameter_mm": [90, 100]}})))
    assert r["kind"] == "no_free_connector" and "diameter" in r["message"]
    assert env.w.txn_log == []


def test_duplicate_route_ids_are_refused(env):
    r = env.route(**route_args(r_straight("same"), r_bend("same")))
    assert r["kind"] == "duplicate_route_id" and env.w.txn_log == []


# ---- transactions, rollback, warnings ------------------------------------------------------------------------------
def test_one_transaction_group_and_one_transaction_per_route(env):
    a = r_straight("a")
    b = r_straight("b", **{"from": {"mark": "RAD"}, "to": {"mark": "MAN", "sort": "y", "index": 0}})
    result = env.route(**route_args(a, b))
    assert result["ok"] is True, why(result)
    log = env.w.txn_log
    assert log[0][0] == "group_start" and log[-1][0] == "group_assimilate"
    starts = [n for kind, n in log if kind == "start"]
    assert starts == ["Route a", "Route b"]
    assert [n for kind, n in log if kind == "commit"] == starts


def test_abort_rolls_the_whole_call_back_and_names_the_failure(env):
    before = env.w.snapshot()
    env.w.fail_on["create_pipe"] = lambda n: n == 5  # the first route needs 1 pipe, the second fails on its 4th piece
    a = r_straight("a")
    b = r_bend("b", **{"from": {"mark": "RAD"}})
    b["to"] = {"mark": "MAN", "sort": "y", "index": 0}
    result = env.route(**route_args(a, b))
    assert result["ok"] is False and result["kind"] == "rolled_back", result
    assert "Revit refused create_pipe" in result["message"] and "Route b" in result["message"]
    assert result["changed_ids"] == [] and "unchanged" in result["summary"]
    assert env.w.snapshot() == before and env.owned() == []
    assert not env.s["hp"].MEPModel.ConnectorManager.Connectors[0].IsConnected
    assert env.w.txn_log[-1][0] == "group_rollback" and env.bridge.modes == ["write"]


def test_skip_keeps_what_worked_and_lists_the_failure(env):
    env.w.fail_on["create_pipe"] = lambda n: n == 2
    a = r_straight("a")
    b = r_straight("b", **{"from": {"mark": "RAD"}, "to": {"mark": "MAN", "sort": "y", "index": 0}})
    result = env.route(**route_args(a, b, on_error="skip"))
    assert result["ok"] is False and result["kind"] == "partial_failure", result
    assert len(result["changed_ids"]) == 1 and len(curves_of(env, "mep:a")) == 1
    assert curves_of(env, "mep:b") == []
    assert "Revit refused create_pipe" in result["message"]
    assert env.w.txn_log[-1][0] == "group_assimilate"
    assert not env.s["rad"].MEPModel.ConnectorManager.Connectors[0].IsConnected  # the failed route left nothing behind


def test_warnings_are_dismissed_and_listed(env):
    env.w.commit_failures["Route r1"] = [base.Failure("Pipe is slightly off axis", "Warning", [])]
    result = env.route(**route_args(r_straight()))
    assert result["ok"] is True and result["warnings_dismissed"] == 1
    assert any("slightly off axis" in i for i in result["info"])


def test_an_error_level_failure_rolls_the_call_back(env):
    env.w.commit_failures["Route r1"] = [base.Failure("Elements are overlapping", "Error", [])]
    before = env.w.snapshot()
    result = env.route(**route_args(r_straight()))
    assert result["ok"] is False and result["kind"] == "rolled_back" and "overlapping" in result["message"]
    assert env.w.snapshot() == before


def test_a_failing_post_check_in_abort_mode_rolls_back(env, monkeypatch):
    original = rs.PipeLike.apply_param

    def lossy(self, key, value):  # Revit "accepts" the size but keeps another one
        original(self, key, value * 0.5 if key == self.size_key else value)

    monkeypatch.setattr(rs.PipeLike, "apply_param", lossy)
    # the Param stores what was set; the element keeps half of it: the read-back differs only through the connector,
    # so make the parameter itself lie
    monkeypatch.setattr(rs.Param, "AsDouble", lambda self: float(self.value) * 0.5 if self.key == getattr(self.owner, "size_key", None) else float(self.value))
    before = env.w.snapshot()
    result = env.route(**route_args(r_straight()))
    assert result["ok"] is False and result["kind"] == "rolled_back", result
    assert "sizes as requested" in result["message"] and env.w.snapshot() == before
    assert result["post_check"]["failed"] >= 1


def test_a_failing_post_check_in_skip_mode_keeps_the_model_but_is_never_ok(env, monkeypatch):
    monkeypatch.setattr(rs.Param, "AsDouble", lambda self: float(self.value) * 0.5 if self.key == getattr(self.owner, "size_key", None) else float(self.value))
    result = env.route(**route_args(r_straight(), on_error="skip"))
    assert result["ok"] is False and result["kind"] == "post_check_failed"
    assert result["changed_ids"] and result["post_check"]["ok"] is False
    assert len(env.owned()) == 1


def test_an_open_end_the_script_did_not_plan_is_a_failed_post_check(env):
    # the stub refuses nothing here: break the join on purpose so one piece end stays open
    original = rs._Creator.NewElbowFitting

    def no_join(self, a, b):
        f = original(self, a, b)
        for c in list(a.AllRefs):
            a.disconnect(c)
        return f

    rs._Creator.NewElbowFitting = no_join
    try:
        result = env.route(**route_args(r_bend()))
    finally:
        rs._Creator.NewElbowFitting = original
    assert result["ok"] is False and result["kind"] == "rolled_back" and "open ends" in result["message"]


# --------------------------------------------------------------------------- #
# revit_mep_connect
# --------------------------------------------------------------------------- #
def touching_pipe(env, eid, start, end, system=SUP, connect_start=None):
    p = env.w.add(rs.StubPipe(eid, start, end, system, 1, 1, 1))
    if connect_start is not None:
        connect_start.ConnectTo(p.c0)
    return p


def conn_args(*items, **top):
    args = {"kind": "pipe", "tag": "MEP1", "system": "hsup", "connections": list(items)}
    args.update(top)
    return args


def test_equipment_and_a_touching_pipe_end_are_joined_directly(env):
    p = touching_pipe(env, 910, (10, 0, 1), (20, 0, 1))
    result = env.connect(**conn_args({"id": "c1", "a": {"mark": "HP", "sort": "y"}, "b": {"element_id": 910, "near_m": [10 * M, 0, 1 * M]}}))
    assert result["ok"] is True, why(result)
    assert env.s["hp"].MEPModel.ConnectorManager.Connectors[0] in p.c0.AllRefs
    assert result["rows"][0]["joint"] == "direct" and result["rows"][0]["status"] == "connected"
    assert sorted(result["changed_ids"]) == sorted([env.s["hp"].Id.Value, 910])
    assert env.w.fittings == []
    # open ends are listed (the far end of the pipe), but they do not fail a connect
    assert result["open_ends"] and result["open_ends"][0]["element_id"] == 910
    assert env.bridge.modes == ["write", "read"]


def test_two_pipes_meeting_at_a_corner_get_an_elbow(env):
    a = touching_pipe(env, 911, (0, 0, 1), (10, 0, 1))
    b = env.w.add(rs.StubPipe(912, (10, 0, 1), (10, 10, 1), SUP, 1, 1, 1))
    result = env.connect(**conn_args({"id": "c1", "a": {"element_id": 911, "near_m": [10 * M, 0, M]}, "b": {"element_id": 912, "near_m": [10 * M, 0, M]}}))
    assert result["ok"] is True, why(result)
    assert fittings_labelled(env) == ["elbow"] and result["rows"][0]["joint"] == "elbow"
    fid = result["rows"][0]["id"]
    assert fid in result["changed_ids"] and env.w.GetElement(fid).entity.values == {"tag": "MEP1", "key": "mep:connect:c1", "kind": "fitting"}
    assert a.c1.IsConnected and b.c0.IsConnected


def test_straight_joints_get_a_union_or_a_transition(env):
    touching_pipe(env, 913, (0, 0, 1), (10, 0, 1))
    c = env.w.add(rs.StubPipe(914, (10, 0, 1), (20, 0, 1), SUP, 1, 1, 1))
    result = env.connect(**conn_args({"id": "u", "a": {"element_id": 913, "near_m": [10 * M, 0, M]}, "b": {"element_id": 914, "near_m": [10 * M, 0, M]}}))
    assert result["ok"] is True and fittings_labelled(env) == ["union"]
    touching_pipe(env, 915, (30, 0, 1), (40, 0, 1))
    d = env.w.add(rs.StubPipe(916, (40, 0, 1), (50, 0, 1), SUP, 1, 1, 1))
    d.c0.Radius = 0.03
    result = env.connect(**conn_args({"id": "t", "a": {"element_id": 915, "near_m": [40 * M, 0, M]}, "b": {"element_id": 916, "near_m": [40 * M, 0, M]}}))
    assert result["ok"] is True and fittings_labelled(env) == ["union", "transition"]
    assert c.c0.IsConnected


def test_connectors_that_are_apart_are_never_moved_or_routed(env):
    touching_pipe(env, 917, (0, 0, 1), (10, 0, 1))
    before = env.w.snapshot()
    result = env.connect(**conn_args({"id": "far", "a": {"element_id": 917, "near_m": [10 * M, 0, M]}, "b": {"mark": "MAN", "sort": "y"}}))
    assert result["ok"] is False and result["kind"] == "not_coincident" and "revit_mep_route" in result["message"]
    assert env.w.snapshot() == before and env.w.txn_log == []


def test_connect_is_idempotent(env):
    touching_pipe(env, 918, (10, 0, 1), (20, 0, 1))
    args = conn_args({"id": "c1", "a": {"mark": "HP", "sort": "y"}, "b": {"element_id": 918, "near_m": [10 * M, 0, M]}})
    first = env.connect(**args)
    count = len(env.w.elements)
    second = env.connect(**args)
    assert first["ok"] and second["ok"] is True, second
    assert second["rows"][0]["status"] == "already_connected" and len(env.w.elements) == count
    assert any("ALREADY_CONNECTED" in i for i in second["info"])


def test_a_connector_in_use_by_something_else_is_refused(env):
    touching_pipe(env, 919, (10, 0, 1), (20, 0, 1), connect_start=env.s["hp"].MEPModel.ConnectorManager.Connectors[0])
    touching_pipe(env, 920, (10, 0, 1), (5, 0, 1))
    result = env.connect(**conn_args({"id": "c", "a": {"mark": "HP", "sort": "y"}, "b": {"element_id": 920, "near_m": [10 * M, 0, M]}}))
    assert result["ok"] is False and result["kind"] == "connector_in_use"


def test_connect_guard_and_system_checks(env):
    touching_pipe(env, 921, (10, 30, 1), (20, 30, 1))
    r = env.connect(**conn_args({"id": "g", "a": {"mark": "GEN"}, "b": {"element_id": 921}}))
    assert r["kind"] == "category_mismatch" and env.w.txn_log == []
    r = env.connect(**conn_args({"id": "g", "a": {"mark": "RETONLY"}, "b": {"element_id": 921, "near_m": [10 * M, 30 * M, M]}}))
    assert r["kind"] == "system_mismatch"
    r = env.connect(**conn_args({"id": "g", "a": {"mark": "HRV"}, "b": {"element_id": 921}}))
    assert r["kind"] == "domain_mismatch"
    r = env.connect(**conn_args({"id": "g", "a": {"element_id": 921}, "b": {"element_id": 921}}))
    assert r["kind"] == "same_element"
    touching_pipe(env, 925, (10, 0, 1), (20, 0, 1))
    r = env.connect(**conn_args({"id": "g", "a": {"mark": "HP", "sort": "y"}, "b": {"element_id": 925, "near_m": [10 * M, 0, M]}, "joint": "union"}))
    assert r["kind"] == "joint_needs_curves"


def test_same_flow_direction_on_both_connectors_is_refused(env):
    hp = env.w.equipment("HP2", BIC.OST_MechanicalEquipment, [port(SUP, (60, 0, 1), direction="Out")])
    p = touching_pipe(env, 922, (60, 0, 1), (70, 0, 1))
    p.c0.Direction = "Out"
    result = env.connect(**conn_args({"id": "f", "a": {"mark": "HP2"}, "b": {"element_id": 922, "near_m": [60 * M, 0, M]}}))
    assert result["kind"] == "flow_mismatch" and hp.MEPModel.ConnectorManager.Connectors[0].IsConnected is False


def test_connect_rolls_back_when_a_fitting_fails(env):
    touching_pipe(env, 923, (0, 0, 1), (10, 0, 1))
    env.w.add(rs.StubPipe(924, (10, 0, 1), (10, 10, 1), SUP, 1, 1, 1))
    env.w.fail_on["elbow"] = lambda n: True
    before = env.w.snapshot()
    result = env.connect(**conn_args({"id": "c", "a": {"element_id": 923, "near_m": [10 * M, 0, M]}, "b": {"element_id": 924, "near_m": [10 * M, 0, M]}}))
    assert result["ok"] is False and result["kind"] == "rolled_back" and "Revit refused elbow" in result["message"]
    assert env.w.snapshot() == before and result["changed_ids"] == []


# --------------------------------------------------------------------------- #
# revit_mep_circuit
# --------------------------------------------------------------------------- #
def circuit_args(*circuits, **top):
    args = {"tag": "MEP1", "circuits": list(circuits)}
    args.update(top)
    return args


C1 = {"id": "C1", "name": "C1 Lighting", "panel": {"mark": "PANEL"}, "elements": [{"mark": "LT1"}, {"mark": "LT2"}, {"mark": "SO1"}]}
C2 = {"id": "C2", "panel": {"mark": "PANEL"}, "elements": [{"mark": "LT3"}]}


def test_circuits_are_made_from_elements_and_a_panel(env):
    result = env.circuit(**circuit_args(C1, C2))
    assert result["ok"] is True and result["verified"] is True, why(result)
    circuits = [e for e in env.w.elements if isinstance(e, rs.StubElectricalSystem)]
    assert len(circuits) == 2 and sorted(result["changed_ids"]) == sorted(c.Id.Value for c in circuits)
    c1 = next(c for c in circuits if c.entity.values["key"] == "mep:circuit:C1")
    assert c1.Elements.Size == 3 and c1.BaseEquipment is env.s["panel"] and c1.SystemType == "PowerCircuit"
    assert c1.get_Parameter(rs.BuiltInParameter.RBS_ELEC_CIRCUIT_NAME).AsString() == "C1 Lighting"
    c2 = next(c for c in circuits if c is not c1)
    assert c2.get_Parameter(rs.BuiltInParameter.RBS_ELEC_CIRCUIT_NAME).AsString() == "C2"  # name defaults to the id
    assert sorted(r["elements"] for r in result["rows"]) == [1, 3]
    assert all(r["panel_id"] == env.s["panel"].Id.Value for r in result["rows"])
    assert env.bridge.modes == ["write"]  # circuits have no pipe or duct report
    assert [n for kind, n in env.w.txn_log if kind == "start"] == ["Circuit C1", "Circuit C2"]


def test_circuit_rerun_replaces_the_circuit_it_made(env):
    first = env.circuit(**circuit_args(C1))
    second = env.circuit(**circuit_args(C1))
    assert second["ok"] is True, second
    circuits = [e for e in env.w.elements if isinstance(e, rs.StubElectricalSystem)]
    assert len(circuits) == 1 and circuits[0].Id.Value == second["changed_ids"][0]
    assert first["changed_ids"] != second["changed_ids"] and "replaced" in second["summary"]
    assert len(env.s["lt1"].circuits) == 1


def test_an_element_on_a_foreign_circuit_is_refused(env):
    foreign = rs.StubElectricalSystem.Create(None, [env.s["lt1"].Id], "PowerCircuit")
    before = env.w.snapshot()
    result = env.circuit(**circuit_args(C1))
    assert result["ok"] is False and result["kind"] == "already_on_circuit"
    assert foreign.Id.Value in result["element_ids"] and env.w.snapshot() == before


@pytest.mark.parametrize("override,code", [
    ({"elements": [{"mark": "GENL"}]}, "category_mismatch"),
    ({"elements": [{"mark": "PL"}]}, "domain_mismatch"),
    ({"elements": [{"mark": "NOC"}]}, "no_connectors"),
    ({"elements": [{"mark": "NOPE"}]}, "element_not_found"),
    ({"elements": [{"mark": "PANEL"}]}, "panel_in_circuit"),
    ({"panel": {"mark": "LT1"}}, "panel_category"),
    ({"panel": {"mark": "GENL"}}, "category_mismatch"),
    ({"elements": [{"mark": "LT1"}, {"mark": "LT1"}]}, "element_in_two_circuits"),
])
def test_circuit_guard_refuses_wrong_families_before_changes(env, override, code):
    before = env.w.snapshot()
    result = env.circuit(**circuit_args({**C2, **override}))
    assert result["ok"] is False and result["kind"] == code, result
    assert env.w.snapshot() == before and env.w.txn_log == []


def test_circuit_system_must_match_the_connectors(env):
    result = env.circuit(**circuit_args(C2, system="data"))
    assert result["kind"] == "system_mismatch" and "PowerCircuit" in result["message"]


def test_a_failing_circuit_rolls_back_all_circuits(env):
    env.w.fail_on["create_circuit"] = lambda n: n == 2
    before = env.w.snapshot()
    result = env.circuit(**circuit_args(C1, C2))
    assert result["ok"] is False and result["kind"] == "rolled_back" and "Revit refused create_circuit" in result["message"]
    assert env.w.snapshot() == before and result["changed_ids"] == []
    assert env.s["lt1"].circuits == []


def test_a_circuit_with_a_failed_post_check_is_never_ok(env, monkeypatch):
    monkeypatch.setattr(rs.StubElectricalSystem, "SelectPanel", lambda self, panel: None)  # Revit "accepts" it but assigns no panel
    result = env.circuit(**circuit_args(C2))
    assert result["ok"] is False and result["kind"] == "rolled_back" and "panel assigned" in result["message"]
    assert [e for e in env.w.elements if isinstance(e, rs.StubElectricalSystem)] == []


# --------------------------------------------------------------------------- #
# revit_mep_check_elements (read only)
# --------------------------------------------------------------------------- #
def test_check_elements_reports_every_verdict_without_changing_anything(env):
    before = env.w.snapshot()
    result = env.check(kind="pipe", system="hsup", elements=[{"mark": m} for m in ("HP", "GEN", "NOC", "HRV", "RETONLY", "NOPE")])
    assert result["ok"] is True and result["would_be_refused"] == 5, result
    verdicts = {r["mark"]: r["verdict"] for r in result["rows"]}
    assert verdicts == {"HP": "ok", "GEN": "category_mismatch", "NOC": "no_connectors", "HRV": "domain_mismatch",
                        "RETONLY": "system_mismatch", "NOPE": "element_not_found"}
    assert len(result["fails"]) == 5
    hp = next(r for r in result["rows"] if r["mark"] == "HP")
    assert "Piping 2" in hp["connectors"] and hp["systems"] == "ReturnHydronic, SupplyHydronic"
    assert env.w.snapshot() == before and env.bridge.modes == ["read"] and env.w.txn_log == []
    assert result["changed_ids"] == []


def test_check_elements_for_electrical_and_free_connectors(env):
    result = env.check(kind="elec", system="power", elements=[{"mark": "LT1"}, {"mark": "PANEL"}, {"mark": "GENL"}, {"mark": "PL"}])
    verdicts = {r["mark"]: r["verdict"] for r in result["rows"]}
    assert verdicts == {"LT1": "ok", "PANEL": "ok", "GENL": "category_mismatch", "PL": "domain_mismatch"}
    env.route(**route_args(r_straight()))
    result = env.check(kind="pipe", system="hsup", need_free=True, elements=[{"mark": "RETONLY"}, {"element_id": env.s["hp"].Id.Value}])
    assert {r["verdict"] for r in result["rows"]} == {"system_mismatch", "no_free_connector"}  # HP's one supply connector is taken now
    result = env.check(kind="pipe", system="hsup", need_free=True, elements=[{"mark": "RAD"}])
    assert result["rows"][0]["verdict"] == "ok"


def test_check_elements_without_a_system_checks_category_and_domain_only(env):
    result = env.check(kind="duct", elements=[{"mark": "HRV"}, {"mark": "HP"}, {"mark": "GEN"}])
    verdicts = {r["mark"]: r["verdict"] for r in result["rows"]}
    assert verdicts == {"HRV": "ok", "HP": "domain_mismatch", "GEN": "category_mismatch"}


def test_marks_that_belong_to_two_elements_are_ambiguous(env):
    env.w.equipment("HP", BIC.OST_MechanicalEquipment, [port(SUP, (0, 0, 0))])
    result = env.check(kind="pipe", elements=[{"mark": "HP"}])
    assert result["rows"][0]["verdict"] == "element_not_found" and "2 elements have Mark 'HP'" in result["rows"][0]["message"]
