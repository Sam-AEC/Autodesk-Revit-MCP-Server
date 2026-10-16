"""revit_place_views: the embedded script run under CPython against tests/revit_docs_stub.py.

This proves the control flow: refusals, one transaction per viewport, read-back, rollback, dry run and the line protocol.
It does NOT prove that Revit accepts the same calls: that is UNVERIFIED.
"""
from __future__ import annotations

import pytest

from docs_batch_helpers import make_env, MM, failed, plan, ref, txn_names
import revit_docs_stub as ds


@pytest.fixture()
def env(monkeypatch, tmp_path):
    yield from make_env(monkeypatch, tmp_path)



# --------------------------------------------------------------------------- #
# revit_place_views
# --------------------------------------------------------------------------- #
def test_place_views_in_a_grid_inside_the_title_block_and_report_viewport_ids(env):
    names = ["L0 Plan", "L1 Plan", "L2 Plan", "L3 Plan"]
    result = env.write("place_views", sheet="A101", views=[{"view_name": n} for n in names])
    assert result["ok"] is True and result["verified"] is True, result
    vps = env.s.viewports("A101")
    assert len(vps) == 4
    assert result["changed_ids"] == sorted(v.Id.Value for v in vps) or set(result["changed_ids"]) == {v.Id.Value for v in vps}
    rows = {r["name"]: r for r in result["rows"] if r["kind"] == "viewport"}
    assert set(rows) == set(names) and all(r["id"] in result["changed_ids"] for r in rows.values())
    margin = 15 / MM
    for vp in vps:
        o = vp.GetBoxOutline()
        assert o.MinimumPoint.X >= margin - 1e-6 and o.MaximumPoint.X <= 2.76 - margin + 1e-6
        assert o.MinimumPoint.Y >= margin - 1e-6 and o.MaximumPoint.Y <= 1.95 - margin + 1e-6
    # 2 x 2 grid, reading order: the first view is top left
    first, last = rows["L0 Plan"], rows["L3 Plan"]
    assert first["x_mm"] < last["x_mm"] and first["y_mm"] > last["y_mm"]
    assert result["post_check"]["ok"] is True and result["committed"] is True
    assert txn_names(env) == ["Place view '%s' on sheet A101" % n for n in names]
    assert str(vps[0].Id.Value) in result["summary"]


def test_place_views_row_and_column_layouts(env):
    views = [{"view_name": "L0 Plan"}, {"view_name": "L1 Plan"}]
    env.write("place_views", sheet="A101", views=views, layout="row")
    a, b = env.s.viewports("A101")
    assert a.GetBoxCenter().Y == pytest.approx(b.GetBoxCenter().Y) and a.GetBoxCenter().X < b.GetBoxCenter().X
    env.write("place_views", sheet="A102", views=[{"view_name": "L2 Plan"}, {"view_name": "L3 Plan"}], layout="column")
    c, d = env.s.viewports("A102")
    assert c.GetBoxCenter().X == pytest.approx(d.GetBoxCenter().X) and c.GetBoxCenter().Y > d.GetBoxCenter().Y


def test_place_views_top_left_alignment_puts_the_box_corner_at_the_cell_corner(env):
    a, b = plan(env, "L0 Plan"), plan(env, "L1 Plan")
    a.vp_size, b.vp_size = (0.6, 0.4), (0.9, 0.7)
    result = env.write("place_views", sheet="A101", views=[ref(a), ref(b)], layout="row", align="top_left", margin_mm=10, gutter_mm=20)
    assert result["ok"] is True, result
    area = (10 / MM, 10 / MM, 2.76 - 10 / MM, 1.95 - 10 / MM)
    cell_w = (area[2] - area[0] - 20 / MM) / 2
    for vp, left in zip(env.s.viewports("A101"), (area[0], area[0] + cell_w + 20 / MM)):
        o = vp.GetBoxOutline()
        assert o.MinimumPoint.X == pytest.approx(left) and o.MaximumPoint.Y == pytest.approx(area[3])


def test_place_views_explicit_positions_skip_the_layout_and_work_without_a_title_block(env):
    result = env.write("place_views", sheet="A104", views=[{"view_name": "L0 Plan", "x_mm": 100, "y_mm": 200}])
    assert result["ok"] is True, result
    vp = env.s.viewports("A104")[0]
    assert vp.GetBoxCenter().X * MM == pytest.approx(100) and vp.GetBoxCenter().Y * MM == pytest.approx(200)


def test_place_views_without_title_block_or_area_is_refused_and_changes_nothing(env):
    before = env.s.snapshot()
    failed(env.write("place_views", sheet="A104", views=[{"view_name": "L0 Plan"}]), "no_layout_area")
    assert env.s.snapshot() == before and env.bridge.modes == ["write"]
    ok = env.write("place_views", sheet="A104", views=[{"view_name": "L0 Plan"}], area_mm=[0, 0, 800, 500])
    assert ok["ok"] is True, ok


def test_a_view_already_on_a_sheet_is_refused_with_sheet_and_viewport_id(env):
    placed = env.s.place(plan(env, "L1 Plan"), "A102")
    before = env.s.snapshot()
    result = env.write("place_views", sheet="A101", views=[{"view_name": "L0 Plan"}, ref(plan(env, "L1 Plan"))])
    failed(result, "view_already_placed")
    assert "A102" in result["message"] and str(placed.Id.Value) in result["message"]
    assert plan(env, "L1 Plan").Id.Value in result["element_ids"] and placed.Id.Value in result["element_ids"]
    assert env.s.snapshot() == before and result["changed_ids"] == []
    # the same sheet counts too: a second call cannot double-place
    env.write("place_views", sheet="A101", views=[{"view_name": "L0 Plan"}])
    again = env.write("place_views", sheet="A101", views=[{"view_name": "L0 Plan"}])
    failed(again, "view_already_placed")
    assert len(env.s.viewports("A101")) == 1


def test_legends_may_go_on_several_sheets(env):
    assert env.write("place_views", sheet="A101", views=[ref(env.s.legend)])["ok"] is True
    assert env.write("place_views", sheet="A102", views=[ref(env.s.legend)])["ok"] is True
    assert len(env.s.viewports()) == 2


@pytest.mark.parametrize("args,kind", [
    ({"sheet": "Z999", "views": [{"view_name": "L0 Plan"}]}, "sheet_not_found"),
    ({"sheet": "A101", "views": [{"view_name": "No such view"}]}, "view_not_found"),
    ({"sheet": "A101", "views": [{"view_id": 987654}]}, "view_not_found"),
    ({"sheet": "A101", "views": [{"view_name": "L0 Plan"}, {"view_name": "L0 Plan"}]}, "duplicate_view"),
    ({"sheet": "A101", "views": [{"view_name": "Door schedule"}]}, "view_not_found"),
    ({"sheet": "A101", "views": [{"view_name": "Plan Template"}]}, "view_not_found"),
])
def test_place_views_refusals_change_nothing(env, args, kind):
    before = env.s.snapshot()
    failed(env.write("place_views", **args), kind)
    assert env.s.snapshot() == before


def test_a_sheet_placed_as_a_view_is_refused(env):
    failed(env.write("place_views", sheet="A101", views=[ref(env.s.sheets["A102"])]), "view_not_found")


def test_place_views_dry_run_rolls_everything_back_and_reports_would_change(env):
    before = env.s.snapshot()
    result = env.write("place_views", sheet="A101", views=[{"view_name": "L0 Plan"}, {"view_name": "L1 Plan"}], dry_run=True)
    assert result["ok"] is True and result["dry_run"] is True and result["committed"] is False and result["changed_ids"] == []
    assert result["would_change"]["element_count"] == 2 and result["would_change"]["items"] == 2
    assert env.s.snapshot() == before and not env.s.viewports()
    assert env.w.txn_log[-1][0] == "group_rollback"


def test_a_failed_viewport_rolls_the_whole_call_back_by_default(env):
    env.w.fail_on["viewport"] = lambda n: n == 2
    before = env.s.snapshot()
    result = env.write("place_views", sheet="A101", views=[{"view_name": "L0 Plan"}, {"view_name": "L1 Plan"}, {"view_name": "L2 Plan"}])
    failed(result, "rolled_back")
    assert "L1 Plan" in result["message"] and plan(env, "L1 Plan").Id.Value in result["element_ids"]
    assert "Revit refused viewport" in result["message"]
    assert result["changed_ids"] == [] and env.s.snapshot() == before


def test_skip_keeps_the_viewports_that_worked_and_says_partial(env):
    env.w.fail_on["viewport"] = lambda n: n == 2
    result = env.write("place_views", sheet="A101", views=[{"view_name": "L0 Plan"}, {"view_name": "L1 Plan"}, {"view_name": "L2 Plan"}], on_error="skip")
    failed(result, "partial_failure")
    assert len(env.s.viewports("A101")) == 2 and len(result["changed_ids"]) == 2
    assert result["post_check"]["ok"] is True


def test_overlap_and_oversize_are_reported_not_hidden(env):
    env.s.place(env.s.legend, "A101", x=1.0, y=1.0)
    big = plan(env, "L0 Plan")
    big.vp_size = (3.0, 0.5)
    result = env.write("place_views", sheet="A101", views=[ref(big)], area_mm=[0, 0, 800, 500])
    assert result["ok"] is True
    codes = " ".join(result["info"])
    assert "VIEWPORT_OVERLAP" in codes and "VIEWPORT_OVERSIZE" in codes


def test_revit_refusing_to_add_the_view_is_a_step_failure_with_the_view_id(env, monkeypatch):
    monkeypatch.setattr(ds.Viewport, "CanAddViewToSheet", staticmethod(lambda d, s, v: False))
    result = env.write("place_views", sheet="A101", views=[{"view_name": "L0 Plan"}])
    failed(result, "rolled_back")
    assert "cannot be added" in result["message"] and plan(env, "L0 Plan").Id.Value in result["element_ids"]


def test_place_views_post_check_catches_a_viewport_that_ends_up_elsewhere(env, monkeypatch):
    original = ds.Viewport.Create

    def drifting(document, sheet_id, view_id, centre):
        vp = original(document, sheet_id, view_id, centre)
        vp._center = (vp._center[0] + 0.5, vp._center[1])
        return vp

    monkeypatch.setattr(ds.Viewport, "Create", staticmethod(drifting))
    result = env.write("place_views", sheet="A101", views=[{"view_name": "L0 Plan"}])
    failed(result, "rolled_back")
    assert "viewport_position" in result["message"] and not env.s.viewports()
