"""The revit_sparing scripts executed under CPython against a stub of the Revit API (tests/revit_sparing_stub.py).

This proves the detection arithmetic (sizes, clearance, rounding, angles, links, existing openings, grouping), the
budgets, the ownership/replace rules, rollback (the stub keeps a real undo journal) and the line protocol. It does NOT
prove that Revit accepts the same calls: that is UNVERIFIED.
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
import revit_sparing_stub as ss  # noqa: E402
from revit_mcp_server.modules.revit_sparing import module as sp  # noqa: E402
from revit_mcp_server.security.read_mode import validate_read_script  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402

TAG = "SPA-L00"
FAMILY = {"mode": "family", "family_name": "Sparing", "type_name": "Standaard",
          "size_parameters": {"width": "b", "height": "h", "depth": "d"}, "status_parameter": "Sparing status"}


def build_scene(w: ss.SparingWorld) -> Dict[str, Any]:
    s: Dict[str, Any] = {}
    s["L0"] = w.put(base.Level(11, "00 begane grond", 0.0))
    s["L1"] = w.put(base.Level(12, "01 verdieping", 3000 / ss.MM))
    s["wall"] = w.put(ss.SWall(101, (0, 5000, 0), (10000, 5000, 0), height=3000, width=200))
    s["floor"] = w.put(ss.SFloor(201, (-1000, -1000), (11000, 11000), top_z=3000, thickness=250))
    s["pipe"] = w.put(ss.SMep(301, "pipes", (2000, 0, 1000), (2000, 10000, 1000), diameter=110, system="Riolering", level=s["L0"]))
    s["duct"] = w.put(ss.SMep(302, "ducts", (6000, 0, 2000), (6000, 10000, 2000), width=400, height=200, insulation=25,
                              system="Toevoer", level=s["L0"]))
    s["riser"] = w.put(ss.SMep(303, "pipes", (8000, 8000, 0), (8000, 8000, 4000), diameter=50, system="Riolering", level=s["L0"]))
    s["oblique"] = w.put(ss.SMep(304, "pipes", (3000, 3000, 500), (5000, 7000, 500), diameter=110, system="Water", level=s["L0"]))
    s["beside"] = w.put(ss.SMep(305, "pipes", (0, 1000, 500), (10000, 1000, 500), diameter=110, system="Water", level=s["L0"]))
    return s


class Bridge:
    """The add-in: runs the script it is handed against the stub world and records the mode."""

    def __init__(self, world: ss.SparingWorld) -> None:
        self.world, self.modes, self.scripts = world, [], []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        assert name == "revit_execute_python"
        self.modes.append(args["mode"])
        self.scripts.append(args["script"])
        if args["mode"] == "read":
            validate_read_script(args["script"])
        return {"success": True, "output": self.world.run(args["script"]), "error": ""}


class Env:
    def __init__(self, world, scene, tmp_path):
        self.w, self.s, self.bridge = world, scene, Bridge(world)
        self.module, self.ws = sp.RevitSparingModule(), WorkspaceMonitor([tmp_path])

    def find(self, **args):
        return self.module.find(tool_executor=self.bridge, workspace=self.ws, **args)

    def place(self, **args):
        kwargs = dict(FAMILY)
        kwargs["tag"] = TAG
        kwargs.update(args)
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        return self.module.place(approved_executor=self.bridge, workspace=self.ws, **kwargs)

    def owned(self, tag=TAG):
        return [e for e in self.w.elements if getattr(e, "entity", None) is not None and e.entity.values.get("tag") == tag]


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(sp, "_server_in_mock_mode", lambda: False)
    with ss.installed_sparing(monkeypatch) as world:
        yield Env(world, build_scene(world), tmp_path)


def rows_by_mep(result) -> Dict[int, Dict[str, Any]]:
    return {r["mep_id"]: r for r in result["rows"]}


def why(result):
    return {k: result.get(k) for k in ("kind", "message", "summary", "fails", "info")}


# --------------------------------------------------------------------------- #
# find: detection
# --------------------------------------------------------------------------- #
def test_find_reports_every_crossing_with_sizes_and_suggestions(env):
    r = env.find()
    assert r["ok"] is True and r["verified"] is True, why(r)
    assert list(r)[:5] == ["ok", "tool", "verified", "summary", "totals"] and list(r)[-1] == "rows"
    t = r["totals"]
    assert (t["crossings"], t["need_sparing"], t["already_open"], t["truncated"]) == (4, 4, 0, False)
    assert t["mep_elements"] == 5 and t["hosts"] == 2
    by = rows_by_mep(r)
    assert set(by) == {301, 302, 303, 304}  # the pipe beside the wall crosses nothing
    pipe = by[301]
    assert pipe["crossing_id"] == "301x101" and pipe["host_cat"] == "walls" and pipe["system"] == "Riolering"
    assert (pipe["x_mm"], pipe["y_mm"], pipe["z_mm"]) == pytest.approx((2000, 5000, 1000), abs=0.2)
    assert pipe["mep_size"] == "dia 110" and pipe["host_t_mm"] == pytest.approx(200)
    assert pipe["passage"] == "perpendicular" and pipe["angle_deg"] == pytest.approx(0)
    assert (pipe["shape"], pipe["sparing_w_mm"], pipe["sparing_h_mm"], pipe["sparing_d_mm"]) == ("round", 160, 160, 200)
    assert pipe["level"] == "00 begane grond" and pipe["existing"] == ""
    duct = by[302]  # 400 x 200 + 2 x 25 insulation = 450 x 250, + 2 x 25 clearance, rounded up to 10
    assert duct["mep_size"] == "450x250" and duct["insul_mm"] == pytest.approx(25)
    assert (duct["shape"], duct["sparing_w_mm"], duct["sparing_h_mm"]) == ("rect", 500, 300)
    riser = by[303]
    assert riser["host_cat"] == "floors" and riser["z_mm"] == pytest.approx(2875, abs=0.2)
    assert (riser["sparing_w_mm"], riser["sparing_d_mm"], riser["level"]) == (100, 250, "00 begane grond")
    oblique = by[304]  # 26.6 degrees: wider along the wall, by the slant of the bore through 200 mm
    assert oblique["passage"] == "oblique" and oblique["angle_deg"] == pytest.approx(26.6, abs=0.1)
    expected_w = 2 * (55 * math.sqrt(5) / 2 + 100 * 0.5)
    assert oblique["sparing_w_mm"] == int(math.ceil((expected_w + 50) / 10) * 10) == 280
    assert (oblique["shape"], oblique["sparing_h_mm"]) == ("rect", 160)
    assert env.bridge.modes == ["read"]


def test_find_filters_clearance_rounding_and_paging(env):
    r = env.find(system="RIOL", categories=["pipes"], clearance_mm=50, round_to_mm=25)
    by = rows_by_mep(r)
    assert set(by) == {301, 303}
    assert by[301]["sparing_w_mm"] == 225 and by[303]["sparing_w_mm"] == 150
    r = env.find(level="01 verdieping")
    assert r["totals"]["crossings"] == 0 and r["rows"] == []
    r = env.find(ids=[302, 999])
    assert [x["mep_id"] for x in r["rows"]] == [302]
    assert any("IDS_NOT_MEP" in i and "999" in i for i in r["info"])
    r = env.find(limit=1, offset=1)
    assert len(r["rows"]) == 1 and r["limits"]["truncated"] is True and r["counts"]["rows"] == 4
    r = env.find(host_categories=["floors"])
    assert [x["mep_id"] for x in r["rows"]] == [303]


def test_find_insulated_pipe_and_round_duct_and_tray(env):
    w, s = env.w, env.s
    w.put(ss.SMep(310, "pipes", (9000, 0, 1500), (9000, 10000, 1500), diameter=28, insulation=20, level=s["L0"]))
    w.put(ss.SMep(311, "ducts", (500, 0, 2200), (500, 10000, 2200), diameter=250, level=s["L0"]))
    w.put(ss.SMep(312, "cabletrays", (7000, 0, 2500), (7000, 10000, 2500), width=300, height=60, level=s["L0"]))
    by = rows_by_mep(env.find())
    assert by[310]["mep_size"] == "dia 68" and by[310]["sparing_w_mm"] == 120
    assert by[311]["shape"] == "round" and by[311]["sparing_w_mm"] == 300
    assert (by[312]["mep_cat"], by[312]["sparing_w_mm"], by[312]["sparing_h_mm"]) == ("cabletrays", 350, 110)


def test_existing_opening_is_found_even_though_it_cuts_the_host(env):
    hole = env.w.foreign_opening(901, env.s["wall"], (2000, 5000, 1000), 200, 200)
    r = env.find()
    by = rows_by_mep(r)
    assert by[301]["existing"] == "opening %d" % hole.Id.Value and by[301]["existing_id"] == 901
    assert r["totals"]["already_open"] == 1 and r["totals"]["need_sparing"] == 3
    assert by[302]["existing"] == ""


def test_existing_sparing_family_instance_counts(env):
    sym = env.w.family(800, "Sparing")
    inst = env.w.put(ss.SInstance(950, sym, ss.ft((6000, 5000, 2000))))
    by = rows_by_mep(env.find(sparing_family="Sparing"))
    assert by[302]["existing"] == "sparing %d" % inst.Id.Value
    assert rows_by_mep(env.find())[302]["existing"] == ""  # no family name: only native openings count


def test_two_passages_of_one_run_close_together_merge_into_one_sparing(env):
    # a second, separate pipe of the same system right next to the first one, same direction: one sparing for both
    env.w.put(ss.SMep(320, "pipes", (2000, 5000 - 40, 1000), (2000, 10000, 1000), diameter=110, system="Riolering", level=env.s["L0"]))
    env.s["pipe"].Location.Curve = ss.SLine(ss.ft((2000, 0, 1000)), ss.ft((2000, 5000 - 40, 1000)))
    r = env.find(categories=["pipes"], merge_tolerance_mm=200)
    rows = [x for x in r["rows"] if x["host_id"] == 101 and x["system"] == "Riolering"]
    assert len(rows) == 1 and rows[0]["members"] == 2 and rows[0]["mep_ids"] == "301,320"
    assert rows[0]["shape"] == "rect"
    r = env.find(categories=["pipes"], merge_tolerance_mm=0)
    assert len([x for x in r["rows"] if x["host_id"] == 101 and x["system"] == "Riolering"]) == 2


def test_pipe_inside_a_wall_along_its_plane_is_not_a_sparing(env):
    env.w.put(ss.SMep(330, "pipes", (1000, 5000, 1500), (9000, 5000, 1500), diameter=20, level=env.s["L0"]))
    r = env.find(ids=[330])
    assert r["totals"]["crossings"] == 0 and r["totals"]["parallel_in_host"] == 1
    assert any("PARALLEL_IN_HOST" in i for i in r["info"])


def test_links_hosts_and_mep_with_rotation_and_translation(env):
    link_doc = ss.LinkDoc([ss.SWall(101, (0, 5000, 0), (10000, 5000, 0), height=3000, width=300),
                           ss.SMep(401, "ducts", (1000, -2000, 1500), (1000, 8000, 1500), width=300, height=300)])
    # rotate 90 degrees and move 30 m along x: the linked wall runs along y at x = 25 m
    env.w.put(ss.SLink(700, "ARC.rvt", link_doc, ss.Transform(math.pi / 2, ss.ft((30000, 0, 0)))))
    env.w.put(ss.SMep(340, "pipes", (20000, 2000, 1000), (29000, 2000, 1000), diameter=110, level=env.s["L0"]))
    assert all(x["host_link"] == "" for x in env.find()["rows"])  # links are off by default
    r = env.find(include_links=True)
    by = rows_by_mep(r)
    linked = by[340]
    assert linked["host_link"] == "ARC.rvt" and linked["host_id"] == 101 and linked["crossing_id"] == "340xL700.101"
    assert (linked["x_mm"], linked["y_mm"], linked["host_t_mm"]) == pytest.approx((25000, 2000, 300), abs=0.2)
    assert linked["passage"] == "perpendicular"
    # MEP and host both in the same link: the duct crosses the linked wall at link (1000, 5000) = project (25000, 1000)
    duct = by[401]
    assert (duct["mep_link"], duct["host_link"], duct["crossing_id"]) == ("ARC.rvt", "ARC.rvt", "L700.401xL700.101")
    assert (duct["x_mm"], duct["y_mm"], duct["sparing_w_mm"], duct["sparing_h_mm"]) == pytest.approx((25000, 1000, 350, 350), abs=0.2)


def test_mep_in_a_link_crossing_a_host_of_the_active_model(env):
    link_doc = ss.LinkDoc([ss.SMep(402, "pipes", (0, 0, 0), (0, 10000, 0), diameter=160, system="HWA")])
    env.w.put(ss.SLink(701, "W-installaties.rvt", link_doc, ss.Transform(0.0, ss.ft((4500, 0, 1200)))))
    r = env.find(include_links=True, system="HWA")
    (row,) = r["rows"]
    assert row["mep_link"] == "W-installaties.rvt" and row["crossing_id"] == "L701.402x101"
    assert (row["x_mm"], row["y_mm"], row["z_mm"]) == pytest.approx((4500, 5000, 1200), abs=0.2)
    assert row["sparing_w_mm"] == 210


def test_project_coordinates_are_relative_to_the_project_base_point(env):
    env.w.pbp = ss.ft((1000, 2000, 0))
    row = rows_by_mep(env.find())[301]
    assert (row["x_mm"], row["y_mm"]) == pytest.approx((1000, 3000), abs=0.2)
    assert env.find()["totals"]["coordinates"] == "project"


def test_budgets_truncate_and_flag_the_result(env):
    r = env.find(max_pairs=1)
    assert r["ok"] is True and r["verified"] is False
    assert r["totals"]["truncated"] is True and r["totals"]["truncated_reason"] == "max_pairs"
    assert r["limits"]["partial"] is True and r["totals"]["pairs_tested"] == 1
    assert any(i.startswith("TRUNCATED") for i in r["info"])
    base.Stopwatch.tick = 100000
    r = env.find()
    assert r["totals"]["truncated_reason"] == "time_budget_s" and r["totals"]["pairs_tested"] == 0
    base.Stopwatch.tick = 0
    r = env.find(max_elements=2)
    assert r["totals"]["truncated_reason"] == "max_elements" and r["totals"]["mep_elements"] == 2
    assert r["verified"] is False


def test_unreadable_size_and_curved_mep_are_listed_and_unverified(env):
    bad = env.w.put(ss.SMep(350, "pipes", (100, 0, 100), (100, 10000, 100), diameter=0))
    bad.params.clear()
    r = env.find()
    assert r["verified"] is False and r["totals"]["skipped_elements"] == 1
    assert any("MEP_SIZE_UNKNOWN" in i for i in r["info"])


def test_find_never_changes_the_model(env):
    before = env.w.snapshot()
    env.find(include_links=True)
    assert env.w.snapshot() == before and env.w.txn_log == []


# --------------------------------------------------------------------------- #
# place: family mode
# --------------------------------------------------------------------------- #
def test_place_family_sizes_tags_and_status(env):
    env.w.family(800, "Sparing")
    r = env.place()
    assert r["ok"] is True and r["verified"] is True, why(r)
    assert r["post_check"]["ok"] is True and r["post_check"]["failed"] == 0
    assert len(r["changed_ids"]) == 4 and env.bridge.modes == ["write"]
    made = {e.entity.values["key"]: e for e in env.owned()}
    assert set(made) == {"sparing:301x101", "sparing:302x101", "sparing:303x201", "sparing:304x101"}
    pipe = made["sparing:301x101"]
    assert pipe.how == "face" and pipe.ref.owner is env.s["wall"]
    assert [round(pipe.named[k].value * ss.MM) for k in ("b", "h", "d")] == [160, 160, 200]
    assert pipe.named["Sparing status"].value == "Voorstel"
    assert pipe.entity.values["kind"] == "sparing_family"
    duct = made["sparing:302x101"]
    assert [round(duct.named[k].value * ss.MM) for k in ("b", "h")] == [500, 300]
    # one transaction per sparing in one group, plus the probe that was rolled back
    log = env.w.txn_log
    assert log[0] == ("start", "AEC sparing parameter probe (rolled back)") and log[1][0] == "rollback"
    assert ("group_assimilate", "AEC sparingen %s" % TAG) in log
    assert len([x for x in log if x[0] == "commit" and x[1].startswith("Sparing ")]) == 4
    items = [x for x in r["rows"] if x["kind"] == "sparing"]
    assert {x["action"] for x in items} == {"created"} and r["dry_run"] is False


def test_place_is_idempotent_and_replaces_only_its_own(env):
    env.w.family(800, "Sparing")
    first = env.place()
    assert first["ok"] is True, why(first)
    foreign = env.w.put(ss.SInstance(960, env.w.GetElement(801), ss.ft((500, 9000, 500))))  # far away, someone else's
    other_tag = env.place(tag="ANDER", crossing_ids=["301x101"])
    assert other_tag["ok"] is True and other_tag["totals"]["crossings"] == 4
    # the crossing already has a sparing (of tag SPA-L00): another tag leaves it alone and skips it
    assert [x["reason"] for x in other_tag["rows"] if x["kind"] == "skipped"] == ["existing_foreign"]
    again = env.place()
    assert again["ok"] is True, why(again)
    owned = env.owned()
    assert len(owned) == 4 and sorted(e.entity.values["key"] for e in owned) == sorted(
        "sparing:" + c for c in ("301x101", "302x101", "303x201", "304x101"))
    assert {x["action"] for x in again["rows"] if x["kind"] == "sparing"} == {"replaced"}
    assert set(again["changed_ids"]).isdisjoint(first["changed_ids"])
    assert foreign in env.w.elements


def test_foreign_opening_at_a_crossing_is_skipped_not_duplicated(env):
    env.w.family(800, "Sparing")
    hole = env.w.foreign_opening(901, env.s["wall"], (2000, 5000, 1000), 200, 200)
    r = env.place()
    assert r["ok"] is True, why(r)
    skipped = [x for x in r["rows"] if x["kind"] == "skipped"]
    assert [(x["crossing_id"], x["reason"]) for x in skipped] == [("301x101", "existing_foreign")]
    assert len(env.owned()) == 3 and hole in env.w.elements and hole.entity is None


def test_missing_parameters_are_refused_with_the_list_and_nothing_changes(env):
    env.w.family(800, "Sparing", instance_params={"Breedte": (0.1, "Double", False), "Hoogte": (0.1, "Double", False)},
                 type_params={"b": 0.1})
    before = env.w.snapshot()
    r = env.place()
    assert r["ok"] is False and r["kind"] == "missing_parameter", why(r)
    assert "'b' (width) is a type parameter" in r["message"] and "'h' (height) does not exist" in r["message"]
    assert "Breedte, Hoogte" in r["message"] and "Sparing status" in r["message"]
    assert env.w.snapshot() == before and r["changed_ids"] == []


def test_family_not_found_lists_what_is_loaded(env):
    env.w.family(800, "Sparing")
    r = env.place(family_name="Sparing rond")
    assert r["kind"] == "family_not_found" and "Sparing" in r["message"]
    r = env.place(type_name="Groot")
    assert r["kind"] == "family_not_found" and "Standaard" in r["message"]


def test_abort_rolls_everything_back_with_ids_and_revit_message(env):
    env.w.family(800, "Sparing")
    env.w.fail_on["place_family"] = lambda n: n == 3  # call 1 is the probe
    before = env.w.snapshot()
    r = env.place()
    assert r["ok"] is False and r["kind"] == "rolled_back", why(r)
    assert "Revit refused place_family" in r["message"] and r["changed_ids"] == []
    assert 302 in r["element_ids"] and 101 in r["element_ids"]
    assert env.w.snapshot() == before and env.owned() == []
    assert ("group_rollback", "AEC sparingen %s" % TAG) in env.w.txn_log


def test_skip_keeps_what_worked(env):
    env.w.family(800, "Sparing")
    env.w.fail_on["place_family"] = lambda n: n == 3
    r = env.place(on_error="skip")
    assert r["ok"] is False and r["kind"] == "partial_failure"
    assert len(r["changed_ids"]) == 3 and len(env.owned()) == 3


def test_warnings_are_dismissed_and_listed_errors_roll_back(env):
    env.w.family(800, "Sparing")
    env.w.commit_failures["Sparing 301x101"] = [base.Failure("Instances overlap", "Warning", [])]
    r = env.place()
    assert r["ok"] is True and r["warnings_dismissed"] == 1
    assert any("Instances overlap" in i for i in r["info"])
    env.w.commit_failures["Sparing 302x101"] = [base.Failure("Can't cut instance out of wall", "Error", [])]
    r = env.place()
    assert r["ok"] is False and "Can't cut instance out of wall" in r["message"]
    assert len(env.owned()) == 4  # the earlier build is intact: the replacement was rolled back


def test_dry_run_reports_then_rolls_everything_back(env):
    env.w.family(800, "Sparing")
    before = env.w.snapshot()
    r = env.place(dry_run=True)
    assert r["ok"] is True and r["dry_run"] is True and r["outcome"] == "dry_run", why(r)
    assert r["summary"].startswith("DRY RUN") and r["changed_ids"] == [] and r["verified"] is False
    assert r["post_check"]["ok"] is True and len([x for x in r["rows"] if x["kind"] == "sparing"]) == 4
    assert env.w.snapshot() == before and env.owned() == []


def test_crossing_ids_subset_unknown_ids_and_max_sparings(env):
    env.w.family(800, "Sparing")
    r = env.place(crossing_ids=["303x201"])
    assert r["ok"] is True and [e.entity.values["key"] for e in env.owned()] == ["sparing:303x201"]
    r = env.place(crossing_ids=["999x101"])
    assert r["kind"] == "crossing_not_found" and "999x101" in r["message"]
    r = env.place(max_sparings=2)
    assert r["kind"] == "too_many_sparings"


def test_unhosted_family_is_turned_to_face_the_wall(env):
    env.w.family(800, "Sparing", placement="OneLevelBased")
    r = env.place(crossing_ids=["304x101", "303x201"])
    assert r["ok"] is True, why(r)
    made = {e.entity.values["key"]: e for e in env.owned()}
    facing = made["sparing:304x101"].FacingOrientation
    assert abs(facing.Y) == pytest.approx(1.0) and made["sparing:304x101"].how == "unhosted"
    assert made["sparing:303x201"].FacingOrientation.Y == pytest.approx(1.0)  # floors: not turned


def test_hosted_family_cannot_go_into_a_linked_host(env):
    link_doc = ss.LinkDoc([ss.SWall(101, (0, 5000, 0), (10000, 5000, 0))])
    env.w.put(ss.SLink(700, "ARC.rvt", link_doc, ss.Transform(0.0, ss.ft((0, 20000, 0)))))
    env.w.put(ss.SMep(340, "pipes", (2000, 21000, 1000), (2000, 29000, 1000), diameter=110, level=env.s["L0"]))
    env.w.family(800, "Sparing", placement="OneLevelBasedHosted")
    r = env.place(include_links=True, crossing_ids=["340xL700.101"])
    assert r["ok"] is False and r["kind"] == "placement_failed" and "linked model" in r["message"]
    env.w.family(810, "Sparing vlak")
    r = env.place(include_links=True, crossing_ids=["340xL700.101"], family_name="Sparing vlak")
    assert r["ok"] is True, why(r)
    (inst,) = env.owned()
    assert inst.ref.link is not None and inst.ref.link.Name == "ARC.rvt"


# --------------------------------------------------------------------------- #
# place: native openings
# --------------------------------------------------------------------------- #
def test_place_native_openings_cut_and_rerun_replaces_them(env):
    r = env.place(mode="opening", family_name=None, type_name=None, size_parameters=None, status_parameter=None)
    assert r["ok"] is True, why(r)
    openings = env.owned()
    assert len(openings) == 4 and all(isinstance(e, ss.SOpening) for e in openings)
    assert {e.entity.values["kind"] for e in openings} == {"sparing_opening"}
    assert len(env.s["wall"].solid.holes) == 3 and len(env.s["floor"].solid.holes) == 1
    # the openings cut the host, so a new find sees them as existing ones
    assert rows_by_mep(env.find())[301]["existing"].startswith("opening ")
    again = env.place(mode="opening", family_name=None, type_name=None, size_parameters=None, status_parameter=None)
    assert again["ok"] is True, why(again)
    assert {x["action"] for x in again["rows"] if x["kind"] == "sparing"} == {"replaced"}
    assert len(env.owned()) == 4 and len(env.s["wall"].solid.holes) == 3


def test_opening_status_parameter_and_link_host_skip(env):
    env.w.opening_params = {"Sparing status": ("", "String", False)}
    link_doc = ss.LinkDoc([ss.SWall(101, (0, 5000, 0), (10000, 5000, 0))])
    env.w.put(ss.SLink(700, "ARC.rvt", link_doc, ss.Transform(0.0, ss.ft((0, 20000, 0)))))
    env.w.put(ss.SMep(340, "pipes", (2000, 21000, 1000), (2000, 29000, 1000), diameter=110, level=env.s["L0"]))
    r = env.place(mode="opening", family_name=None, type_name=None, size_parameters=None, include_links=True,
                  status_value="Akkoord")
    assert r["ok"] is True, why(r)
    assert [x["reason"] for x in r["rows"] if x["kind"] == "skipped"] == ["host_in_link"]
    assert {e.named["Sparing status"].value for e in env.owned()} == {"Akkoord"}


def test_opening_without_the_status_parameter_is_refused(env):
    r = env.place(mode="opening", family_name=None, type_name=None, size_parameters=None)
    assert r["kind"] == "missing_parameter" and "a native opening" in r["message"]
    assert env.owned() == []


def test_stale_sparingen_are_listed_not_deleted(env):
    env.w.family(800, "Sparing")
    assert env.place()["ok"] is True
    env.s["oblique"].Location.Curve = ss.SLine(ss.ft((3000, 3000, 500)), ss.ft((3000, 4000, 500)))  # rerouted
    r = env.place()
    assert any(i.startswith("STALE_SPARING") for i in r["info"])
    assert len(env.owned()) == 4


def test_scripts_built_for_the_stub_are_the_shipped_ones(env):
    env.find()
    script = env.bridge.scripts[0]
    for part in (sp.REVIT_PRELUDE, sp.SCRIPT_DIR / "_sparing_detect.ipy", sp.SCRIPT_DIR / "find.ipy"):
        assert part.read_text(encoding="utf-8") in script
    assert isinstance(rs.WORLD["w"], ss.SparingWorld)
