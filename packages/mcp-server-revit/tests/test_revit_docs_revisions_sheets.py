"""Revisions (list, add, clouds, issue) and sheets (index, update) of revit_docs.

The embedded scripts run under CPython against tests/revit_docs_stub.py. This proves the control flow (refusals, one
transaction per element, read-back, rollback, dry run, line protocol). It does NOT prove that Revit accepts the same
calls: that is UNVERIFIED.
"""
from __future__ import annotations

import pytest

import revit_docs_stub as ds
from revit_api_stub import BoundingBox, Element
from docs_batch_helpers import make_env, MM, failed, plan, ref, txn_names


@pytest.fixture()
def env(monkeypatch, tmp_path):
    yield from make_env(monkeypatch, tmp_path)



def revisions(env):
    return [e for e in env.w.elements if isinstance(e, ds.Revision)]


def wall(env, lo, hi):
    """An element with a bounding box (model coordinates, feet) that is visible in every view."""
    e = Element(env.w.next_id(), None)
    e.bbox = BoundingBox(lo, hi)
    env.w.elements.append(e)
    return e


# --------------------------------------------------------------------------- #
# Revisions: list and add
# --------------------------------------------------------------------------- #
def test_list_revisions_with_clouds_sheets_and_issue_state(env):
    env.s.place(plan(env, "L0 Plan"), "A101")
    env.w.elements.append(ds.RevisionCloud(env.w.next_id(), plan(env, "L0 Plan"), env.s.rev2, []))
    env.s.sheets["A102"]._extra_revs.append(env.s.rev1.Id.Value)
    result = env.read("list_revisions")
    assert result["ok"] is True and env.bridge.modes == ["read"]
    rows = {r["number"]: r for r in result["rows"]}
    assert rows["1"]["issued"] is True and rows["1"]["sheets"] == 1 and rows["1"]["clouds"] == 0
    assert rows["2"]["issued"] is False and rows["2"]["clouds"] == 1 and rows["2"]["sheets"] == 1
    assert [r["sequence"] for r in result["rows"]] == [1, 2]
    assert [r["number"] for r in env.read("list_revisions", only_open=True)["rows"]] == ["2"]


def test_add_revision_reads_every_property_back(env):
    result = env.write("add_revision", description="Fire strategy update", date="2026-10-15", issued_by="SM", issued_to="Client", visibility="tag")
    assert result["ok"] is True and result["verified"] is True, result
    rev = revisions(env)[-1]
    assert (rev.Description, rev.RevisionDate, rev.IssuedBy, rev.IssuedTo, rev.Visibility, rev.Issued) == ("Fire strategy update", "2026-10-15", "SM", "Client", "TagVisible", False)
    assert result["changed_ids"] == [rev.Id.Value] and result["rows"][0]["number"] == "3" and result["rows"][0]["sequence"] == 3
    assert txn_names(env) == ["Add revision 'Fire strategy update'"]


def test_add_revision_refuses_a_repeat_and_changes_nothing(env):
    before = env.s.snapshot()
    result = env.write("add_revision", description="Client comments")
    failed(result, "revision_exists")
    assert result["element_ids"] == [env.s.rev2.Id.Value] and env.s.snapshot() == before
    assert env.write("add_revision", description="Client comments", date="2027-01-01")["ok"] is True


def test_add_revision_dry_run_and_failure_leave_the_model_alone(env):
    before = env.s.snapshot()
    dry = env.write("add_revision", description="Trial", dry_run=True)
    assert dry["ok"] is True and dry["dry_run"] is True and dry["changed_ids"] == [] and env.s.snapshot() == before
    env.w.fail_on["revision"] = lambda n: True
    failed(env.write("add_revision", description="Trial"), "rolled_back")
    assert env.s.snapshot() == before


# --------------------------------------------------------------------------- #
# Revision clouds
# --------------------------------------------------------------------------- #
def test_one_cloud_around_elements_in_a_plan_view_lies_in_the_view_plane(env):
    a = wall(env, (1.0, 2.0, 0.0), (4.0, 3.0, 3.0))
    b = wall(env, (6.0, 1.0, 0.0), (9.0, 8.0, 3.0))
    view = plan(env, "L0 Plan")
    env.s.place(view, "A101")
    result = env.write("add_revision_clouds", revision_number="2", view=ref(view), element_ids=[a.Id.Value, b.Id.Value], margin_mm=100)
    assert result["ok"] is True and result["verified"] is True, result
    (cloud,) = env.s.clouds()
    assert result["changed_ids"] == [cloud.Id.Value] and cloud.RevisionId.Value == env.s.rev2.Id.Value and cloud.OwnerViewId.Value == view.Id.Value
    xs = [p.X for c in cloud.curves for p in (c.p0, c.p1)]
    ys = [p.Y for c in cloud.curves for p in (c.p0, c.p1)]
    margin = 100 / MM
    assert (min(xs), max(xs)) == pytest.approx((1.0 - margin, 9.0 + margin)) and (min(ys), max(ys)) == pytest.approx((1.0 - margin, 8.0 + margin))
    assert result["rows"][0]["sheet"] == "A101" and result["post_check"]["ok"] is True
    assert "revision_on_sheet" in [c["check"] for c in result["post_check"]["checks"]]


def test_clouds_in_a_section_view_use_the_view_axes(env):
    e = wall(env, (1.0, 0.0, 2.0), (4.0, 1.0, 5.0))
    result = env.write("add_revision_clouds", revision_id=env.s.rev2.Id.Value, view=ref(env.s.section), element_ids=[e.Id.Value], margin_mm=0)
    assert result["ok"] is True, result
    (cloud,) = env.s.clouds()
    assert {round(p.Y, 6) for c in cloud.curves for p in (c.p0, c.p1)} == {5.0}  # the plane of the section
    assert {round(p.Z, 6) for c in cloud.curves for p in (c.p0, c.p1)} == {2.0, 5.0}
    assert any("VIEW_NOT_ON_SHEET" in i for i in result["info"])


def test_per_element_makes_one_cloud_each_and_bbox_adds_one(env):
    a = wall(env, (1.0, 1.0, 0.0), (2.0, 2.0, 3.0))
    b = wall(env, (5.0, 5.0, 0.0), (6.0, 6.0, 3.0))
    result = env.write("add_revision_clouds", revision_number="2", view=ref(plan(env, "L0 Plan")), element_ids=[a.Id.Value, b.Id.Value],
                       bbox_m={"min": [10, 10, 0], "max": [12, 12, 3]}, per_element=True)
    assert result["ok"] is True and len(env.s.clouds()) == 3 and len(result["changed_ids"]) == 3
    assert [n for n in txn_names(env)] == ["Add revision cloud around element %d in view 'L0 Plan'" % a.Id.Value,
                                           "Add revision cloud around element %d in view 'L0 Plan'" % b.Id.Value,
                                           "Add revision cloud around box in view 'L0 Plan'"]


def test_bbox_only_cloud(env):
    result = env.write("add_revision_clouds", revision_number="2", view=ref(plan(env, "L0 Plan")), bbox_m={"min": [0, 0, 0], "max": [3, 3, 3]}, margin_mm=0)
    assert result["ok"] is True
    xs = [p.X for c in env.s.clouds()[0].curves for p in (c.p0, c.p1)]
    assert (min(xs), max(xs)) == pytest.approx((0.0, 3 / 0.3048))


def test_clouds_refuse_an_issued_revision_a_bad_view_and_unseen_elements(env):
    a = wall(env, (1.0, 1.0, 0.0), (2.0, 2.0, 3.0))
    ghost = Element(env.w.next_id(), None)
    env.w.elements.append(ghost)
    before = env.s.snapshot()
    issued = env.write("add_revision_clouds", revision_number="1", view=ref(plan(env, "L0 Plan")), element_ids=[a.Id.Value])
    failed(issued, "revision_issued")
    assert issued["element_ids"] == [env.s.rev1.Id.Value]
    failed(env.write("add_revision_clouds", revision_number="2", view=ref(env.s.view3d), element_ids=[a.Id.Value]), "view_not_supported")
    failed(env.write("add_revision_clouds", revision_number="2", view=ref(env.s.sheets["A101"]), element_ids=[a.Id.Value]), "view_not_supported")
    unseen = env.write("add_revision_clouds", revision_number="2", view=ref(plan(env, "L0 Plan")), element_ids=[a.Id.Value, ghost.Id.Value, 999999])
    failed(unseen, "element_not_in_view")
    assert set(unseen["element_ids"]) == {ghost.Id.Value, 999999}
    failed(env.write("add_revision_clouds", revision_number="9", view=ref(plan(env, "L0 Plan")), element_ids=[a.Id.Value]), "revision_not_found")
    failed(env.write("add_revision_clouds", revision_id=424242, view=ref(plan(env, "L0 Plan")), element_ids=[a.Id.Value]), "revision_not_found")
    assert env.s.snapshot() == before and not env.s.clouds()


def test_a_thin_cloud_is_refused_and_margin_fixes_it(env):
    line = wall(env, (1.0, 1.0, 0.0), (1.0, 1.0, 0.0))
    failed(env.write("add_revision_clouds", revision_number="2", view=ref(plan(env, "L0 Plan")), element_ids=[line.Id.Value], margin_mm=0), "empty_extent")
    assert env.write("add_revision_clouds", revision_number="2", view=ref(plan(env, "L0 Plan")), element_ids=[line.Id.Value], margin_mm=50)["ok"] is True


def test_cloud_failure_rolls_back_every_cloud_by_default_and_skip_keeps_the_rest(env):
    a = wall(env, (1.0, 1.0, 0.0), (2.0, 2.0, 3.0))
    b = wall(env, (5.0, 5.0, 0.0), (6.0, 6.0, 3.0))
    env.w.fail_on["cloud"] = lambda n: n == 2
    args = dict(revision_number="2", view=ref(plan(env, "L0 Plan")), element_ids=[a.Id.Value, b.Id.Value], per_element=True)
    result = env.write("add_revision_clouds", **args)
    failed(result, "rolled_back")
    assert not env.s.clouds() and plan(env, "L0 Plan").Id.Value in result["element_ids"]
    env.w.calls.clear()
    skip = env.write("add_revision_clouds", on_error="skip", **args)
    failed(skip, "partial_failure")
    assert len(env.s.clouds()) == 1 and len(skip["changed_ids"]) == 1


def test_cloud_dry_run_leaves_no_cloud(env):
    a = wall(env, (1.0, 1.0, 0.0), (2.0, 2.0, 3.0))
    before = env.s.snapshot()
    result = env.write("add_revision_clouds", revision_number="2", view=ref(plan(env, "L0 Plan")), element_ids=[a.Id.Value], dry_run=True)
    assert result["ok"] is True and result["dry_run"] is True and result["would_change"]["element_count"] == 1 and result["changed_ids"] == []
    assert env.s.snapshot() == before and not env.s.clouds()


# --------------------------------------------------------------------------- #
# Issue and assign
# --------------------------------------------------------------------------- #
def test_issue_revision_assigns_sheets_then_issues_and_reads_back(env):
    env.s.place(plan(env, "L0 Plan"), "A101")
    env.w.elements.append(ds.RevisionCloud(env.w.next_id(), plan(env, "L0 Plan"), env.s.rev2, []))
    result = env.write("issue_revision", revision_number="2", sheets=["A101", "A102", "A103"], issue=True, issued_by="SM", issued_to="Planning")
    assert result["ok"] is True and result["verified"] is True, result
    rev = env.s.rev2
    assert rev.Issued is True and (rev.IssuedBy, rev.IssuedTo) == ("SM", "Planning")
    by = {r["sheet"]: r["status"] for r in result["rows"] if r["kind"] == "sheet"}
    assert by == {"A101": "unchanged", "A102": "assigned", "A103": "assigned"}  # A101 already shows it through the cloud
    assert env.s.sheets["A102"]._extra_revs == [rev.Id.Value] and env.s.sheets["A101"]._extra_revs == []
    assert rev.Id.Value in result["changed_ids"] and env.s.sheets["A102"].Id.Value in result["changed_ids"]
    assert txn_names(env) == ["Add revision 2 to sheet A102", "Add revision 2 to sheet A103", "Issue revision 2"]


def test_assign_only_does_not_issue_and_is_repeatable(env):
    first = env.write("issue_revision", revision_id=env.s.rev2.Id.Value, sheets=["A102"])
    assert first["ok"] is True and env.s.rev2.Issued is False
    again = env.write("issue_revision", revision_id=env.s.rev2.Id.Value, sheets=["A102"])
    assert again["ok"] is True and again["changed_ids"] == [] and again["rows"][0]["status"] == "unchanged"
    assert env.s.sheets["A102"]._extra_revs == [env.s.rev2.Id.Value]


def test_issue_only_and_already_issued(env):
    done = env.write("issue_revision", revision_number="2", issue=True)
    assert done["ok"] is True and env.s.rev2.Issued is True and done["rows"][0]["status"] == "issued"
    again = env.write("issue_revision", revision_number="2", issue=True)
    assert again["ok"] is True and again["changed_ids"] == [] and any("ALREADY_ISSUED" in i for i in again["info"])


def test_issue_revision_failure_rolls_back_the_assignments_and_the_issue(env):
    before = env.s.snapshot()
    env.w.fail_on["set_revisions"] = lambda n: n == 2
    result = env.write("issue_revision", revision_number="2", sheets=["A101", "A102"], issue=True)
    failed(result, "rolled_back")
    assert env.s.snapshot() == before and env.s.rev2.Issued is False
    assert env.s.sheets["A102"].Id.Value in result["element_ids"]


def test_issue_revision_refuses_unknown_sheets_and_revisions(env):
    before = env.s.snapshot()
    failed(env.write("issue_revision", revision_number="2", sheets=["A101", "Z1"], issue=True), "sheet_not_found")
    failed(env.write("issue_revision", revision_number="7", issue=True), "revision_not_found")
    assert env.s.snapshot() == before


def test_issue_revision_dry_run(env):
    before = env.s.snapshot()
    result = env.write("issue_revision", revision_number="2", sheets=["A102"], issue=True, dry_run=True)
    assert result["ok"] is True and result["dry_run"] is True and result["would_change"]["element_count"] == 2
    assert env.s.snapshot() == before


# --------------------------------------------------------------------------- #
# Sheet index
# --------------------------------------------------------------------------- #
def test_sheet_index_lists_sheets_views_revisions_and_findings(env):
    env.s.place(plan(env, "L0 Plan"), "A101")
    env.s.place(plan(env, "L1 Plan"), "A101", 2.0, 1.0)
    env.w.elements.append(ds.ScheduleSheetInstance(env.w.next_id(), env.s.sheets["A103"], env.s.schedule))
    env.s.sheets["A101"]._extra_revs.append(env.s.rev1.Id.Value)
    result = env.read("sheet_index")
    assert result["ok"] is True and env.bridge.modes == ["read"]
    rows = {r["number"]: r for r in result["rows"]}
    assert set(rows) == {"A101", "A102", "A103", "A104"}
    a101 = rows["A101"]
    assert a101["views"] == 2 and a101["view_names"] == "L0 Plan | L1 Plan" and a101["revisions"] == "1" and a101["revision"] == "1"
    assert a101["titleblock"] == "A1 metric : A1" and a101["empty"] is False and a101["findings"] == ""
    assert rows["A103"]["schedules"] == 1 and rows["A103"]["empty"] is False
    assert rows["A102"]["empty"] is True and rows["A102"]["findings"] == "empty"
    assert rows["A104"]["findings"] == "empty,no_title_block"
    assert sorted(f.split(":")[0] for f in result["fails"]) == ["EMPTY_SHEET", "EMPTY_SHEET"]
    assert any("NO_TITLE_BLOCK" in i for i in result["info"])
    assert [r["number"] for r in env.read("sheet_index", only_findings=True)["rows"]] == ["A102", "A104"]
    assert [r["number"] for r in env.read("sheet_index", name_contains="plans")["rows"]] == ["A101"]


def test_sheet_index_reports_duplicate_and_near_duplicate_numbers_and_placeholders(env):
    twin = env.s.add_sheet("A101", "Twin", True)  # built outside the stub's number check, as an old file could hold it
    env.s.add_sheet("a102 ", "Lower case twin", True)
    env.s.add_sheet("P100", "Reserved", False, placeholder=True)
    result = env.read("sheet_index")
    assert any(f.startswith("DUPLICATE_SHEET_NUMBER") and str(twin.Id.Value) in f for f in result["fails"])
    assert any("NEAR_DUPLICATE_SHEET_NUMBER" in i for i in result["info"])
    assert any("PLACEHOLDER_SHEET" in i for i in result["info"])
    rows = [r for r in result["rows"] if r["number"] == "P100"]
    assert rows and rows[0]["empty"] is False  # a placeholder sheet is not "empty"
    assert sorted(r["findings"] for r in result["rows"] if r["number"] == "A101") == ["duplicate_number,empty", "duplicate_number,empty"]


# --------------------------------------------------------------------------- #
# Update sheets
# --------------------------------------------------------------------------- #
def test_update_sheets_renames_and_renumbers_and_reads_back(env):
    result = env.write("update_sheets", sheets=[
        {"number": "A101", "new_number": "B101", "new_name": "Floor plans"},
        {"number": "A102", "new_name": "Sections and elevations"},
        {"number": "A103", "new_number": "B103"},
        {"number": "A104", "new_name": "No title block"},
    ])
    assert result["ok"] is True and result["verified"] is True, result
    s = env.s.sheets
    assert (s["A101"].SheetNumber, s["A101"].Name) == ("B101", "Floor plans")
    assert (s["A102"].SheetNumber, s["A102"].Name) == ("A102", "Sections and elevations")
    assert s["A103"].SheetNumber == "B103" and s["A103"].Name == "Details"
    by = {r["previous_number"]: r["status"] for r in result["rows"]}
    assert by == {"A101": "renumbered and renamed", "A102": "renamed", "A103": "renumbered", "A104": "unchanged"}
    assert sorted(result["changed_ids"]) == sorted(s[n].Id.Value for n in ("A101", "A102", "A103"))
    checks = {c["check"] for c in result["post_check"]["checks"]}
    assert {"numbers_unique", "other_sheets_untouched", "no_temporary_numbers"} <= checks


def test_a_number_that_another_sheet_keeps_is_a_collision_and_nothing_changes(env):
    before = env.s.snapshot()
    result = env.write("update_sheets", sheets=[{"number": "A101", "new_number": "A102", "new_name": "x"}, {"number": "A103", "new_name": "Details 2"}])
    failed(result, "sheet_number_conflict")
    assert "A102" in result["message"] and "not in the table" in result["message"]
    assert env.s.sheets["A102"].Id.Value in result["element_ids"] and env.s.snapshot() == before and txn_names(env) == []


def test_swapping_numbers_goes_through_temporary_numbers(env):
    result = env.write("update_sheets", sheets=[{"number": "A101", "new_number": "A102"}, {"number": "A102", "new_number": "A101"}])
    assert result["ok"] is True, result
    s = env.s.sheets
    assert (s["A101"].SheetNumber, s["A102"].SheetNumber) == ("A102", "A101")
    assert not any(e.SheetNumber.startswith("ZZ-PARK") for e in env.w.elements if isinstance(e, ds.ViewSheet))
    assert txn_names(env)[:2] == ["Park sheet A101 under a temporary number", "Park sheet A102 under a temporary number"]


def test_a_chain_of_numbers_works_and_a_failure_in_the_second_pass_leaves_no_temporary_number(env):
    chain = [{"number": "A101", "new_number": "A102"}, {"number": "A102", "new_number": "A103"}, {"number": "A103", "new_number": "A105"}]
    before = env.s.snapshot()
    env.w.fail_on["sheet_number"] = lambda n: n == 5  # 3 parks, then the 2nd final number
    result = env.write("update_sheets", sheets=chain)
    failed(result, "rolled_back")
    assert env.s.snapshot() == before
    env.w.fail_on.clear()
    good = env.write("update_sheets", sheets=chain)
    assert good["ok"] is True
    assert [env.s.sheets[n].SheetNumber for n in ("A101", "A102", "A103")] == ["A102", "A103", "A105"]


def test_update_sheets_table_errors_are_refused_before_revit(env):
    for rows, text in [
        ([{"number": "A101", "new_number": "B1"}, {"number": "A101", "new_name": "x"}], "listed twice"),
        ([{"number": "A101", "new_number": "B1"}, {"number": "A102", "new_number": "B1"}], "same number"),
        ([{"number": "A101"}], "changes nothing"),
        ([{"number": "A101", "new_name": "x", "extra": 1}], "unknown field"),
    ]:
        result = env.write("update_sheets", sheets=rows)
        failed(result, "invalid_input")
        assert text in result["message"]
    chain = env.write("update_sheets", sheets=[{"number": "A101", "new_number": "A102"}, {"number": "A102", "new_number": "A103"}], on_error="skip")
    failed(chain, "invalid_input")
    assert "on_error abort" in chain["message"]
    assert env.bridge.modes == []


def test_a_sheet_that_does_not_exist_is_refused(env):
    before = env.s.snapshot()
    failed(env.write("update_sheets", sheets=[{"number": "Z9", "new_name": "x"}]), "sheet_not_found")
    assert env.s.snapshot() == before


def test_update_sheets_dry_run_and_revit_refusal(env):
    before = env.s.snapshot()
    dry = env.write("update_sheets", sheets=[{"number": "A101", "new_number": "B101"}, {"number": "A102", "new_name": "x"}], dry_run=True)
    assert dry["ok"] is True and dry["dry_run"] is True and dry["would_change"]["by_status"] == {"renumbered": 1, "renamed": 1}
    assert env.s.snapshot() == before
    env.w.fail_on["sheet_number"] = lambda n: True
    failed(env.write("update_sheets", sheets=[{"number": "A101", "new_number": "B101"}]), "rolled_back")
    assert env.s.snapshot() == before
