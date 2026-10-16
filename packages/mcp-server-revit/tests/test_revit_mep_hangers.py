"""revit_mep_hanger_plan and revit_mep_hanger_place: the scripts executed under CPython against a stub of the Revit API
(tests/revit_hanger_stub.py), plus the module side (spacing table, argument checks, approval gating, result contract).

This proves the layout arithmetic, the rule handling (a rule needs a source), the host split, the idempotent placement,
rollback and the line protocol. It does NOT prove that Revit accepts the same calls: that is UNVERIFIED.
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import revit_api_stub as base  # noqa: E402
import revit_hanger_stub as rh  # noqa: E402
import revit_mep_stub as rs  # noqa: E402
from revit_mcp_server.errors import BridgeError  # noqa: E402
from revit_mcp_server.modules.revit_mep import module as mep  # noqa: E402
from revit_mcp_server.security.dispatch import run_gated_tool  # noqa: E402
from revit_mcp_server.security.read_mode import validate_read_script  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402
from test_revit_mep import FakeRevit, approved, wire  # noqa: E402

SOURCE = "TEST TABLE row 1 (a made-up value for the tests, not a standard)"
RULE: Dict[str, Any] = {"id": "steel-15-50", "kind": "pipe", "material": "steel", "size_min_mm": 15, "size_max_mm": 50,
                        "max_spacing_mm": 2000, "min_fitting_distance_mm": 150, "source": SOURCE}
ARGS_PLAN: Dict[str, Any] = {"ids": [], "material": "steel", "spacing_rules": [RULE]}


class Bridge:
    """The add-in: runs the script it is handed against the stub world and records the mode."""

    def __init__(self, world: rh.HWorld) -> None:
        self.world, self.modes, self.scripts = world, [], []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        assert name == "revit_execute_python"
        self.modes.append(args["mode"])
        self.scripts.append(args["script"])
        return {"success": True, "output": self.world.run(args["script"]), "error": ""}


class Env:
    def __init__(self, world: rh.HWorld, tmp_path: Path) -> None:
        self.w, self.bridge = world, Bridge(world)
        self.module, self.ws = mep.RevitMepModule(), WorkspaceMonitor([tmp_path])
        self.l0, self.l1 = world.level("L0", 0.0), world.level("L1", 2.5 / rh.M)
        self.view = world.view3d()
        self.sym = world.hanger_family()

    def plan(self, **args: Any) -> Dict[str, Any]:
        return self.module.hanger_plan(tool_executor=self.bridge, workspace=self.ws, **args)

    def place(self, **args: Any) -> Dict[str, Any]:
        args.setdefault("tag", "HANG1")
        args.setdefault("family_name", "Rod hanger")
        args.setdefault("type_name", "Standard")
        return self.module.hanger_place(approved_executor=self.bridge, workspace=self.ws, **args)

    def owned(self, tag: str = "HANG1") -> List[Any]:
        out = []
        for e in self.w.elements:
            ent = getattr(e, "entity", None)
            if ent is not None and ent.values["tag"] == tag and ent.values["key"].startswith("hanger:"):
                out.append(e)
        return out


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(mep, "_server_in_mock_mode", lambda: False)
    revit_module = sys.modules[mep._revit_module_class().__module__]
    monkeypatch.setattr(revit_module, "_server_in_mock_mode", lambda: False)
    with rh.installed_hangers(monkeypatch) as world:
        yield Env(world, tmp_path)


def plan_args(*ids: int, **over: Any) -> Dict[str, Any]:
    args = dict(ARGS_PLAN)
    args["ids"] = list(ids)
    args.update(over)
    return args


def run_of(result: Dict[str, Any], element: Any) -> Dict[str, Any]:
    return next(r for r in result["rows"] if r["id"] == element.Id.Value)


def stations(run: Dict[str, Any]) -> List[float]:
    return [p["station_mm"] for p in run["positions"]]


def why(result: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("kind", "message", "summary", "fails", "info")
    out = {k: result.get(k) for k in keys}
    out["failed_checks"] = [c for c in (result.get("post_check") or {}).get("checks", []) if not c["ok"]]
    return out


# --------------------------------------------------------------------------- #
# The spacing table
# --------------------------------------------------------------------------- #
def test_the_shipped_table_is_empty_but_for_one_example_row():
    rules, disclaimer = mep.load_spacing_table()
    assert len(rules) == 1 and rules[0]["example"] is True
    assert rules[0]["source"] == "" and rules[0]["max_spacing_mm"] is None
    assert not mep.usable_rule(rules[0])
    assert "not an engineering calculation" in disclaimer
    raw = json.loads(mep.HANGER_TABLE.read_text(encoding="utf-8"))
    assert "EXAMPLE" in raw["rules"][0]["note"] and set(raw["fields"]) >= {"source", "max_spacing_mm", "example"}


def test_a_rule_is_usable_only_with_a_source_a_spacing_and_no_example_flag():
    ok = mep.clean_rules([RULE], "rules")[0]
    assert mep.usable_rule(ok)
    assert not mep.usable_rule({**ok, "source": "   "})
    assert not mep.usable_rule({**ok, "max_spacing_mm": None})
    assert not mep.usable_rule({**ok, "example": True})


@pytest.mark.parametrize("rules,needle", [
    ("x", "list of at most 500"),
    ([1], "must be an object"),
    ([{**RULE, "extra": 1}], "unknown keys"),
    ([{**RULE, "id": "bad id"}], "id is required"),
    ([RULE, RULE], "used twice"),
    ([{**RULE, "kind": "pump"}], "kind must be one of"),
    ([{**RULE, "size_min_mm": 60}], "smaller than size_min_mm"),
    ([{**RULE, "max_spacing_mm": 0}], "greater than 0"),
    ([{**RULE, "max_spacing_mm": -5}], "between"),
    ([{**RULE, "source": 5 * "x" * 100}], "at most 300"),
    ([{**RULE, "example": "yes"}], "true or false"),
])
def test_bad_rules_are_refused_before_anything_is_sent(env, rules, needle):
    result = env.plan(ids=[1], spacing_rules=rules)
    assert result["ok"] is False and result["kind"] == "invalid_input" and needle in result["message"]
    assert env.bridge.modes == []


def test_the_shipped_table_gives_no_positions_and_says_so(env):
    p_example = env.w.pipe((0, 0, 3), (10, 0, 3), dia_mm=20)
    p_other = env.w.pipe((0, 1, 3), (10, 1, 3), dia_mm=32)
    result = env.plan(ids=[p_example.Id.Value, p_other.Id.Value], material="example material")
    assert result["ok"] is True, why(result)
    assert run_of(result, p_example)["status"] == "example_rule" and run_of(result, p_example)["positions"] == []
    assert run_of(result, p_other)["status"] == "no_spacing_rule" and run_of(result, p_other)["positions"] == []
    assert result["totals"]["hangers"] == 0 and result["totals"]["runs_no_rule"] == 2
    assert result["spacing_table"]["usable"] == 0 and result["spacing_table"]["example_rows"] == 1
    assert any("NO_USABLE_SPACING_RULE" in i for i in result["info"])
    assert any("NO_SPACING_RULE" in i for i in result["info"])
    assert "not an engineering calculation" in result["disclaimer"]


# --------------------------------------------------------------------------- #
# revit_mep_hanger_plan: positions
# --------------------------------------------------------------------------- #
def test_hangers_sit_exactly_at_the_maximum_spacing_on_a_free_run(env):
    p = env.w.pipe((0, 0, 3), (10, 0, 3))
    result = env.plan(**plan_args(p.Id.Value))
    assert result["ok"] is True, why(result)
    run = run_of(result, p)
    assert run["status"] == "planned" and run["rule"] == "steel-15-50" and run["spacing_mm"] == 2000.0
    assert run["rule_source"] == SOURCE
    assert stations(run) == pytest.approx([0, 2000, 4000, 6000, 8000, 10000], abs=0.2)
    pos = run["positions"]
    assert [q["x_m"] for q in pos] == pytest.approx([0, 2, 4, 6, 8, 10], abs=0.002) and all(q["y_m"] == 0 and q["z_m"] == 3 for q in pos)
    assert env.bridge.modes == ["read"]
    validate_read_script(env.bridge.scripts[0])


def test_hangers_keep_the_fitting_distance_at_both_ends_and_are_centred(env):
    p = env.w.pipe((0, 0, 3), (10, 0, 3))
    env.w.fit_at(p, 0)
    env.w.fit_at(p, 1)
    run = run_of(env.plan(**plan_args(p.Id.Value)), p)
    # window 150 .. 9850 = 9700 mm: 5 hangers 2000 apart, the leftover 1700 mm split over both ends
    assert stations(run) == pytest.approx([1000, 3000, 5000, 7000, 9000], abs=0.2)
    assert run["fitting_distance_mm"] == 150.0
    assert min(stations(run)) >= 150 and max(stations(run)) <= 9850


def test_the_call_overrides_the_fitting_distance_of_the_rule(env):
    p = env.w.pipe((0, 0, 3), (4, 0, 3))
    env.w.fit_at(p, 0)
    run = run_of(env.plan(**plan_args(p.Id.Value, min_fitting_distance_mm=500)), p)
    # window 500 .. 4000 = 3500 mm: 2 hangers, 1500 mm of leftover
    assert run["fitting_distance_mm"] == 500.0
    assert stations(run) == pytest.approx([1250, 3250], abs=0.2)
    assert min(stations(run)) >= 500


def test_a_tap_in_the_middle_is_a_fitting_too(env):
    p = env.w.pipe((0, 0, 3), (10, 0, 3))
    env.w.tap_at(p, 5.0)
    run = run_of(env.plan(**plan_args(p.Id.Value)), p)
    # two windows, 0 .. 4850 and 5150 .. 10000 (4850 mm each): 3 hangers 2000 apart in each, centred
    assert stations(run) == pytest.approx([425, 2425, 4425, 5575, 7575, 9575], abs=0.2)
    assert all(abs(s - 5000) >= 150 for s in stations(run))


def test_a_run_shorter_than_two_fitting_distances_gets_no_hanger(env):
    p = env.w.pipe((0, 0, 3), (0.25, 0, 3))
    env.w.fit_at(p, 0)
    env.w.fit_at(p, 1)
    run = run_of(env.plan(**plan_args(p.Id.Value)), p)
    assert run["status"] == "too_short" and run["positions"] == []


def test_a_riser_gets_no_hangers_but_a_gentle_slope_does(env):
    riser = env.w.pipe((0, 0, 0), (0, 0, 3))
    sloped = env.w.pipe((0, 1, 3), (10, 1, 3.5))
    result = env.plan(**plan_args(riser.Id.Value, sloped.Id.Value))
    assert run_of(result, riser)["status"] == "not_horizontal" and run_of(result, riser)["positions"] == []
    run = run_of(result, sloped)
    assert run["status"] == "planned"
    length = math.hypot(10, 0.5) * 1000
    assert run["length_m"] == pytest.approx(length / 1000, abs=0.002)
    assert max(b - a for a, b in zip(stations(run), stations(run)[1:])) == pytest.approx(2000, abs=0.2)


# --------------------------------------------------------------------------- #
# revit_mep_hanger_plan: which rule applies
# --------------------------------------------------------------------------- #
def plan_one(env, p, rules, **over):
    return run_of(env.plan(**plan_args(p.Id.Value, spacing_rules=rules, **over)), p)


def test_a_rule_without_a_source_is_never_used(env):
    p = env.w.pipe((0, 0, 3), (10, 0, 3))
    for source in ("", "   "):
        run = plan_one(env, p, [{**RULE, "source": source}])
        assert run["status"] == "rule_without_source" and run["positions"] == [] and run["hangers"] == 0
        assert "rule 'steel-15-50'" in run["note"]


def test_an_example_row_is_never_used_even_with_a_source(env):
    p = env.w.pipe((0, 0, 3), (10, 0, 3))
    run = plan_one(env, p, [{**RULE, "example": True}])
    assert run["status"] == "example_rule" and run["positions"] == []


def test_a_row_still_to_be_filled_in_is_incomplete(env):
    p = env.w.pipe((0, 0, 3), (10, 0, 3))
    run = plan_one(env, p, [{**RULE, "max_spacing_mm": None}])
    assert run["status"] == "rule_incomplete" and run["positions"] == []


def test_no_matching_row_means_no_spacing_rule(env):
    p = env.w.pipe((0, 0, 3), (10, 0, 3), dia_mm=80)
    assert plan_one(env, p, [RULE])["status"] == "no_spacing_rule"
    p32 = env.w.pipe((0, 1, 3), (10, 1, 3), dia_mm=32)
    assert plan_one(env, p32, [RULE], material="copper")["status"] == "no_spacing_rule"
    assert plan_one(env, p32, [{**RULE, "kind": "duct"}])["status"] == "no_spacing_rule"
    result = env.plan(**plan_args(p.Id.Value, p32.Id.Value, spacing_rules=[RULE]))
    assert result["totals"]["runs_no_rule"] == 1 and result["totals"]["runs_planned"] == 1
    assert any("NO_SPACING_RULE" in i for i in result["info"])


def test_two_rows_that_both_match_are_ambiguous_but_a_material_row_beats_a_general_one(env):
    p = env.w.pipe((0, 0, 3), (10, 0, 3))
    other = {**RULE, "id": "second", "max_spacing_mm": 1000}
    assert plan_one(env, p, [RULE, other])["status"] == "rule_ambiguous"
    general = {**RULE, "id": "general", "material": "", "max_spacing_mm": 1000}
    run = plan_one(env, p, [general, RULE])
    assert run["status"] == "planned" and run["rule"] == "steel-15-50" and run["spacing_mm"] == 2000.0
    run = plan_one(env, p, [general, RULE], material="plastic")
    assert run["rule"] == "general" and run["spacing_mm"] == 1000.0


def test_the_size_range_is_inclusive(env):
    for dia in (15, 50):
        p = env.w.pipe((0, 0, 3), (4, 0, 3), dia_mm=dia)
        assert plan_one(env, p, [RULE])["status"] == "planned", dia


def test_rectangular_ducts_use_the_width_and_cable_trays_their_own_rules(env):
    duct = env.w.duct((0, 0, 3), (6, 0, 3), width_mm=400, height_mm=200)
    round_duct = env.w.duct((0, 1, 3), (6, 1, 3), dia_mm=250)
    tray = env.w.tray((0, 2, 3), (6, 2, 3), width_mm=300, height_mm=60)
    rules = [
        {**RULE, "id": "duct-rect", "kind": "duct", "material": "", "size_min_mm": 300, "size_max_mm": 500, "max_spacing_mm": 3000},
        {**RULE, "id": "duct-round", "kind": "duct", "material": "", "size_min_mm": 200, "size_max_mm": 300, "max_spacing_mm": 1500},
        {**RULE, "id": "tray", "kind": "cabletray", "material": "", "size_min_mm": 200, "size_max_mm": 400, "max_spacing_mm": 1200},
    ]
    result = env.plan(ids=[duct.Id.Value, round_duct.Id.Value, tray.Id.Value], spacing_rules=rules)
    assert result["ok"] is True, why(result)
    assert (run_of(result, duct)["rule"], run_of(result, duct)["size"]) == ("duct-rect", "400x200")
    assert (run_of(result, round_duct)["rule"], run_of(result, round_duct)["size"]) == ("duct-round", "dia 250")
    assert (run_of(result, tray)["rule"], run_of(result, tray)["size"]) == ("tray", "300x60")
    assert stations(run_of(result, tray)) == pytest.approx([0, 1200, 2400, 3600, 4800, 6000], abs=0.2)


# --------------------------------------------------------------------------- #
# revit_mep_hanger_plan: support hosts
# --------------------------------------------------------------------------- #
def test_hangers_are_split_by_host_availability_and_carry_host_id_and_rod_length(env):
    p = env.w.pipe((0, 0, 3), (10, 0, 3))
    floor = env.w.host("floor", (-1, -1, 3.5), (5.1, 1, 3.7))
    result = env.plan(**plan_args(p.Id.Value))
    run = run_of(result, p)
    with_host = [q for q in run["positions"] if q["support"] == "host"]
    without = [q for q in run["positions"] if q["support"] == "no support host"]
    assert [q["station_mm"] for q in with_host] == pytest.approx([0, 2000, 4000], abs=0.2) and len(without) == 3
    assert all(q["host_id"] == floor.Id.Value and q["host_category"] == "floor" and q["host_link"] == "" for q in with_host)
    # the top of the 32 mm pipe is 16 mm above its axis; the floor underside is at 3.5 m
    assert all(q["rod_mm"] == pytest.approx(500 - 16, abs=0.6) for q in with_host)
    assert all(q["host_id"] is None and q["rod_mm"] is None for q in without)
    assert (run["with_host"], run["no_host"]) == (3, 3) and run["rod_min_mm"] == run["rod_max_mm"]
    assert result["totals"]["hangers_with_host"] == 3 and result["totals"]["hangers_no_host"] == 3
    assert result["verified"] is True and "3 with a support host, 3 with no support host" in result["summary"]


def test_insulation_raises_the_attach_point(env):
    p = env.w.pipe((0, 0, 3), (4, 0, 3), insulation_mm=30)
    env.w.host("floor", (-1, -1, 3.5), (5, 1, 3.7))
    run = run_of(env.plan(**plan_args(p.Id.Value)), p)
    assert run["positions"][0]["rod_mm"] == pytest.approx(500 - 16 - 30, abs=0.6)


def test_the_nearest_host_wins_and_the_categories_are_chosen_by_the_call(env):
    p = env.w.pipe((0, 0, 3), (4, 0, 3))
    env.w.host("floor", (-1, -1, 3.8), (5, 1, 4.0))
    beam = env.w.host("beam", (-1, -0.1, 3.4), (5, 0.1, 3.6))
    ceiling = env.w.host("ceiling", (-1, -1, 3.2), (5, 1, 3.25))
    result = env.plan(**plan_args(p.Id.Value))
    assert {q["host_id"] for q in run_of(result, p)["positions"]} == {beam.Id.Value}  # ceilings are off by default
    result = env.plan(**plan_args(p.Id.Value, host_categories=["floors", "ceilings"]))
    assert {q["host_id"] for q in run_of(result, p)["positions"]} == {ceiling.Id.Value}
    result = env.plan(**plan_args(p.Id.Value, host_categories=["beams"]))
    assert {q["host_category"] for q in run_of(result, p)["positions"]} == {"beam"}


def test_a_host_beyond_the_reach_is_no_support_host(env):
    p = env.w.pipe((0, 0, 3), (4, 0, 3))
    env.w.host("floor", (-1, -1, 7), (5, 1, 7.2))
    run = run_of(env.plan(**plan_args(p.Id.Value)), p)
    assert {q["support"] for q in run["positions"]} == {"no support host"}
    run = run_of(env.plan(**plan_args(p.Id.Value, max_reach_mm=5000)), p)
    assert {q["support"] for q in run["positions"]} == {"host"}


def test_a_host_in_a_linked_model_is_found_with_the_link_and_its_own_id(env):
    p = env.w.pipe((0, 0, 3), (4, 0, 3))
    li, link_doc = env.w.link(offset_m=(0, 0, 0.5))
    slab = env.w.host("floor", (-1, -1, 3.0), (5, 1, 3.2), into=link_doc)
    run = run_of(env.plan(**plan_args(p.Id.Value)), p)
    first = run["positions"][0]
    assert first["host_id"] == slab.Id.Value and first["host_link"] == str(li.Id.Value) and first["host_category"] == "floor"
    assert first["rod_mm"] == pytest.approx(500 - 16, abs=0.6)
    run = run_of(env.plan(**plan_args(p.Id.Value, include_links=False)), p)
    assert {q["support"] for q in run["positions"]} == {"no support host"}


def test_without_a_3d_view_the_host_is_unknown_not_missing(env):
    env.w.elements.remove(env.view)
    p = env.w.pipe((0, 0, 3), (4, 0, 3))
    env.w.host("floor", (-1, -1, 3.5), (5, 1, 3.7))
    result = env.plan(**plan_args(p.Id.Value))
    run = run_of(result, p)
    assert {q["support"] for q in run["positions"]} == {"host_unknown"} and run["no_host"] == 0
    assert result["verified"] is False and result["limits"]["partial"] is True
    assert any("NO_3D_VIEW" in i for i in result["info"])
    assert result["totals"]["hangers_host_unknown"] == len(run["positions"])
    assert rh.ReferenceIntersector.rays == 0


def test_no_rays_are_cast_for_runs_without_positions(env):
    p = env.w.pipe((0, 0, 3), (10, 0, 3), dia_mm=80)
    env.w.host("floor", (-1, -1, 3.5), (5, 1, 3.7))
    env.plan(**plan_args(p.Id.Value))
    assert rh.ReferenceIntersector.rays == 0


# --------------------------------------------------------------------------- #
# revit_mep_hanger_plan: scope, budgets, paging
# --------------------------------------------------------------------------- #
def test_a_scope_is_required_and_the_model_is_never_scanned_unasked(env):
    result = env.plan(spacing_rules=[RULE])
    assert result["ok"] is False and result["kind"] == "invalid_input" and "scope" in result["message"]
    assert env.bridge.modes == []


def test_scope_by_system_level_and_view(env):
    a = env.w.pipe((0, 0, 3), (4, 0, 3), system_name="Heating supply")
    b = env.w.pipe((0, 1, 3), (4, 1, 3), system_name="Cold water")
    c = env.w.pipe((0, 2, 3), (4, 2, 3))
    c.ReferenceLevel = env.l1
    a.ReferenceLevel = env.l0
    b.ReferenceLevel = env.l0
    ids = lambda r: sorted(x["id"] for x in r["rows"])  # noqa: E731
    assert ids(env.plan(system="heating", spacing_rules=[RULE], material="steel")) == [a.Id.Value]
    assert ids(env.plan(level="L1", spacing_rules=[RULE], material="steel")) == [c.Id.Value]
    assert ids(env.plan(level="L0", spacing_rules=[RULE], material="steel")) == sorted([a.Id.Value, b.Id.Value])
    env.w.view_members[env.view.Id.Value] = [b.Id.Value]
    assert ids(env.plan(view_id=env.view.Id.Value, spacing_rules=[RULE], material="steel")) == [b.Id.Value]
    result = env.plan(view_id=999999, spacing_rules=[RULE])
    assert result["ok"] is False and result["kind"] == "invalid_input" and "999999" in result["message"]


def test_ids_that_are_not_runs_or_do_not_exist_are_listed_not_used(env):
    p = env.w.pipe((0, 0, 3), (4, 0, 3))
    slab = env.w.host("floor", (0, 0, 3), (1, 1, 3.2))
    result = env.plan(**plan_args(p.Id.Value, slab.Id.Value, 424242))
    assert [r["id"] for r in result["rows"]] == [p.Id.Value]
    assert any("NOT_A_RUN" in i and str(slab.Id.Value) in i for i in result["info"])
    assert any("ID_NOT_FOUND" in i and "424242" in i for i in result["info"])
    result = env.plan(**plan_args(p.Id.Value, categories=["ducts"]))
    assert result["rows"] == []


def test_max_elements_truncates_and_says_so(env):
    pipes = [env.w.pipe((0, i, 3), (4, i, 3)) for i in range(5)]
    result = env.plan(**plan_args(*[p.Id.Value for p in pipes], max_elements=2))
    assert result["ok"] is True and len(result["rows"]) == 2
    assert result["totals"]["truncated"] is True and result["totals"]["truncated_reason"] == "max_elements"
    assert result["limits"]["truncated"] is True and result["verified"] is False
    assert any("TRUNCATED" in i for i in result["info"]) and "TRUNCATED" in result["summary"]


def test_max_hangers_stops_before_a_run_that_would_exceed_it(env):
    pipes = [env.w.pipe((0, i, 3), (10, i, 3)) for i in range(3)]  # 6 hangers each
    result = env.plan(**plan_args(*[p.Id.Value for p in pipes], max_hangers=10))
    assert len(result["rows"]) == 1 and result["totals"]["hangers"] == 6
    assert result["totals"]["truncated_reason"] == "max_hangers" and result["verified"] is False


def test_the_time_budget_stops_the_work(env):
    pipes = [env.w.pipe((0, i, 3), (4, i, 3)) for i in range(3)]
    base.Stopwatch.tick = 5000
    try:
        result = env.plan(**plan_args(*[p.Id.Value for p in pipes], time_budget_s=1))
    finally:
        base.Stopwatch.tick = 0
    assert result["totals"]["truncated_reason"] == "time_budget_s" and len(result["rows"]) < 3 and result["limits"]["truncated"] is True


def test_runs_are_paged_with_their_positions_nested(env):
    pipes = [env.w.pipe((0, i, 3), (4, i, 3)) for i in range(4)]
    ids = [p.Id.Value for p in pipes]
    first = env.plan(**plan_args(*ids, limit=2))
    assert [r["id"] for r in first["rows"]] == ids[:2] and first["limits"]["truncated"] is True
    assert all(len(r["positions"]) == 3 for r in first["rows"])
    second = env.plan(**plan_args(*ids, limit=2, offset=2))
    assert [r["id"] for r in second["rows"]] == ids[2:] and second["limits"]["truncated"] is False
    assert first["counts"]["rows"] == 4 and second["totals"]["runs"] == 4


def test_unreadable_runs_are_reported_not_guessed(env):
    p = env.w.pipe((0, 0, 3), (4, 0, 3))
    del p.parameters[rs.BuiltInParameter.RBS_PIPE_DIAMETER_PARAM]
    q = env.w.pipe((0, 1, 3), (4, 1, 3))
    q.Location = None
    result = env.plan(**plan_args(p.Id.Value, q.Id.Value))
    assert run_of(result, p)["status"] == "size_unreadable" and run_of(result, q)["status"] == "not_straight"
    assert result["verified"] is False and any("RUNS_UNMEASURED" in i for i in result["info"])


@pytest.mark.parametrize("args,needle", [
    ({"categories": ["walls"]}, "unknown value"),
    ({"ids": "5"}, "list of at most 2000"),
    ({"ids": [0]}, "ids must be between"),
    ({"host_categories": ["roofs"]}, "unknown value"),
    ({"max_reach_mm": 50}, "max_reach_mm must be between"),
    ({"max_elements": 0}, "max_elements must be between"),
    ({"max_hangers": 99999}, "max_hangers must be between"),
    ({"time_budget_s": 99}, "time_budget_s must be between"),
    ({"include_links": "yes"}, "true or false"),
    ({"min_fitting_distance_mm": -1}, "min_fitting_distance_mm must be between"),
    ({"material": "x" * 80}, "at most 60"),
    ({"view_id": 0}, "view_id must be between"),
])
def test_bad_plan_arguments_are_refused_before_anything_is_sent(env, args, needle):
    result = env.plan(**{"ids": [1], "spacing_rules": [RULE], **args})
    assert result["ok"] is False and result["kind"] == "invalid_input" and needle in result["message"], result
    assert env.bridge.modes == []


# --------------------------------------------------------------------------- #
# revit_mep_hanger_place
# --------------------------------------------------------------------------- #
def scene_with_floor(env, length_m: float = 6.0):
    p = env.w.pipe((0, 0, 3), (length_m, 0, 3))
    floor = env.w.host("floor", (-1, -1, 3.5), (length_m + 1, 1, 3.7))
    return p, floor


def place_args(p, **over: Any) -> Dict[str, Any]:
    args = {"ids": [p.Id.Value], "material": "steel", "spacing_rules": [RULE], "rod_length_parameter": "Rod length"}
    args.update(over)
    return args


def test_hangers_are_placed_tagged_marked_and_read_back(env):
    p, floor = scene_with_floor(env)
    result = env.place(**place_args(p))
    assert result["ok"] is True and result["verified"] is True, why(result)
    made = env.w.instances_of(env.sym)
    assert len(made) == 4 and sorted(result["changed_ids"]) == sorted(e.Id.Value for e in made)
    assert result["committed"] is True and result["dry_run"] is False
    for e in made:
        ent = e.entity.values
        assert ent["tag"] == "HANG1" and ent["kind"] == "hanger" and ent["key"].startswith("hanger:%d:" % p.Id.Value)
        assert e.get_Parameter("comments").AsString() == "AEC-HANGER HANG1 " + ent["key"]
        assert e.named["Rod length"].AsDouble() * 304.8 == pytest.approx(500 - 16, abs=0.6)
        assert e.Location.Point.Y == 0 and e.Location.Point.Z * rh.M == pytest.approx(3.0, abs=1e-6)
        assert e.LevelId == env.l1.Id  # the highest level at or below the hanger
    assert sorted(round(e.Location.Point.X * rh.M, 3) for e in made) == [0.0, 2.0, 4.0, 6.0]
    assert result["post_check"]["ok"] is True and result["post_check"]["checked"] == 4
    assert env.bridge.modes == ["write"]
    items = result["rows"]
    assert len(items) == 4 and {i["status"] for i in items} == {"created"} and all(i["host_id"] == floor.Id.Value for i in items)
    assert all(i["rod_mm"] == pytest.approx(484, abs=0.6) for i in items)
    assert "not an engineering calculation" in result["disclaimer"] and result["spacing_table"]["usable"] == 1


def test_hangers_are_turned_to_follow_the_run(env):
    along_x, _ = scene_with_floor(env)
    along_y = env.w.pipe((10, 0, 3), (10, 4, 3))
    env.w.host("floor", (9, -1, 3.5), (11, 5, 3.7))
    result = env.place(**place_args(along_x, ids=[along_x.Id.Value, along_y.Id.Value]))
    assert result["ok"] is True, why(result)
    for e in env.w.instances_of(env.sym):
        want = 0.0 if e.Location.Point.X * rh.M < 9 else math.pi / 2
        assert e.angle == pytest.approx(want, abs=1e-9)
    result = env.place(**place_args(along_y, tag="HANG2", align_to_run=False))
    assert result["ok"] is True
    assert all(e.angle == 0.0 for e in env.w.instances_of(env.sym) if e.entity.values["tag"] == "HANG2")


def test_a_second_run_places_nothing_and_changes_nothing(env):
    p, _ = scene_with_floor(env)
    first = env.place(**place_args(p))
    before = env.w.snapshot()
    again = env.place(**place_args(p))
    assert again["ok"] is True and again["changed_ids"] == [] and again["committed"] is True
    assert "nothing to place" in again["summary"]
    assert {i["status"] for i in again["rows"]} == {"skipped_existing"} and len(again["rows"]) == 4
    assert len(env.w.instances_of(env.sym)) == 4 and env.w.snapshot() == before
    assert len(first["changed_ids"]) == 4


def test_a_rerun_after_a_new_tag_does_not_duplicate_either(env):
    p, _ = scene_with_floor(env)
    env.place(**place_args(p))
    other = env.place(**place_args(p, tag="HANG2"))
    assert other["ok"] is True and other["changed_ids"] == []
    assert {i["status"] for i in other["rows"]} == {"skipped_existing_foreign"}
    assert len(env.w.instances_of(env.sym)) == 4


def test_a_foreign_hanger_in_place_is_skipped_and_never_touched(env):
    p, _ = scene_with_floor(env)
    foreign = rh.HInstance(env.w.next_id(), env.sym, rh.ft((2.0, 0.0, 3.0)), env.l1)
    env.w.put(foreign)
    result = env.place(**place_args(p))
    assert result["ok"] is True, why(result)
    skipped = [i for i in result["rows"] if i["status"] != "created"]
    assert [(i["status"], i["id"]) for i in skipped] == [("skipped_existing_foreign", foreign.Id.Value)]
    assert len(env.w.instances_of(env.sym)) == 4 and foreign.entity is None and foreign.get_Parameter("comments").AsString() == ""
    assert foreign.Id.Value not in result["changed_ids"]


def test_a_hanger_left_over_from_an_earlier_plan_is_reported_not_deleted(env):
    p, _ = scene_with_floor(env)
    env.place(**place_args(p))
    stale = rh.HInstance(env.w.next_id(), env.sym, rh.ft((1.0, 0.0, 3.0)), env.l1)
    env.w.put(stale)
    from revit_mep_stub import Entity, Schema  # noqa: PLC0415
    ent = Entity(next(iter(Schema.registry.values())))
    ent.values.update({"tag": "HANG1", "key": "hanger:%d:1000" % p.Id.Value, "kind": "hanger"})
    stale.entity = ent
    result = env.place(**place_args(p))
    assert result["ok"] is True and result["changed_ids"] == []
    assert any("STALE_HANGER" in i and str(stale.Id.Value) in i for i in result["info"])
    assert stale in env.w.elements


def test_positions_without_a_support_host_are_skipped_unless_asked_for(env):
    p = env.w.pipe((0, 0, 3), (6, 0, 3))
    env.w.host("floor", (-1, -1, 3.5), (3.1, 1, 3.7))
    result = env.place(**place_args(p))
    assert result["ok"] is True, why(result)
    by = {}
    for i in result["rows"]:
        by.setdefault(i["status"], []).append(i)
    assert len(by["created"]) == 2 and len(by["skipped_no_host"]) == 2
    assert len(env.w.instances_of(env.sym)) == 2
    result = env.place(**place_args(p, place_without_host=True))
    assert result["ok"] is True and len(result["changed_ids"]) == 2 and len(env.w.instances_of(env.sym)) == 4
    bare = [e for e in env.w.instances_of(env.sym) if e.Location.Point.X * rh.M > 3.1]
    assert all(e.named["Rod length"].AsDouble() == 0.0 for e in bare)  # no host: no rod length written


def test_positions_taken_from_the_plan_are_placed_and_the_run_is_rechecked(env):
    p, _ = scene_with_floor(env)
    plan = env.plan(**plan_args(p.Id.Value))
    positions = [{**{k: q[k] for k in ("x_m", "y_m", "z_m", "rod_mm", "support")}, "run_id": p.Id.Value} for q in plan["rows"][0]["positions"]]
    result = env.place(hangers=positions, rod_length_parameter="Rod length")
    assert result["ok"] is True, why(result)
    assert len(result["changed_ids"]) == 4 and result["post_check"]["ok"] is True
    again = env.place(hangers=positions, rod_length_parameter="Rod length")
    assert again["ok"] is True and again["changed_ids"] == []
    assert len(env.w.instances_of(env.sym)) == 4
    # a plan position without a host is not placed from a pasted plan either
    bare = [{**positions[0], "support": "no support host"}]
    skipped = env.place(hangers=bare, tag="HANG9")
    assert skipped["ok"] is True and skipped["changed_ids"] == [] and {i["status"] for i in skipped["rows"]} <= {"skipped_no_host", "skipped_existing_foreign"}


def test_a_position_off_its_run_is_refused_before_anything_changes(env):
    p, _ = scene_with_floor(env)
    before = env.w.snapshot()
    result = env.place(hangers=[{"run_id": p.Id.Value, "x_m": 2.0, "y_m": 0.5, "z_m": 3.0}])
    assert result["ok"] is False and result["kind"] == "position_off_run" and result["element_ids"] == [p.Id.Value]
    assert result["changed_ids"] == [] and env.w.snapshot() == before
    result = env.place(hangers=[{"run_id": p.Id.Value, "x_m": 9.0, "y_m": 0.0, "z_m": 3.0}])
    assert result["kind"] == "position_off_run"


def test_hangers_on_something_that_is_not_a_run_are_refused(env):
    p, floor = scene_with_floor(env)
    result = env.place(hangers=[{"run_id": floor.Id.Value, "x_m": 2.0, "y_m": 0.0, "z_m": 3.5}])
    assert result["ok"] is False and result["kind"] == "category_mismatch" and "not a pipe, duct or cable tray" in result["message"]
    result = env.place(hangers=[{"run_id": 777777, "x_m": 2.0, "y_m": 0.0, "z_m": 3.5}])
    assert result["kind"] == "element_not_found"
    assert env.w.instances_of(env.sym) == []


def test_the_family_category_guard_refuses_a_wall_family(env):
    p, _ = scene_with_floor(env)
    env.w.hanger_family("Wall-ish", category=base.BuiltInCategory.OST_Walls)
    before = env.w.snapshot()
    result = env.place(**place_args(p, family_name="Wall-ish"))
    assert result["ok"] is False and result["kind"] == "hanger_category_mismatch" and "Generic" in result["message"]
    assert result["changed_ids"] == [] and env.w.snapshot() == before and env.w.journal == []


@pytest.mark.parametrize("category", [rh.BuiltInCategory.OST_GenericModel, rh.BuiltInCategory.OST_PipeAccessory,
                                      rh.BuiltInCategory.OST_DuctAccessory, rh.BuiltInCategory.OST_CableTrayFitting,
                                      rh.BuiltInCategory.OST_SpecialityEquipment])
def test_the_hanger_categories_are_accepted(env, category):
    p, _ = scene_with_floor(env)
    env.w.hanger_family("Cat hanger", category=category)
    result = env.place(**place_args(p, family_name="Cat hanger", rod_length_parameter=None))
    assert result["ok"] is True, why(result)


def test_only_level_based_families_are_placed(env):
    p, _ = scene_with_floor(env)
    env.w.hanger_family("Face hanger", placement="WorkPlaneBased")
    result = env.place(**place_args(p, family_name="Face hanger"))
    assert result["ok"] is False and result["kind"] == "placement_unsupported" and "WorkPlaneBased" in result["message"]


def test_a_family_with_mep_connectors_is_a_valve_not_a_hanger(env):
    p, _ = scene_with_floor(env)
    env.w.hanger_family("Valve", category=rh.BuiltInCategory.OST_PipeAccessory, connectors=True)
    before = env.w.snapshot()
    result = env.place(**place_args(p, family_name="Valve"))
    assert result["ok"] is False and result["kind"] == "family_has_connectors"
    assert result["changed_ids"] == [] and env.w.snapshot() == before and env.w.journal == []  # the probe was rolled back


def test_a_missing_or_wrong_rod_parameter_refuses_with_the_parameters_it_has(env):
    p, _ = scene_with_floor(env)
    result = env.place(**place_args(p, rod_length_parameter="Stang"))
    assert result["ok"] is False and result["kind"] == "missing_parameter" and "Rod length" in result["message"]
    env.w.hanger_family("Locked", params={"Rod length": (0.0, "Double", True)})
    result = env.place(**place_args(p, family_name="Locked"))
    assert result["kind"] == "missing_parameter" and "read-only" in result["message"]
    env.w.hanger_family("Text rod", params={"Rod length": ("", "String", False)})
    assert env.place(**place_args(p, family_name="Text rod"))["kind"] == "missing_parameter"
    assert env.w.instances_of(env.sym) == [] and env.w.journal == []


def test_an_unknown_family_or_type_lists_what_is_loaded(env):
    p, _ = scene_with_floor(env)
    result = env.place(**place_args(p, family_name="Nope"))
    assert result["ok"] is False and result["kind"] == "family_not_found" and "Rod hanger" in result["message"]
    result = env.place(**place_args(p, type_name="Huge"))
    assert result["kind"] == "family_not_found" and "Standard" in result["message"]


def test_a_failure_rolls_the_whole_call_back_and_names_the_run(env):
    a, _ = scene_with_floor(env)
    b = env.w.pipe((0, 5, 3), (6, 5, 3))
    env.w.host("floor", (-1, 4, 3.5), (7, 6, 3.7))
    before = env.w.snapshot()
    env.w.fail_on["place_hanger"] = lambda n: n == 7  # call 1 is the probe; run a takes calls 2-5, run b starts at 6
    result = env.place(**place_args(a, ids=[a.Id.Value, b.Id.Value]))
    assert result["ok"] is False and result["kind"] == "rolled_back", why(result)
    assert "Revit refused place_hanger" in result["message"] and result["element_ids"] == [b.Id.Value]
    assert result["changed_ids"] == [] and env.w.snapshot() == before and env.owned() == []


def test_skip_mode_keeps_the_runs_that_worked(env):
    a, _ = scene_with_floor(env)
    b = env.w.pipe((0, 5, 3), (6, 5, 3))
    env.w.host("floor", (-1, 4, 3.5), (7, 6, 3.7))
    env.w.fail_on["place_hanger"] = lambda n: n == 7
    result = env.place(**place_args(a, ids=[a.Id.Value, b.Id.Value], on_error="skip"))
    assert result["ok"] is False and result["kind"] == "partial_failure" and result["element_ids"] == [b.Id.Value]
    assert len(result["changed_ids"]) == 4 and len(env.w.instances_of(env.sym)) == 4
    # the run that failed is picked up by the next call, the finished one is left alone
    env.w.fail_on.clear()
    again = env.place(**place_args(a, ids=[a.Id.Value, b.Id.Value]))
    assert again["ok"] is True and len(again["changed_ids"]) == 4 and len(env.w.instances_of(env.sym)) == 8


def test_a_hanger_that_reads_back_wrong_fails_the_call_and_rolls_back(env, monkeypatch):
    p, _ = scene_with_floor(env)
    original = rh._HCreator.NewFamilyInstance

    def crooked(self, point, symbol, level, structural):
        return original(self, rh.XYZ(point.X + 0.1, point.Y, point.Z), symbol, level, structural)

    monkeypatch.setattr(rh._HCreator, "NewFamilyInstance", crooked)
    before = env.w.snapshot()
    result = env.place(**place_args(p))
    assert result["ok"] is False and result["kind"] == "rolled_back"
    assert "from the requested position" in result["message"] and result["changed_ids"] == []
    assert env.w.snapshot() == before


def test_a_dry_run_does_everything_then_leaves_the_model_unchanged(env):
    p, _ = scene_with_floor(env)
    before = env.w.snapshot()
    result = env.place(**place_args(p, dry_run=True))
    assert result["ok"] is True, why(result)
    assert result["dry_run"] is True and result["committed"] is False and result["changed_ids"] == []
    assert result["would_change"]["element_count"] == 4 and result["would_change"]["by_status"] == {"created": 4}
    assert result["post_check"]["ok"] is True and result["post_check"]["checked"] == 4
    assert result["summary"].startswith("DRY RUN, nothing was changed") and "dry_run false" in result["hint"]
    assert env.w.snapshot() == before and env.w.journal == [] and env.w.instances_of(env.sym) == []
    log = env.w.txn_log
    assert log[-1][0] == "group_rollback" and not any(kind == "group_assimilate" for kind, _ in log)
    real = env.place(**place_args(p))
    assert len(real["changed_ids"]) == result["would_change"]["element_count"]


def test_a_dry_run_that_has_nothing_to_do_is_still_a_dry_run(env):
    p, _ = scene_with_floor(env)
    result = env.place(**place_args(p, spacing_rules=[{**RULE, "source": ""}], dry_run=True))
    assert result["ok"] is True and result["dry_run"] is True and result["committed"] is False and result["changed_ids"] == []
    assert "nothing to place" in result["summary"] and any("RUN_SKIPPED" in i for i in result["info"])


def test_nothing_is_placed_for_a_run_without_a_usable_rule(env):
    p, _ = scene_with_floor(env)
    result = env.place(**place_args(p, spacing_rules=None, material="example material"))
    assert result["ok"] is True and result["changed_ids"] == [] and env.w.instances_of(env.sym) == []
    assert result["spacing_table"]["usable"] == 0


def test_too_many_hangers_is_refused_before_anything_changes(env):
    p, _ = scene_with_floor(env)
    result = env.place(**place_args(p, max_hangers=2))
    assert result["ok"] is False and result["kind"] == "too_many_hangers" and "max_hangers=2" in result["message"]
    assert env.w.instances_of(env.sym) == [] and env.w.journal == []


@pytest.mark.parametrize("over,needle", [
    ({"tag": ""}, "tag is required"),
    ({"tag": "café"}, "tag is required"),
    ({"family_name": ""}, "family_name is required"),
    ({"type_name": "a:b"}, "characters Revit does not allow"),
    ({"dry_run": "false"}, "dry_run must be true or false"),
    ({"on_error": "ignore"}, "on_error must be one of"),
    ({"place_without_host": "no"}, "place_without_host must be true or false"),
    ({"existing_tolerance_mm": 0}, "existing_tolerance_mm must be between"),
    ({"max_hangers": 501}, "max_hangers must be between"),
    ({"align_to_run": 1}, "align_to_run must be true or false"),
    ({"ids": [5], "hangers": [{"run_id": 5, "x_m": 0, "y_m": 0, "z_m": 0}]}, "not both"),
    ({"ids": [], "hangers": None}, "give a scope"),
    ({"ids": [], "hangers": []}, "give a scope"),
    ({"ids": [], "hangers": [{"x_m": 0, "y_m": 0, "z_m": 0}]}, "run_id is required"),
    ({"ids": [], "hangers": [{"run_id": 5, "x_m": "a", "y_m": 0, "z_m": 0}]}, "x_m must be a finite number"),
    ({"ids": [], "hangers": [{"run_id": 5, "x_m": 0, "y_m": 0, "z_m": 0, "colour": "red"}]}, "unknown keys"),
    ({"ids": [], "hangers": [{"run_id": 5, "x_m": 0, "y_m": 0, "z_m": 0, "rod_mm": -4}]}, "rod_length_mm must be greater than 0"),
    ({"ids": [], "hangers": "x"}, "list of 1 to 500"),
])
def test_bad_place_arguments_are_refused_before_anything_is_sent(env, over, needle):
    args: Dict[str, Any] = {"tag": "HANG1", "family_name": "Rod hanger", "type_name": "Standard", "ids": [1], "spacing_rules": [RULE]}
    args.update(over)
    result = env.module.hanger_place(approved_executor=env.bridge, workspace=env.ws, **args)
    assert result["ok"] is False and result["kind"] == "invalid_input" and needle in result["message"], result
    assert env.bridge.modes == []


# --------------------------------------------------------------------------- #
# Wiring: manifest, approval gate, read mode
# --------------------------------------------------------------------------- #
PLAN_OUT = ("SUMMARY\t1 run(s) checked, 1 planned, 0 without a usable spacing rule; 1 hanger(s): 1 with a support host, 0 with no support host\n"
            "META\truns\t1\nMETA\truns_planned\t1\nMETA\thangers\t1\nMETA\thangers_with_host\t1\nMETA\ttruncated\t0\n"
            "ROW\tkind=run\trun=R5\tid=5\tcategory=pipes\tstatus=planned\thangers=1\twith_host=1\tno_host=0\n"
            "ROW\tkind=hanger\trun=R5\trun_id=5\tidx=0\tstation_mm=1000.0\tx_m=1.0\ty_m=0.0\tz_m=3.0\tsupport=host\thost_id=9\trod_mm=484.0\n"
            "COUNT\tfail\t0")
PLACE_OUT = ("SUMMARY\t1 of 1 hanger(s) placed on 1 run(s), 0 skipped\nMETA\toutcome\tok\nMETA\ton_error\tabort\nMETA\tchanged_ids\t77\n"
             "ROW\trow_type=post\tcheck=hanger R5\tok=1\tdetail=ok\n"
             "ROW\trow_type=item\tkind=hanger\tid=77\trun_id=5\tstatus=created\nCOUNT\tfail\t0")
PLACE_ARGS = {"tag": "HANG1", "family_name": "Rod hanger", "type_name": "Standard", "ids": [5], "spacing_rules": [RULE]}


def manifest() -> Dict[str, Any]:
    return json.loads((mep.MODULE_DIR / "module.json").read_text(encoding="utf-8"))


def test_manifest_declares_a_read_tool_and_a_gated_write_tool():
    commands = {c["mcp_tool"]: c for c in manifest()["commands"]}
    plan, place = commands["revit_mep_hanger_plan"], commands["revit_mep_hanger_place"]
    assert plan["id"] == "hanger_plan" and plan["is_mutating"] is False and "requires_plan" not in plan
    assert place["id"] == "hanger_place" and place["is_mutating"] is True and place["requires_plan"] is True and place["destructive"] is False
    assert set(place["input_schema"]["required"]) == {"tag", "family_name", "type_name"}
    assert place["input_schema"]["properties"]["dry_run"]["default"] is False
    assert "dry_run" not in plan["input_schema"]["properties"]
    for cmd in (plan, place):
        assert "not an engineering calculation" in cmd["title"]
    assert "source" in json.dumps(plan["input_schema"]["properties"]["spacing_rules"])
    assert hasattr(mep.RevitMepModule, "hanger_plan") and hasattr(mep.RevitMepModule, "hanger_place")


def test_the_write_tool_needs_an_approved_plan_the_read_tool_does_not(tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch, revit=FakeRevit(write_output=PLACE_OUT, read_output=PLAN_OUT))
    with pytest.raises(BridgeError, match="plan_id"):
        asyncio.run(run_gated_tool(registry, gate, "revit_mep_hanger_place", dict(PLACE_ARGS)))
    assert revit.calls == []
    plan = asyncio.run(run_gated_tool(registry, gate, "revit_mep_hanger_plan", {"ids": [5], "spacing_rules": [RULE]}))
    assert plan["ok"] is True and [c[1]["mode"] for c in revit.calls] == ["read"]
    validate_read_script(revit.calls[0][1]["script"])
    assert plan["rows"][0]["positions"][0]["rod_mm"] == 484.0 and plan["rows"][0]["positions"][0]["host_id"] == 9
    pid = approved(gate, "revit_mep_hanger_place", PLACE_ARGS)
    result = asyncio.run(run_gated_tool(registry, gate, "revit_mep_hanger_place", {**PLACE_ARGS, "plan_id": pid}))
    assert result["ok"] is True, result
    assert [c[1]["mode"] for c in revit.calls] == ["read", "write"]  # no system report: hangers are not MEP members
    assert result["changed_ids"] == [77] and gate.load_plan(pid)["actions"][0]["state"] == "executed"
    with pytest.raises(BridgeError):
        asyncio.run(run_gated_tool(registry, gate, "revit_mep_hanger_place", {**PLACE_ARGS, "plan_id": pid}))


def test_a_pending_plan_does_not_run_the_hanger_write(tmp_path, monkeypatch):
    provider, gate, registry, revit, _ = wire(tmp_path, monkeypatch)
    plan = gate.create_plan([{"tool": "revit_mep_hanger_place", "arguments": dict(PLACE_ARGS)}], [{}])
    with pytest.raises(BridgeError, match="pending"):
        asyncio.run(run_gated_tool(registry, gate, "revit_mep_hanger_place", {**PLACE_ARGS, "plan_id": plan["plan_id"]}))
    assert revit.calls == []


def test_the_scripts_are_read_safe_and_python27_clean():
    plan_script = mep.build_script("hanger_plan.ipy", {"categories": [], "ids": [], "rules": []})
    validate_read_script(plan_script)
    compile(plan_script, "hanger_plan", "exec")
    compile(mep.build_script("hanger_place.ipy", {"tag": "x'\nraise Exception('oops')"}), "hanger_place", "exec")
    validate_read_script((mep.SCRIPT_DIR / "_hanger_plan.ipy").read_text(encoding="utf-8"))
    assert mep.SCRIPTS["hanger_plan.ipy"] == (False, False) and mep.SCRIPTS["hanger_place.ipy"] == (True, False)
