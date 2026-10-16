"""The revit_cleanup audit script executed under CPython against a stub of the Revit API (tests/revit_cleanup_stub.py).

This proves the script's control flow, its rules, the scope handling, the budgets and the line protocol. It does NOT prove
that Revit accepts the same calls: that is UNVERIFIED (see the module docstring of revit_cleanup).
"""
from __future__ import annotations

import ast
import itertools
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import revit_cleanup_stub as st  # noqa: E402
from revit_mcp_server.modules.revit_cleanup import module as cleanup  # noqa: E402
from revit_mcp_server.security.read_mode import validate_read_script  # noqa: E402

CAT = st.CAT


class Bridge:
    """The add-in: validates a read-mode script, runs it against the stub world and records the mode."""

    def __init__(self, doc: st.Document) -> None:
        self.doc, self.modes, self.scripts = doc, [], []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        assert name == "revit_execute_python"
        self.modes.append(args["mode"])
        self.scripts.append(args["script"])
        if args["mode"] == "read":
            validate_read_script(args["script"])
        return {"success": True, "output": st.run_script(args["script"], self.doc), "error": ""}


def build_scene() -> Dict[str, Any]:
    d = st.Document()
    n = itertools.count(100)
    s: Dict[str, Any] = {"doc": d}

    def add(el: Any, name: str) -> Any:
        s[name] = el
        d.add(el)
        return el

    nid = lambda: next(n)  # noqa: E731
    l0 = add(st.Level(nid(), "L0", 0.0), "l0")
    l1 = add(st.Level(nid(), "L1", 10.0), "l1")
    add(st.Level(nid(), "L1 copy", 10.001), "l1b")
    add(st.Level(nid(), "L2", 20.0), "l2")

    # view templates: T1 applied to a view, T2 used by nobody, T3 only the default of a view type
    t1 = add(st.ViewPlan(nid(), "T1", None, template=True), "t1")
    add(st.ViewPlan(nid(), "T2", None, template=True), "t2")
    t3 = add(st.ViewPlan(nid(), "T3", None, template=True), "t3")
    add(st.ViewFamilyType(nid(), "Floor Plan", t3), "vft")

    # views and sheets
    plan0 = add(st.ViewPlan(nid(), "Plan L0", l0), "plan0")
    plan0.ViewTemplateId = t1.Id
    plan1 = add(st.ViewPlan(nid(), "Plan L1", l1), "plan1")
    dep = add(st.ViewPlan(nid(), "Plan L1 - dependent", l1), "dep")
    plan1.dependent_views = [dep]
    sec = add(st.ViewSection(nid(), "Section A", "Section"), "sec")
    callout = add(st.ViewSection(nid(), "Callout of A", "Detail"), "callout")
    sec.dependents = [callout]
    add(st.ViewDrafting(nid(), "Draft 1", "DraftingView"), "draft")
    broken = add(st.ViewSection(nid(), "Section B", "Section"), "broken")
    broken.dependents = None
    sched = add(st.ViewSchedule(nid(), "Door schedule", "Schedule"), "sched")

    s1 = add(st.ViewSheet(nid(), "A101", "Plans"), "s1")
    s1.placed = [plan0, dep]
    add(st.Viewport(nid(), plan0, s1), "vp0")
    add(st.Viewport(nid(), dep, s1), "vpdep")
    add(st.ViewSheet(nid(), "A102", "Empty"), "s2")
    add(st.ViewSheet(nid(), "A103", "Placeholder", placeholder=True), "s3")
    s4 = add(st.ViewSheet(nid(), "A104", "Schedules"), "s4")
    add(st.ScheduleSheetInstance(nid(), sched, s4), "ssi")

    # CAD
    cad_a = st.Element(nid(), "site.dwg")
    cad_a.is_type = True
    cad_b = st.Element(nid(), "old.dwg")
    cad_b.is_type = True
    cad_c = st.Element(nid(), "xref.dwg")
    cad_c.is_type = True
    d.add(cad_a, cad_b, cad_c)
    add(st.ImportInstance(nid(), cad_a, False, plan0), "imp_view")
    add(st.ImportInstance(nid(), cad_b, False), "imp_model")
    add(st.ImportInstance(nid(), cad_c, True), "link_model")

    # rooms
    add(st.Room(nid(), "Hall"), "r_ok")
    add(st.Room(nid(), "Ghost", placed=False, area=0.0), "r_unplaced")
    add(st.Room(nid(), "Flat", placed=True, area=0.0), "r_flat")

    # groups
    gt1 = add(st.GroupType(nid(), "Bath unit"), "gt1")
    gt2 = add(st.GroupType(nid(), "Stair core"), "gt2")
    add(st.GroupType(nid(), "Old group"), "gt3")
    d.add(st.Group(nid(), gt1), st.Group(nid(), gt2), st.Group(nid(), gt2))

    # families: F1 one used and one unused type, F2 nothing used, F3 in-place, F4 profile, F5 tag family
    f1 = add(st.Family(nid(), "Chair", CAT["furniture"]), "f1")
    sa = add(st.FamilySymbol(nid(), "Wood", f1), "sym_a")
    add(st.FamilySymbol(nid(), "Steel", f1), "sym_b")
    f2 = add(st.Family(nid(), "Lamp", CAT["furniture"]), "f2")
    add(st.FamilySymbol(nid(), "Round", f2), "sym_c")
    f3 = add(st.Family(nid(), "Custom bench", CAT["furniture"], in_place=True), "f3")
    add(st.FamilySymbol(nid(), "Bench", f3), "sym_d")
    f4 = add(st.Family(nid(), "Rail profile", CAT["profiles"]), "f4")
    add(st.FamilySymbol(nid(), "Round rail", f4), "sym_p")
    f5 = add(st.Family(nid(), "Door tag", CAT["tags"]), "f5")
    tag_sym = add(st.FamilySymbol(nid(), "Tag 1", f5), "sym_t")
    add(st.Element(nid(), "chair 1", CAT["furniture"], sa), "chair")
    add(st.Element(nid(), "tag 1", None, tag_sym), "tag")

    # walls and doors: one exact duplicate, one collinear overlap, one crossing wall, doors on one spot
    wt = st.Element(nid(), "Generic 200", CAT["walls"])
    wt.is_type = True
    dt1 = st.Element(nid(), "D 900", CAT["doors"])
    dt1.is_type = True
    dt2 = st.Element(nid(), "D 1000", CAT["doors"])
    dt2.is_type = True
    d.add(wt, dt1, dt2)
    add(st.wall(nid(), (0, 0, 0), (10, 0, 0), wt), "w1")
    add(st.wall(nid(), (0, 0, 0), (10, 0, 0), wt), "w1dup")
    add(st.wall(nid(), (1, 0, 0), (10, 0, 0), wt), "w2")
    add(st.wall(nid(), (5, -5, 0), (5, 5, 0), wt), "w3")
    for w in ("w1", "w1dup", "w2", "w3"):
        s[w].LevelId = l0.Id
    add(st.point_element(nid(), (3, 0, 0), dt1, CAT["doors"]), "d1")
    add(st.point_element(nid(), (3, 0, 0), dt1, CAT["doors"]), "d2")
    add(st.point_element(nid(), (3, 0, 0), dt2, CAT["doors"]), "d3")

    # detail lines: 3 in a plan, 2 in a drafting view (ignored), 1 model line (ignored)
    for _ in range(3):
        d.add(st.CurveElement(nid(), "DetailCurve", plan0))
    for _ in range(2):
        d.add(st.CurveElement(nid(), "DetailCurve", s["draft"]))
    d.add(st.CurveElement(nid(), "ModelCurve", plan0))

    # grids: two on top of each other, one with a dimension
    add(st.Grid(nid(), "A", (0, 0, 0), (0, 10, 0)), "g1")
    add(st.Grid(nid(), "A copy", (0, 0, 0), (0, 10, 0)), "g2")
    g3 = add(st.Grid(nid(), "B", (5, 0, 0), (5, 10, 0)), "g3")
    g3.dependents = [st.Dimension(nid())]

    d.warnings = [
        st.Failure("Highlighted walls are overlapping", [s["w1"].Id.Value, s["w1dup"].Id.Value]),
        st.Failure("Highlighted walls are overlapping", [s["w2"].Id.Value]),
        st.Failure("Highlighted walls are overlapping", [s["w3"].Id.Value]),
        st.Failure("Room is not enclosed", [s["r_flat"].Id.Value]),
    ]
    # what is visible in the plan (for a view scope)
    for name in ("w1", "w1dup", "w2", "d1", "d2", "d3", "r_ok", "r_flat", "imp_view", "chair"):
        s[name].visible_in.add(plan0.Id.Value)
    return s


def clean_scene() -> st.Document:
    """A model with nothing to report: one level with a plan on a sheet and a wall on the level."""
    d = st.Document()
    l0 = st.Level(1, "L0", 0.0)
    plan = st.ViewPlan(2, "Plan L0", l0)
    sheet = st.ViewSheet(3, "A101", "Plans")
    sheet.placed = [plan]
    wt = st.Element(5, "Generic 200", CAT["walls"])
    wt.is_type = True
    w = st.wall(6, (0, 0, 0), (10, 0, 0), wt)
    w.LevelId = l0.Id
    d.add(l0, plan, sheet, st.Viewport(4, plan, sheet), wt, w)
    return d


class Env:
    def __init__(self, doc: st.Document) -> None:
        self.doc, self.bridge, self.module = doc, Bridge(doc), cleanup.RevitCleanupModule()

    def audit(self, **args: Any) -> Dict[str, Any]:
        return self.module.cleanup_audit(tool_executor=self.bridge, **args)


@pytest.fixture()
def world(monkeypatch):
    monkeypatch.setattr(cleanup, "_server_in_mock_mode", lambda: False)
    with st.installed(monkeypatch):
        yield


@pytest.fixture()
def scene(world):
    s = build_scene()
    s["env"] = Env(s["doc"])
    return s


def finding(result: Dict[str, Any], code: str) -> Dict[str, Any]:
    hits = [f for f in result["findings"] if f["code"] == code]
    assert len(hits) == 1, (code, [f["code"] for f in result["findings"]])
    return hits[0]


def status(result: Dict[str, Any]) -> Dict[str, str]:
    return {c["check"]: c["status"] for c in result["checks"]}


def ids(*els: Any) -> list:
    return sorted(e.Id.Value for e in els)


# --------------------------------------------------------------------------- #
# Whole model
# --------------------------------------------------------------------------- #
def test_whole_model_findings_counts_ids_and_severities(scene):
    r = scene["env"].audit(max_ids=50)
    assert r["ok"] is True and r["read_only"] is True and r["changed_ids"] == []
    # one view has dependents that cannot be read: that check is partial, so the audit is not "verified" even though it fails
    assert {k: v for k, v in status(r).items() if v != "ran"} == {"views": "partial"} and r["verified"] is False
    assert r["verdict"] == "FAIL" and r["limits"]["partial"] is True
    assert r["summary"].startswith("FAIL: ")
    sev = {f["code"]: f["severity"] for f in r["findings"]}
    assert sev == {
        "SHEETS_EMPTY": "WARN", "VIEW_TEMPLATES_UNUSED": "WARN", "VIEWS_UNPLACED": "WARN",
        "VIEWS_UNPLACED_WITH_PLACED_CHILDREN": "INFO", "VIEWS_UNPLACED_DEPENDENTS_UNREADABLE": "INFO",
        "GROUPS_SINGLE_INSTANCE": "INFO", "GROUP_TYPES_UNPLACED": "WARN", "LEVELS_DUPLICATE": "FAIL", "LEVELS_UNUSED": "WARN",
        "GRIDS_DUPLICATE": "FAIL", "GRIDS_NO_DIMENSION": "INFO", "ROOMS_UNPLACED": "WARN", "ROOMS_NOT_ENCLOSED": "FAIL",
        "CAD_IMPORTS": "WARN", "CAD_LINKS": "INFO", "WARNINGS": "WARN", "DETAIL_LINES_IN_MODEL_VIEWS": "INFO",
        "FAMILIES_UNPLACED": "WARN", "FAMILY_TYPES_UNPLACED": "WARN", "FAMILIES_IN_PLACE": "INFO",
        "DUPLICATE_ELEMENTS": "FAIL", "OVERLAPPING_ELEMENTS": "WARN",
    }
    assert r["counts"] == {"fails": 4, "warns": 11, "info": 7}
    assert len(r["fails"]) == 4 and all(line.split(" ")[0] in sev for line in r["fails"])
    assert [f["severity"] for f in r["findings"]] == sorted((f["severity"] for f in r["findings"]), key=("FAIL", "WARN", "INFO").index)

    s = scene
    assert finding(r, "SHEETS_EMPTY")["element_ids"] == ids(s["s2"])  # the placeholder sheet and the schedule sheet are not empty
    assert finding(r, "VIEW_TEMPLATES_UNUSED")["element_ids"] == ids(s["t2"])  # T3 is a view type default, T1 is applied
    assert finding(r, "VIEWS_UNPLACED")["count"] == 5
    assert finding(r, "VIEWS_UNPLACED")["element_ids"] == ids(s["plan1"], s["sec"], s["callout"], s["draft"], s["broken"])
    assert finding(r, "VIEWS_UNPLACED_WITH_PLACED_CHILDREN")["element_ids"] == ids(s["plan1"])
    assert finding(r, "VIEWS_UNPLACED_DEPENDENTS_UNREADABLE")["element_ids"] == ids(s["broken"])
    assert finding(r, "GROUPS_SINGLE_INSTANCE")["element_ids"] == ids(s["gt1"])
    assert finding(r, "GROUP_TYPES_UNPLACED")["element_ids"] == ids(s["gt3"])
    assert finding(r, "LEVELS_DUPLICATE")["element_ids"] == ids(s["l1"], s["l1b"])
    assert finding(r, "LEVELS_UNUSED")["element_ids"] == ids(s["l1b"], s["l2"])
    assert finding(r, "GRIDS_DUPLICATE")["element_ids"] == ids(s["g1"], s["g2"]) and finding(r, "GRIDS_DUPLICATE")["count"] == 1
    assert finding(r, "GRIDS_NO_DIMENSION")["element_ids"] == ids(s["g1"], s["g2"])
    assert finding(r, "ROOMS_UNPLACED")["element_ids"] == ids(s["r_unplaced"])
    assert finding(r, "ROOMS_NOT_ENCLOSED")["element_ids"] == ids(s["r_flat"])
    assert finding(r, "CAD_IMPORTS")["count"] == 2 and "1 placed in a single view, 1 model-wide" in finding(r, "CAD_IMPORTS")["note"]
    assert finding(r, "CAD_LINKS")["element_ids"] == ids(s["link_model"])
    assert finding(r, "DETAIL_LINES_IN_MODEL_VIEWS")["count"] == 3
    assert finding(r, "FAMILIES_UNPLACED")["element_ids"] == ids(s["f2"])
    assert finding(r, "FAMILY_TYPES_UNPLACED")["element_ids"] == ids(s["sym_b"])
    assert finding(r, "FAMILY_TYPES_UNPLACED")["names"] == ["Chair : Steel"]  # type names come through the ename helper
    assert finding(r, "FAMILIES_IN_PLACE")["element_ids"] == ids(s["f3"])
    assert finding(r, "DUPLICATE_ELEMENTS")["count"] == 2
    assert finding(r, "DUPLICATE_ELEMENTS")["element_ids"] == ids(s["w1"], s["w1dup"], s["d1"], s["d2"])
    assert finding(r, "OVERLAPPING_ELEMENTS")["count"] == 4
    assert finding(r, "OVERLAPPING_ELEMENTS")["element_ids"] == ids(s["w1"], s["w1dup"], s["w2"], s["d1"], s["d2"], s["d3"])


def test_warnings_top_types_and_detail_line_views(scene):
    r = scene["env"].audit()
    assert finding(r, "WARNINGS")["count"] == 4
    assert [(w["description"], w["count"]) for w in r["warnings_by_type"]] == [
        ("Highlighted walls are overlapping", 3), ("Room is not enclosed", 1)]
    assert r["detail_line_views"] == [{"view_id": scene["plan0"].Id.Value, "name": "Plan L0", "view_type": "FloorPlan", "count": 3}]


def test_detail_lines_warn_above_the_threshold(scene):
    r = scene["env"].audit(detail_line_warn=2)
    assert finding(r, "DETAIL_LINES_IN_MODEL_VIEWS")["severity"] == "WARN"


def test_purge_candidates_are_a_separate_documented_field_with_rules(scene):
    s = scene
    r = s["env"].audit(max_purge_ids=100)
    pc = r["purge_candidates"]
    assert "nothing" in pc["note"].lower() and "not a statement that removing it is safe" in pc["note"]
    groups = {k: v["element_ids"] for k, v in pc["groups"].items()}
    assert groups == {
        "empty_sheets": ids(s["s2"]),
        "view_templates": ids(s["t2"]),
        # a view whose dependent is on a sheet (plan1) and a view whose dependents cannot be read (broken) are not offered
        "views": ids(s["sec"], s["callout"], s["draft"]),
        "group_types_unplaced": ids(s["gt3"]),
        "rooms_unplaced": ids(s["r_unplaced"]),
        "rooms_not_enclosed": ids(s["r_flat"]),
        "cad_imports": ids(s["imp_view"], s["imp_model"]),
        "families_unplaced": ids(s["f2"]),
        "family_types_unplaced": ids(s["sym_b"]),
        "duplicate_copies": ids(s["w1dup"], s["d2"]),
    }
    assert pc["total_ids"] == sum(len(v) for v in groups.values())
    everything = {i for v in groups.values() for i in v}
    # never offered: in-place families, levels, grids, single-instance groups, links, the family in a skipped category
    for name in ("f3", "sym_d", "l1b", "l2", "g1", "g2", "gt1", "link_model", "f4", "sym_p", "tag", "sym_t", "plan1", "broken"):
        assert s[name].Id.Value not in everything, name
    assert all(not g["truncated"] for g in pc["groups"].values())
    assert "safe" not in " ".join(r["warns"] + r["fails"] + r["info"]).lower().replace("not a statement that removing it is safe", "")


def test_purge_ids_are_capped_with_a_complete_count(scene):
    r = scene["env"].audit(max_purge_ids=1, max_ids=1)
    cad = r["purge_candidates"]["groups"]["cad_imports"]
    assert cad["count"] == 2 and len(cad["element_ids"]) == 1 and cad["truncated"] is True
    assert finding(r, "CAD_IMPORTS")["count"] == 2 and len(finding(r, "CAD_IMPORTS")["element_ids"]) == 1
    assert r["limits"]["ids_capped"] is True
    assert "(+1 more)" in [f for f in r["warns"] if f.startswith("CAD_IMPORTS")][0]


def test_in_place_families_are_listed_apart_and_never_called_unplaced(scene):
    r = scene["env"].audit()
    assert "Custom bench (0 instances)" in finding(r, "FAMILIES_IN_PLACE")["names"]
    assert scene["f3"].Id.Value not in finding(r, "FAMILIES_UNPLACED")["element_ids"]
    assert not [n for n in finding(r, "FAMILY_TYPES_UNPLACED")["names"] if "bench" in n.lower()]


def test_a_tag_symbol_used_by_a_non_instance_element_counts_as_used(scene):
    r = scene["env"].audit()
    assert scene["f5"].Id.Value not in finding(r, "FAMILIES_UNPLACED")["element_ids"]
    assert scene["f4"].Id.Value not in finding(r, "FAMILIES_UNPLACED")["element_ids"]  # profile types are referenced by other types
    note = {c["check"]: c["note"] for c in r["checks"]}["families"]
    assert "not assessed" in note and "system types" in note


def test_the_audit_is_read_only_and_the_script_passes_read_mode(scene):
    env = scene["env"]
    before = list(env.doc.elements)
    env.audit()
    assert env.bridge.modes == ["read"] and env.doc.elements == before
    validate_read_script(env.bridge.scripts[0])
    for token in ("Transaction", "open(", "import os", "System.IO"):
        assert token not in env.bridge.scripts[0]


def test_the_script_is_python27_safe():
    path = cleanup.SCRIPT_DIR / cleanup.SCRIPT
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    for node in ast.walk(tree):
        assert not isinstance(node, (ast.JoinedStr, ast.AnnAssign, ast.NamedExpr, ast.Starred)), "f-string, annotation, walrus or star"
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.returns is None and all(a.annotation is None for a in node.args.args), "type hint"
        assert not isinstance(node, ast.Nonlocal)


# --------------------------------------------------------------------------- #
# Verdict: never PASS when something was truncated or unreadable
# --------------------------------------------------------------------------- #
def test_a_clean_model_is_a_pass(world):
    r = Env(clean_scene()).audit()
    assert r["verdict"] == "PASS" and r["verified"] is True and r["findings"] == []
    assert set(status(r).values()) == {"ran"} and r["limits"]["truncated"] is False and r["truncated"] is False
    assert r["summary"].startswith("PASS: 0 FAIL, 0 WARN, 0 INFO")


def test_no_time_left_means_not_run_and_incomplete_never_pass(world, monkeypatch):
    st.Stopwatch.tick = 100000  # every clock read is 100 s later
    r = Env(clean_scene()).audit()
    assert set(status(r).values()) == {"not_run"}
    assert r["verdict"] == "INCOMPLETE" and r["verified"] is False and r["limits"]["truncated"] is True
    assert "not finished" in r["summary"]


def test_a_check_that_runs_out_of_its_slice_is_truncated_and_the_verdict_is_incomplete(world):
    st.Stopwatch.tick = 1500
    r = Env(clean_scene()).audit()
    assert "truncated" in set(status(r).values())
    assert r["verdict"] == "INCOMPLETE" and r["limits"]["truncated"] is True and r["verified"] is False


def test_the_element_cap_truncates_and_a_truncated_family_scan_names_nothing_unplaced(scene):
    env = scene["env"]
    args = cleanup.clean_args(None, ["families", "duplicates"], None, None, None, None, None, None, None)
    args["max_elements"] = 5
    out = st.run_script(cleanup.build_script(args), env.doc)
    from revit_mcp_server.check_contract import parse_script_output

    parsed = parse_script_output(out)
    r = cleanup.build_result(parsed, args, 1)
    assert status(r) == {"families": "truncated", "duplicates": "truncated"}
    assert not [f for f in r["findings"] if f["check"] == "families"]  # an incomplete usage count claims nothing
    assert "families_unplaced" not in r["purge_candidates"]["groups"]
    assert r["verdict"] in ("INCOMPLETE", "FAIL") and r["verified"] is False and r["limits"]["truncated"] is True


def test_fail_findings_still_report_fail_when_another_check_is_incomplete(scene):
    st.Stopwatch.tick = 0
    r = scene["env"].audit(checks=["levels_grids"])
    assert r["verdict"] == "FAIL" and status(r) == {"levels_grids": "ran"}


def test_an_unreadable_item_makes_the_check_partial_not_a_pass(world):
    d = clean_scene()
    d.broken_warnings = True
    r = Env(d).audit()
    assert status(r)["warnings"] == "partial" and r["verdict"] == "INCOMPLETE" and r["verified"] is False
    assert "could not be read" in [c for c in r["checks"] if c["check"] == "warnings"][0]["note"]


def test_a_check_that_raises_is_unreadable_and_the_others_still_run(world):
    d = clean_scene()

    class BadLevel(st.Level):
        @property
        def Elevation(self) -> float:  # noqa: N802
            raise RuntimeError("elevation cannot be read")

        @Elevation.setter
        def Elevation(self, value: float) -> None:  # noqa: N802
            pass

    d.add(BadLevel(50, "Bad", 1.0), BadLevel(51, "Bad 2", 2.0))
    r = Env(d).audit()
    assert status(r)["levels_grids"] == "unreadable" and status(r)["sheets"] == "ran"
    assert "RuntimeError" in [c for c in r["checks"] if c["check"] == "levels_grids"][0]["note"]
    assert r["verdict"] == "INCOMPLETE"


# --------------------------------------------------------------------------- #
# Scope
# --------------------------------------------------------------------------- #
def test_categories_scope_runs_element_checks_for_those_categories_only(scene):
    s = scene
    r = s["env"].audit(scope={"mode": "categories", "categories": ["Doors"]})
    st_ = status(r)
    assert st_["duplicates"] == "ran" and st_["warnings"] == "ran" and st_["families"] == "ran"
    for name in ("sheets", "view_templates", "views", "levels_grids", "groups", "cad", "detail_lines", "rooms_areas"):
        assert st_[name] == "skipped", name
    assert {f["code"] for f in r["findings"]} == {"DUPLICATE_ELEMENTS", "OVERLAPPING_ELEMENTS"}
    assert finding(r, "DUPLICATE_ELEMENTS")["element_ids"] == ids(s["d1"], s["d2"])
    assert r["verdict"] == "FAIL" and "outside this scope" in r["summary"]
    assert [c["note"] for c in r["checks"] if c["check"] == "sheets"][0].startswith("document-level check")


def test_categories_scope_filters_warnings_to_the_scope(scene):
    r = scene["env"].audit(scope={"mode": "categories", "categories": ["Rooms"]})
    assert finding(r, "WARNINGS")["count"] == 1
    assert {f["code"] for f in r["findings"]} >= {"ROOMS_UNPLACED", "ROOMS_NOT_ENCLOSED", "WARNINGS"}
    assert status(r)["duplicates"] == "ran"  # the rooms category is compared too and has nothing to report


def test_categories_scope_for_families_counts_usage_inside_the_categories(scene):
    r = scene["env"].audit(scope={"mode": "categories", "categories": ["Furniture"]}, checks=["families"])
    assert finding(r, "FAMILIES_UNPLACED")["element_ids"] == ids(scene["f2"])
    assert finding(r, "FAMILY_TYPES_UNPLACED")["element_ids"] == ids(scene["sym_b"])
    assert status(r) == {"families": "ran"}


def test_view_scope_looks_only_at_what_is_visible_in_the_view(scene):
    s = scene
    r = s["env"].audit(scope={"mode": "view", "view_id": s["plan0"].Id.Value})
    st_ = status(r)
    assert st_["cad"] == "ran" and st_["detail_lines"] == "ran" and st_["duplicates"] == "ran" and st_["rooms_areas"] == "ran"
    assert st_["families"] == "skipped" and st_["sheets"] == "skipped" and st_["levels_grids"] == "skipped"
    assert finding(r, "CAD_IMPORTS")["element_ids"] == ids(s["imp_view"])
    assert "CAD_LINKS" not in {f["code"] for f in r["findings"]}  # the link is model-wide and not visible in this view
    assert finding(r, "DETAIL_LINES_IN_MODEL_VIEWS")["count"] == 3
    assert finding(r, "ROOMS_NOT_ENCLOSED")["element_ids"] == ids(s["r_flat"]) and "ROOMS_UNPLACED" not in {f["code"] for f in r["findings"]}
    assert finding(r, "WARNINGS")["count"] == 3  # the warnings about w1/w1dup, w2 and r_flat; the one about w3 is not visible here
    assert "view" in r["summary"]


def test_a_view_scope_with_a_missing_view_is_an_input_error(scene):
    r = scene["env"].audit(scope={"mode": "view", "view_id": 999999})
    assert r["ok"] is False and r["kind"] == "invalid_input" and "999999" in r["message"]


def test_an_unknown_category_in_the_scope_is_an_input_error(scene):
    r = scene["env"].audit(scope={"mode": "categories", "categories": ["Nonsense"]})
    assert r["ok"] is False and r["kind"] == "invalid_input" and "Nonsense" in r["message"]


def test_checks_can_be_picked(scene):
    r = scene["env"].audit(checks=["sheets", "groups"])
    assert status(r) == {"sheets": "ran", "groups": "ran"}
    assert {f["check"] for f in r["findings"]} == {"sheets", "groups"}
    assert "purge_candidates" in r and set(r["purge_candidates"]["groups"]) == {"empty_sheets", "group_types_unplaced"}


# --------------------------------------------------------------------------- #
# Duplicates and overlaps
# --------------------------------------------------------------------------- #
def test_a_wall_crossing_another_or_touching_it_is_not_an_overlap(world):
    d = st.Document()
    wt = st.Element(1, "Generic", CAT["walls"])
    wt.is_type = True
    d.add(wt, st.wall(2, (0, 0, 0), (10, 0, 0), wt), st.wall(3, (5, -5, 0), (5, 5, 0), wt), st.wall(4, (10, 0, 0), (20, 0, 0), wt))
    r = Env(d).audit(checks=["duplicates"])
    assert r["findings"] == [] and status(r) == {"duplicates": "ran"}


def test_tolerance_decides_what_is_the_same_place(world):
    d = st.Document()
    t = st.Element(1, "D", CAT["doors"])
    t.is_type = True
    d.add(t, st.point_element(2, (0, 0, 0), t, CAT["doors"]), st.point_element(3, (0.01, 0, 0), t, CAT["doors"]))
    assert Env(d).audit(checks=["duplicates"], tolerance_mm=1)["findings"] == []
    assert finding(Env(d).audit(checks=["duplicates"], tolerance_mm=5), "DUPLICATE_ELEMENTS")["count"] == 1


def test_stacked_floors_without_a_location_are_found_by_their_boxes(world):
    d = st.Document()
    t = st.Element(1, "Slab", CAT["generic"])
    t.is_type = True
    a, b, c = (st.Element(i, "", CAT["generic"], t) for i in (2, 3, 4))
    a.bbox = b.bbox = st.box((0, 0, 0), (10, 10, 1))
    c.bbox = st.box((8, 8, 0), (18, 18, 1))
    d.add(t, a, b, c)
    r = Env(d).audit(checks=["duplicates"], scope={"mode": "categories", "categories": ["Generic Models"]})
    assert finding(r, "DUPLICATE_ELEMENTS")["element_ids"] == [2, 3] and "OVERLAPPING_ELEMENTS" not in {f["code"] for f in r["findings"]}


def test_a_cluster_of_three_identical_elements_keeps_the_lowest_id(world):
    d = st.Document()
    t = st.Element(1, "D", CAT["doors"])
    t.is_type = True
    d.add(t, *(st.point_element(i, (0, 0, 0), t, CAT["doors"]) for i in (2, 3, 4)))
    r = Env(d).audit(checks=["duplicates"])
    assert r["purge_candidates"]["groups"]["duplicate_copies"]["element_ids"] == [3, 4]
