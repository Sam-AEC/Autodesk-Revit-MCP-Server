"""revit_sparing spec tools: export the placed sparingen of a host model as a spec for its linked discipline models, and place
them in the active document (the discipline model) from that spec.

The scripts run against the Revit API stub (tests/revit_sparing_stub.py). Two stub worlds are used one after the other: the
host model (the fixture) to export, then the discipline model, to place into. That mirrors how the bridge works: the
document that is active when the tool runs is the only one it can write to. UNVERIFIED in a live Revit.
"""
from __future__ import annotations

import contextlib
import copy
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterator

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import revit_api_stub as base  # noqa: E402
import revit_sparing_stub as ss  # noqa: E402
from revit_mcp_server.modules.revit_sparing import module as sp  # noqa: E402
from revit_mcp_server.security.workspace import WorkspaceMonitor  # noqa: E402
from test_revit_sparing_scripts import Bridge, Env, build_scene, why  # noqa: E402

STATUS = "Sparing status"
SIZES = {"width": "b", "height": "h", "depth": "d"}
LINK_ID = 700
LINK_T = ss.Transform(math.pi / 2, ss.ft((30000, 0, 0)))  # rotated 90 degrees, 30 m along x


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(sp, "_server_in_mock_mode", lambda: False)
    with ss.installed_sparing(monkeypatch) as world:
        yield Env(world, build_scene(world), tmp_path)


def host_with_link_sparingen(env, **place_args):
    """The host model: its own walls and floors, a linked architectural model with one wall, and sparingen placed everywhere."""
    link_doc = ss.LinkDoc([ss.SWall(101, (0, 5000, 0), (10000, 5000, 0), height=3000, width=300)])
    env.w.put(ss.SLink(LINK_ID, "ARC.rvt", link_doc, LINK_T))
    env.w.put(ss.SMep(340, "pipes", (20000, 2000, 1000), (29000, 2000, 1000), diameter=110, level=env.s["L0"]))
    env.w.family(800, "Sparing")
    r = env.place(include_links=True, **place_args)
    assert r["ok"] is True, why(r)
    return r


def export(env, **args):
    args.setdefault("size_parameters", SIZES)
    return env.module.export_spec(tool_executor=env.bridge, workspace=env.ws, **args)


def link_item(spec, key="340xL700.101"):
    (link,) = spec["links"]
    (item,) = [i for i in link["items"] if i["key"] == key]
    return item


class Discipline:
    """The discipline model as the active document: its own stub world, bridge and module."""

    def __init__(self, world, tmp_path):
        self.w, self.bridge, self.ws = world, Bridge(world), WorkspaceMonitor([tmp_path])
        self.module = sp.RevitSparingModule()

    def place(self, spec, **args):
        kwargs = {"tag": "ARC-L00", "status_parameter": STATUS}
        kwargs.update(args)
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        return self.module.place_spec(spec=spec, approved_executor=self.bridge, workspace=self.ws, **kwargs)

    def owned(self, tag="ARC-L00"):
        return [e for e in self.w.elements if getattr(e, "entity", None) is not None and e.entity.values.get("tag") == tag]


@contextlib.contextmanager
def discipline_model(monkeypatch, tmp_path, family=True, placement="WorkPlaneBased") -> Iterator[Discipline]:
    """A second stub world: the linked model as the active document (wall 101 where the host model's link has it)."""
    with ss.installed_sparing(monkeypatch) as world:
        world.Title = "Linked_samo3"  # a workshared local copy: central title plus the user name
        world.CreationGUID = "arc-central-guid"
        world.put(base.Level(11, "00 begane grond", 0.0))
        world.put(ss.SWall(101, (0, 5000, 0), (10000, 5000, 0), height=3000, width=300))
        if family:
            world.family(800, "Sparing", placement=placement)
        yield Discipline(world, tmp_path)


@pytest.fixture()
def spec(env):
    host_with_link_sparingen(env)
    r = export(env)
    assert r["ok"] is True, why(r)
    return r["spec"]


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def test_export_turns_positions_and_directions_into_the_links_own_coordinates(env):
    host_with_link_sparingen(env)
    before = env.w.snapshot()
    r = export(env)
    assert r["ok"] is True and r["verified"] is True, why(r)
    assert list(r)[:5] == ["ok", "tool", "verified", "summary", "totals"]
    assert env.bridge.modes[-1] == "read" and env.w.snapshot() == before
    spec = r["spec"]
    assert spec["spec_version"] == 1 and spec["units"] == "mm" and spec["size_parameters"] == SIZES
    assert spec["source"]["document"] == "Villa.rvt" and spec["status_labels"]["approved"] == "Akkoord"
    (link,) = spec["links"]
    assert link["link_instance_id"] == LINK_ID and link["link_name"] == "ARC.rvt" and link["document_title"] == "Linked.rvt"
    assert link["transform"]["origin_mm"] == pytest.approx([30000, 0, 0], abs=0.2)
    assert link["transform"]["rotation_deg_z"] == pytest.approx(90.0, abs=1e-3) and link["transform"]["mirrored"] is False
    item = link_item(spec)
    # the pipe crosses the wall at (25000, 2000) in the host; the link is rotated 90 degrees about z and moved 30 m along x.
    # A face-based sparing sits on a face of the 300 mm wall, so 150 mm off the wall's centre line.
    hx, hy, hz = item["host_model_location_mm"]
    assert (abs(hx - 25000), hy, hz) == pytest.approx((150, 2000, 1000), abs=0.5)
    lx, ly, lz = item["location_mm"]  # the same point in the link: rotate back by 90 degrees, then undo the 30 m
    assert (lx, abs(ly - 5000), lz) == pytest.approx((2000, 150, 1000), abs=0.5) and ly == pytest.approx(30000 - hx, abs=0.5)
    assert item["normal"] == pytest.approx([0, -1, 0], abs=1e-3) and item["normal_from"] == "host wall"
    assert (item["host_id"], item["host_category"], item["kind"]) == (101, "walls", "family")
    assert (item["family_name"], item["type_name"], item["status"], item["status_label"]) == ("Sparing", "Standaard", "proposed", "Voorstel")
    assert item["size_mm"] == {"width": 160.0, "height": 160.0, "depth": 300.0, "shape": "rect", "from": "parameters"}
    assert item["source_tag"] == "SPA-L00" and item["discipline"] == "piping"
    # the four sparingen in this model's own walls and floor are not part of any link's spec
    assert r["totals"]["exported"] == 1 and r["totals"]["unassigned"] == 4 and r["totals"]["unassigned_by_reason"] == {"host_in_this_model": 4}
    assert {x["reason"] for x in r["rows"]} == {"host_in_this_model"} and any("HOST_IN_THIS_MODEL" in i for i in r["info"])
    assert "ACTIVE document" in r["active_document"]


def test_export_without_size_parameters_uses_the_bounding_box_and_says_so(env):
    host_with_link_sparingen(env)
    (inst,) = [e for e in env.owned() if e.entity.values["key"] == "sparing:340xL700.101"]
    c = ss._t(inst.Location.Point)
    # a box 160 wide along the wall (host y direction after the 90 degree turn), 300 deep, 160 high
    inst.bbox = base.BoundingBox((c[0] - 150 / ss.MM, c[1] - 80 / ss.MM, c[2] - 80 / ss.MM), (c[0] + 150 / ss.MM, c[1] + 80 / ss.MM, c[2] + 80 / ss.MM))
    r = env.module.export_spec(tool_executor=env.bridge, workspace=env.ws, link_name="arc")
    size = link_item(r["spec"])["size_mm"]
    assert size["from"] == "bounding box" and (size["width"], size["height"], size["depth"]) == pytest.approx((160, 160, 300), abs=0.5)
    assert any("SIZE_FROM_BOUNDING_BOX" in i for i in r["info"])


def test_export_saves_the_spec_and_filters_links(env, tmp_path):
    host_with_link_sparingen(env)
    r = export(env, save_as="spec-arc")
    assert r["ok"] is True and "spec" not in r and r["spec_file"]["name"] == "spec-arc"
    saved = json.loads(Path(r["spec_file"]["path"]).read_text(encoding="utf-8"))
    assert saved["links"][0]["items"][0]["key"] == "340xL700.101"
    assert "spec" in export(env, save_as="spec-arc", include_spec=True)
    none = export(env, link_name="CON")
    assert none["totals"]["exported"] == 0 and none["spec"]["links"] == [] and none["totals"]["unassigned"] == 5
    assert export(env, link_ids=[LINK_ID])["totals"]["exported"] == 1
    assert export(env, link_ids=[999])["totals"]["exported"] == 0


def test_export_foreign_sparingen_go_to_the_forced_link_without_a_host_id(env):
    host_with_link_sparingen(env)
    sym = env.w.GetElement(801)
    env.w.put(ss.SInstance(950, sym, ss.ft((500, 9000, 500))))
    r = export(env, family_name="Sparing", force_link_id=LINK_ID)
    # family_name selects every instance of the family: the 5 this module placed and the foreign one; all go to the forced link
    assert r["ok"] is True and r["totals"]["exported"] == 6, why(r)
    items = {i["key"]: i for i in r["spec"]["links"][0]["items"]}
    foreign = items["id950"]
    assert foreign["host_id"] is None and foreign["source_tag"] == "" and foreign["normal_from"] == "instance facing"
    # host (500, 9000) -> link: undo the 30 m, rotate back 90 degrees
    assert foreign["location_mm"] == pytest.approx([9000, 29500, 500], abs=0.5)
    r = export(env, family_name="Sparing", force_link_id=999)
    assert r["kind"] == "link_not_found"
    r = export(env, family_name="Sparing")
    assert {u["reason"] for u in r["rows"]} >= {"host_unknown"}


def test_export_a_missing_status_parameter_shows_as_no_parameter(env):
    env.w.family(800, "Sparing", instance_params={"b": (0.1, "Double", False), "h": (0.1, "Double", False), "d": (0.1, "Double", False)})
    link_doc = ss.LinkDoc([ss.SWall(101, (0, 5000, 0), (10000, 5000, 0), height=3000, width=300)])
    env.w.put(ss.SLink(LINK_ID, "ARC.rvt", link_doc, LINK_T))
    env.w.put(ss.SMep(340, "pipes", (20000, 2000, 1000), (29000, 2000, 1000), diameter=110, level=env.s["L0"]))
    assert env.place(include_links=True, status_parameter=None)["ok"] is True
    assert link_item(export(env)["spec"])["status"] == "no_parameter"


@pytest.mark.parametrize("args,needle", [
    ({"save_as": "../x"}, "plain name"),
    ({"link_ids": "7"}, "list"),
    ({"link_ids": [0]}, "link_ids"),
    ({"force_link_id": 0}, "force_link_id"),
    ({"max_items": 501}, "max_items"),
    ({"size_parameters": {"width": "b"}}, "width and height, or diameter"),
    ({"include_spec": "yes"}, "true or false"),
    ({"status_labels": {"built": "x", "approved": "x"}}, "must differ"),
])
def test_export_rejects_bad_arguments(env, args, needle):
    sent = len(env.bridge.scripts)
    r = env.module.export_spec(tool_executor=env.bridge, workspace=env.ws, **args)
    assert r["ok"] is False and r["kind"] == "invalid_input" and needle in r["message"], r
    assert len(env.bridge.scripts) == sent


# --------------------------------------------------------------------------- #
# Place from a spec, in the discipline model as the active document
# --------------------------------------------------------------------------- #
def test_place_spec_places_in_the_active_document_tagged_with_the_status(env, spec, monkeypatch, tmp_path):
    with discipline_model(monkeypatch, tmp_path) as arc:
        r = arc.place(spec)
        assert r["ok"] is True and r["verified"] is True, why(r)
        assert arc.bridge.modes == ["write"] and r["totals"]["placed"] == 1 and r["totals"]["spec_items"] == 1
        (inst,) = arc.owned()
        assert inst.entity.values["key"] == "sparing:340xL700.101" and inst.entity.values["kind"] == "sparing_family"
        wall = arc.w.GetElement(base.ElementId(101))
        assert inst.how == "face" and inst.ref.owner is wall and inst.ref.link is None  # a face of the wall in THIS document
        p = ss._t(inst.Location.Point)
        assert (p[0] * ss.MM, p[2] * ss.MM) == pytest.approx((2000, 1000), abs=1)  # the spec's link coordinates, no transform applied
        assert abs(p[1] * ss.MM - 5000) == pytest.approx(150, abs=1)  # on a face of the 300 mm wall
        assert [round(inst.named[k].value * ss.MM) for k in ("b", "h", "d")] == [160, 160, 300]
        assert inst.named[STATUS].value == "Voorstel"
        assert r["post_check"]["ok"] is True and r["changed_ids"] == [inst.Id.Value] and r["spec_link"]["link_name"] == "ARC.rvt"
        assert "ACTIVE document" in r["active_document"]
        # idempotent: the same tag replaces only what it made
        again = arc.place(spec)
        assert again["ok"] is True, why(again)
        assert {x["action"] for x in again["rows"] if x["kind"] == "sparing"} == {"replaced"}
        assert len(arc.owned()) == 1 and again["changed_ids"] != r["changed_ids"]


def test_place_spec_copies_the_status_or_starts_as_proposed(env, spec, monkeypatch, tmp_path):
    spec = copy.deepcopy(spec)
    spec["links"][0]["items"][0]["status"] = "approved"
    with discipline_model(monkeypatch, tmp_path) as arc:
        assert arc.place(spec)["ok"] is True
        (inst,) = arc.owned()
        assert inst.named[STATUS].value == "Akkoord"
        assert arc.place(spec, copy_status=False)["ok"] is True
        assert arc.owned()[0].named[STATUS].value == "Voorstel"
        assert arc.place(spec, status_labels={"approved": "Goedgekeurd"}, status_parameter=STATUS)["ok"] is True
        assert arc.owned()[0].named[STATUS].value == "Goedgekeurd"
        assert arc.place(spec, status_parameter="")["ok"] is True  # no status parameter: none written
        assert arc.owned()[0].named[STATUS].value == ""


def test_place_spec_refuses_a_document_that_is_not_the_one_in_the_spec(env, spec, monkeypatch, tmp_path):
    with discipline_model(monkeypatch, tmp_path) as arc:
        arc.w.Title = "Constructie"
        before = arc.w.snapshot()
        r = arc.place(spec)
        assert r["ok"] is False and r["kind"] == "wrong_document", why(r)
        assert "Linked.rvt" in r["message"] and "Constructie" in r["message"] and "active document" in r["hint"]
        assert arc.w.snapshot() == before and arc.owned() == [] and r["changed_ids"] == []
        assert arc.place(spec, skip_document_check=True)["ok"] is True
        arc.w.Title = "Constructie"
        arc.w.CreationGUID = spec["links"][0]["document_guid"]  # the creation GUID of a local copy equals the central model's
        assert arc.place(spec)["ok"] is True


def test_place_spec_refuses_missing_hosts_unless_asked_to_skip(env, spec, monkeypatch, tmp_path):
    with discipline_model(monkeypatch, tmp_path) as arc:
        arc.w.elements.remove(arc.w.GetElement(base.ElementId(101)))
        before = arc.w.snapshot()
        r = arc.place(spec)
        assert r["ok"] is False and r["kind"] == "host_not_found" and "340xL700.101 (host_not_found, host id 101)" in r["message"]
        assert r["element_ids"] == [101] and arc.w.snapshot() == before
        r = arc.place(spec, on_error="skip")
        assert r["ok"] is True and [x["reason"] for x in r["rows"] if x["kind"] == "skipped"] == ["host_not_found"]
        assert any("HOST_NOT_FOUND" in i for i in r["info"]) and arc.owned() == []
        # a wall id that is something else here is caught too
        arc.w.put(ss.SFloor(101, (0, 0), (5000, 5000), top_z=0))
        assert arc.place(spec)["kind"] == "host_not_found" and "host_category_mismatch" in arc.place(spec)["message"]


def test_place_spec_leaves_a_foreign_opening_alone_and_reports_it(env, spec, monkeypatch, tmp_path):
    with discipline_model(monkeypatch, tmp_path) as arc:
        hole = arc.w.foreign_opening(901, arc.w.GetElement(base.ElementId(101)), (2000, 5000, 1000), 200, 200)
        r = arc.place(spec)
        assert r["ok"] is True, why(r)
        assert [(x["crossing_id"], x["reason"]) for x in r["rows"] if x["kind"] == "skipped"] == [("340xL700.101", "existing_foreign")]
        assert arc.owned() == [] and hole in arc.w.elements and r["changed_ids"] == []


def test_place_spec_dry_run_rolls_everything_back(env, spec, monkeypatch, tmp_path):
    with discipline_model(monkeypatch, tmp_path) as arc:
        before = arc.w.snapshot()
        r = arc.place(spec, dry_run=True)
        assert r["ok"] is True and r["dry_run"] is True and r["outcome"] == "dry_run" and r["verified"] is False, why(r)
        assert r["summary"].startswith("DRY RUN") and r["changed_ids"] == [] and r["post_check"]["ok"] is True
        assert len(r["would_change_ids"]) == 1 and arc.w.snapshot() == before and arc.owned() == []


def test_place_spec_failure_rolls_back_with_ids(env, spec, monkeypatch, tmp_path):
    with discipline_model(monkeypatch, tmp_path) as arc:
        arc.w.fail_on["place_family"] = lambda n: n == 2  # call 1 is the probe
        before = arc.w.snapshot()
        r = arc.place(spec)
        assert r["ok"] is False and r["kind"] == "rolled_back" and "Revit refused place_family" in r["message"], why(r)
        assert 101 in r["element_ids"] and r["changed_ids"] == [] and arc.w.snapshot() == before


def test_place_spec_missing_family_and_parameters_are_refused(env, spec, monkeypatch, tmp_path):
    with discipline_model(monkeypatch, tmp_path, family=False) as arc:
        r = arc.place(spec)
        assert r["kind"] == "family_not_found" and "Sparing" in r["message"] and arc.owned() == []
    with discipline_model(monkeypatch, tmp_path, family=False) as arc:
        arc.w.family(800, "Sparing", instance_params={"b": (0.1, "Double", False), "h": (0.1, "Double", False)})
        r = arc.place(spec, status_parameter=None)
        assert r["kind"] == "missing_parameter" and "'d' (depth) does not exist" in r["message"]


def test_place_spec_unhosted_family_needs_no_host(env, spec, monkeypatch, tmp_path):
    with discipline_model(monkeypatch, tmp_path, placement="OneLevelBased") as arc:
        arc.w.elements.remove(arc.w.GetElement(base.ElementId(101)))
        r = arc.place(spec)
        assert r["ok"] is True, why(r)
        (inst,) = arc.owned()
        assert inst.how == "unhosted" and abs(inst.FacingOrientation.Y) == pytest.approx(1.0)


def test_place_spec_native_openings(env, spec, monkeypatch, tmp_path):
    spec = copy.deepcopy(spec)
    spec["links"][0]["items"][0]["kind"] = "opening"
    with discipline_model(monkeypatch, tmp_path) as arc:
        arc.w.opening_params = {STATUS: ("", "String", False)}
        r = arc.place(spec)
        assert r["ok"] is True and r["totals"]["mode"] == "opening", why(r)
        (op,) = arc.owned()
        assert isinstance(op, ss.SOpening) and op.entity.values["kind"] == "sparing_opening" and op.named[STATUS].value == "Voorstel"
        assert len(arc.w.GetElement(base.ElementId(101)).solid.holes) == 1
        again = arc.place(spec)
        assert again["ok"] is True and len(arc.owned()) == 1 and len(arc.w.GetElement(base.ElementId(101)).solid.holes) == 1
        # items of the other kind are skipped, not forced into this mode
        r = arc.place(spec, mode="family")
        assert r["totals"]["placed"] == 0 and [x["reason"] for x in r["rows"] if x["kind"] == "skipped"] == ["kind_not_selected"]


def test_place_spec_reads_a_saved_spec_by_name(env, monkeypatch, tmp_path):
    host_with_link_sparingen(env)
    assert export(env, save_as="spec-arc")["ok"] is True
    with discipline_model(monkeypatch, tmp_path) as arc:
        r = arc.module.place_spec(spec_file="spec-arc", tag="ARC-L00", approved_executor=arc.bridge, workspace=arc.ws)
        assert r["ok"] is True and len(arc.owned()) == 1, why(r)
        r = arc.module.place_spec(spec_file="missing", tag="ARC-L00", approved_executor=arc.bridge, workspace=arc.ws)
        assert r["kind"] == "invalid_input" and "not found" in r["message"]


def _one(spec, **changes):
    s = copy.deepcopy(spec)
    s["links"][0]["items"][0].update(changes)
    return s


def test_place_spec_rejects_a_bad_spec_before_anything_is_sent(env, spec, monkeypatch, tmp_path):
    cases = [
        (None, {}, "give exactly one"),
        ({"links": []}, {}, "spec_version"),
        ({"spec_version": 1, "links": []}, {}, "no links"),
        (_one(spec, key="bad key"), {}, "not a crossing id"),
        (_one(spec, location_mm=[1, 2]), {}, "three numbers"),
        (_one(spec, location_mm=[1, 2, float("inf")]), {}, "finite"),
        (_one(spec, normal=[0, 0, 0]), {}, "zero vector"),
        (_one(spec, size_mm={"width": 100}), {}, "width and height"),
        (_one(spec, size_mm={"width": 0, "height": 5}), {}, "size_mm.width"),
        (_one(spec, host_category="doors"), {}, "host_category"),
        (_one(spec, kind="hole"), {}, "kind must be"),
        (_one(spec, family_name="", type_name=""), {}, "family_name and type_name are required"),
        (spec, {"tag": "café"}, "tag is required"),
        (spec, {"mode": "opening", "family_name": "Sparing"}, "belong to mode 'family'"),
        (spec, {"link_instance_id": 5}, "not in the spec"),
        (spec, {"spec_file": "spec-arc"}, "exactly one"),
        (None, {"spec_file": "../x"}, "plain name"),
        (spec, {"max_sparings": 0}, "max_sparings"),
        (spec, {"copy_status": "yes"}, "true or false"),
        (spec, {"size_parameters": {"width": "b"}}, "width and height, or diameter"),
    ]
    with discipline_model(monkeypatch, tmp_path) as arc:
        for data, changes, needle in cases:
            kwargs = {"tag": "ARC-L00", "approved_executor": arc.bridge, "workspace": arc.ws, **changes}
            if data is not None:
                kwargs["spec"] = data
            r = arc.module.place_spec(**kwargs)
            assert r["ok"] is False and r["kind"] == "invalid_input" and needle in r["message"], (needle, r)
        assert arc.bridge.scripts == []
        two = copy.deepcopy(spec)
        two["links"].append({**two["links"][0], "link_instance_id": 701, "link_name": "CON.rvt"})
        r = arc.place(two)
        assert r["kind"] == "invalid_input" and "pass link_instance_id" in r["message"] and "701 = CON.rvt" in r["message"]
        assert arc.place(two, link_instance_id=LINK_ID)["ok"] is True
        dup = copy.deepcopy(spec)
        dup["links"][0]["items"].append(dup["links"][0]["items"][0])
        assert "twice" in arc.place(dup)["message"]


def test_the_spec_round_trips_through_json(env, spec, monkeypatch, tmp_path):
    again: Dict[str, Any] = json.loads(json.dumps(spec))
    assert again == spec
    with discipline_model(monkeypatch, tmp_path) as arc:
        assert arc.place(again)["ok"] is True
