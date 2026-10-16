"""revit_list_view_templates, revit_set_view_templates, revit_make_view_template and revit_align_crop.

The embedded scripts run under CPython against tests/revit_docs_stub.py. This proves the control flow (refusals, one
transaction per view, read-back, rollback, dry run, line protocol). It does NOT prove that Revit accepts the same calls:
that is UNVERIFIED.
"""
from __future__ import annotations

import pytest

import revit_docs_stub as ds
from docs_batch_helpers import make_env, failed, plan, ref, txn_names


@pytest.fixture()
def env(monkeypatch, tmp_path):
    yield from make_env(monkeypatch, tmp_path)



def set_template(view, template):
    object.__setattr__(view, "ViewTemplateId", template.Id)


# --------------------------------------------------------------------------- #
# View templates
# --------------------------------------------------------------------------- #
def test_list_view_templates_counts_the_views_that_use_each(env):
    for name in ("L0 Plan", "L1 Plan"):
        set_template(plan(env, name), env.s.tpl_plan)
    result = env.read("list_view_templates")
    assert result["ok"] is True and env.bridge.modes == ["read"]
    rows = {r["name"]: r for r in result["rows"]}
    assert rows["Plan Template"]["used_by"] == 2 and rows["Section Template"]["used_by"] == 0
    assert rows["Plan Template"]["view_type"] == "FloorPlan"
    assert any("UNUSED_TEMPLATES" in i for i in result["info"])
    only = env.read("list_view_templates", only_unused=True)
    assert [r["name"] for r in only["rows"]] == ["Section Template"]
    assert [r["name"] for r in env.read("list_view_templates", name_contains="plan")["rows"]] == ["Plan Template"]


def test_apply_view_template_assigns_reports_previous_and_skips_unchanged(env):
    set_template(plan(env, "L1 Plan"), env.s.tpl_plan)
    views = [ref(plan(env, "L0 Plan")), ref(plan(env, "L1 Plan")), {"view_name": "L2 Plan"}]
    result = env.write("apply_view_template", template="Plan Template", views=views)
    assert result["ok"] is True and result["verified"] is True, result
    assert all(plan(env, n).ViewTemplateId.Value == env.s.tpl_plan.Id.Value for n in ("L0 Plan", "L1 Plan", "L2 Plan"))
    by = {r["name"]: r["status"] for r in result["rows"]}
    assert by == {"L0 Plan": "applied", "L1 Plan": "unchanged", "L2 Plan": "applied"}
    assert sorted(result["changed_ids"]) == sorted([plan(env, "L0 Plan").Id.Value, plan(env, "L2 Plan").Id.Value])
    assert txn_names(env) == ["Apply template 'Plan Template' to view 'L0 Plan'", "Apply template 'Plan Template' to view 'L2 Plan'"]


def test_apply_view_template_by_id_and_dry_run(env):
    before = env.s.snapshot()
    result = env.write("apply_view_template", template_id=env.s.tpl_plan.Id.Value, views=[ref(plan(env, "L0 Plan"))], dry_run=True)
    assert result["ok"] is True and result["dry_run"] is True and result["would_change"]["by_status"] == {"applied": 1}
    assert env.s.snapshot() == before


def test_a_template_that_does_not_fit_the_view_type_fails_with_the_view_id(env):
    before = env.s.snapshot()
    result = env.write("apply_view_template", template="Plan Template", views=[ref(plan(env, "L0 Plan")), ref(env.s.section)])
    failed(result, "rolled_back")
    assert env.s.section.Id.Value in result["element_ids"] and "cannot be applied" in result["message"]
    assert env.s.snapshot() == before


def test_apply_view_template_skip_keeps_what_fits(env):
    result = env.write("apply_view_template", template="Plan Template", views=[ref(env.s.section), ref(plan(env, "L0 Plan"))], on_error="skip")
    failed(result, "partial_failure")
    assert plan(env, "L0 Plan").ViewTemplateId.Value == env.s.tpl_plan.Id.Value and env.s.section.ViewTemplateId.Value == -1


@pytest.mark.parametrize("args,kind", [
    ({"template": "Nope", "views": [{"view_name": "L0 Plan"}]}, "template_not_found"),
    ({"template_id": 424242, "views": [{"view_name": "L0 Plan"}]}, "template_not_found"),
    ({"template": "Plan Template", "views": [{"view_name": "Plan Template"}]}, "view_not_found"),
    ({"template": "Plan Template", "views": [{"view_name": "A101"}]}, "view_not_found"),
])
def test_apply_view_template_refusals_change_nothing(env, args, kind):
    before = env.s.snapshot()
    result = env.write("apply_view_template", **args)
    failed(result, kind)
    if kind == "template_not_found":
        assert "Plan Template" in result["message"]
    assert env.s.snapshot() == before


def test_make_view_template_creates_names_and_reads_back(env):
    src = plan(env, "L0 Plan")
    result = env.write("make_view_template", view=ref(src), name="Coordination plan", assign_to_view=True)
    assert result["ok"] is True and result["verified"] is True, result
    tpl = next(e for e in env.w.elements if isinstance(e, ds.DView) and e.IsTemplate and e.Name == "Coordination plan")
    assert result["changed_ids"] == [tpl.Id.Value] and tpl.ViewType == "FloorPlan"
    assert src.ViewTemplateId.Value == tpl.Id.Value
    assert result["rows"][0]["source_view_id"] == src.Id.Value and result["rows"][0]["assigned_to_source"] is True


def test_make_view_template_never_replaces_a_template_with_that_name(env):
    before = env.s.snapshot()
    result = env.write("make_view_template", view=ref(plan(env, "L0 Plan")), name="Plan Template")
    failed(result, "name_conflict")
    assert result["element_ids"] == [env.s.tpl_plan.Id.Value] and env.s.snapshot() == before


def test_make_view_template_refuses_sheets_and_templates_and_dry_runs_cleanly(env):
    failed(env.write("make_view_template", view=ref(env.s.sheets["A101"]), name="x"), "view_not_found")
    failed(env.write("make_view_template", view=ref(env.s.tpl_plan), name="x"), "view_not_found")
    before = env.s.snapshot()
    result = env.write("make_view_template", view=ref(plan(env, "L0 Plan")), name="Trial", dry_run=True)
    assert result["ok"] is True and result["dry_run"] is True and result["changed_ids"] == []
    assert env.s.snapshot() == before


def test_make_view_template_failure_names_the_source_view(env):
    env.w.fail_on["create_template"] = lambda n: True
    before = env.s.snapshot()
    result = env.write("make_view_template", view=ref(plan(env, "L0 Plan")), name="Trial")
    failed(result, "rolled_back")
    assert plan(env, "L0 Plan").Id.Value in result["element_ids"] and env.s.snapshot() == before


# --------------------------------------------------------------------------- #
# revit_align_crop
# --------------------------------------------------------------------------- #
def test_align_crop_copies_the_reference_rectangle_in_model_coordinates(env):
    ref_view, a, b = plan(env, "L0 Plan"), plan(env, "L1 Plan"), plan(env, "L2 Plan")
    ref_view.set_crop((2.0, 3.0, -1.0), (42.0, 33.0, 1.0), ds.Transform((5.0, 7.0, 0.0)))
    a.set_crop((0.0, 0.0, -4.0), (10.0, 10.0, 6.0), ds.Transform((0.0, 0.0, 10.0)))
    b.set_crop((1.0, 1.0, -1.0), (5.0, 5.0, 1.0), ds.Transform((100.0, -50.0, 20.0)))
    object.__setattr__(b, "CropBoxActive", False)
    want = ds.box_in_model(ref_view)
    result = env.write("align_crop", reference=ref(ref_view), views=[ref(a), {"view_name": "L2 Plan"}, ref(ref_view)])
    assert result["ok"] is True and result["verified"] is True, result
    for v in (a, b):
        assert ds.box_in_model(v) == pytest.approx(want) and v.CropBoxActive is True
    assert (a.CropBox.Min.Z, a.CropBox.Max.Z) == (-4.0, 6.0)  # the height range of each view is kept
    assert sorted(result["changed_ids"]) == sorted([a.Id.Value, b.Id.Value])
    assert {r["name"]: r["status"] for r in result["rows"]} == {"L1 Plan": "aligned", "L2 Plan": "aligned"}
    assert txn_names(env) == ["Align crop of view 'L1 Plan' to 'L0 Plan'", "Align crop of view 'L2 Plan' to 'L0 Plan'"]
    again = env.write("align_crop", reference=ref(ref_view), views=[ref(a), ref(b)])
    assert again["ok"] is True and {r["status"] for r in again["rows"]} == {"unchanged"} and again["changed_ids"] == []


def test_annotation_crop_on_off_and_match_reference_with_offsets(env):
    ref_view, a, b = plan(env, "L0 Plan"), plan(env, "L1 Plan"), plan(env, "L2 Plan")
    object.__setattr__(ref_view.annot, "value", 1)
    ref_view.shape.LeftAnnotationCropOffset, ref_view.shape.TopAnnotationCropOffset = 0.25, 0.5
    result = env.write("align_crop", reference=ref(ref_view), views=[ref(a), ref(b)], align_crop_box=False, annotation_crop="match_reference")
    assert result["ok"] is True, result
    for v in (a, b):
        assert v.annot.value == 1 and v.shape.LeftAnnotationCropOffset == 0.25 and v.shape.TopAnnotationCropOffset == 0.5
    off = env.write("align_crop", reference=ref(ref_view), views=[ref(a)], align_crop_box=False, annotation_crop="off")
    assert off["ok"] is True and a.annot.value == 0 and b.annot.value == 1
    assert [r["annotation_crop"] for r in off["rows"]] == [0]


def test_align_crop_refuses_what_it_cannot_do_and_starts_no_transaction(env):
    ref_view, a = plan(env, "L0 Plan"), plan(env, "L1 Plan")
    failed(env.write("align_crop", reference=ref(env.s.section), views=[ref(a)]), "view_not_plan")
    failed(env.write("align_crop", reference=ref(ref_view), views=[ref(env.s.view3d)]), "view_not_plan")
    failed(env.write("align_crop", reference=ref(ref_view), views=[ref(env.s.tpl_plan)]), "view_not_plan")
    failed(env.write("align_crop", reference=ref(ref_view), views=[ref(ref_view)]), "invalid_input")
    object.__setattr__(ref_view, "CropBoxActive", False)
    failed(env.write("align_crop", reference=ref(ref_view), views=[ref(a)]), "reference_crop_off")
    object.__setattr__(ref_view, "CropBoxActive", True)
    ref_view.shape.ShapeSet = True
    failed(env.write("align_crop", reference=ref(ref_view), views=[ref(a)]), "crop_not_rectangular")
    assert txn_names(env) == [] and env.bridge.modes.count("write") == 6


def test_a_rotated_or_shaped_target_fails_with_its_id_and_rolls_back(env):
    ref_view, a, b = plan(env, "L0 Plan"), plan(env, "L1 Plan"), plan(env, "L2 Plan")
    a.set_crop((0.0, 0.0, -1.0), (9.0, 9.0, 1.0), ds.Transform((0.0, 0.0, 10.0)))
    b.set_crop((0.0, 0.0, -1.0), (9.0, 9.0, 1.0), ds.Transform((0.0, 0.0, 20.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)))
    before = env.s.snapshot()
    result = env.write("align_crop", reference=ref(ref_view), views=[ref(a), ref(b)])
    failed(result, "rolled_back")
    assert result["element_ids"] == [b.Id.Value] and "rotated" in result["message"] and env.s.snapshot() == before
    a.shape.ShapeSet = True
    shaped = env.write("align_crop", reference=ref(ref_view), views=[ref(a)])
    failed(shaped, "rolled_back")
    assert "custom crop shape" in shaped["message"] and shaped["element_ids"] == [a.Id.Value]


def test_align_crop_post_check_catches_a_crop_that_did_not_take(env, monkeypatch):
    ref_view, a = plan(env, "L0 Plan"), plan(env, "L1 Plan")
    a.set_crop((0.0, 0.0, -1.0), (9.0, 9.0, 1.0), ds.Transform((0.0, 0.0, 10.0)))
    # a view template that controls the crop: the assignment is accepted but ignored
    monkeypatch.setattr(ds.DView, "CropBox", property(lambda self: self._crop.copy(), lambda self, box: None))
    result = env.write("align_crop", reference=ref(ref_view), views=[ref(a)])
    failed(result, "rolled_back")
    assert "crop_matches_reference" in result["message"]


def test_align_crop_dry_run_and_skip(env):
    ref_view, a, b = plan(env, "L0 Plan"), plan(env, "L1 Plan"), plan(env, "L2 Plan")
    a.set_crop((0.0, 0.0, -1.0), (9.0, 9.0, 1.0), ds.Transform((0.0, 0.0, 10.0)))
    b.set_crop((0.0, 0.0, -1.0), (9.0, 9.0, 1.0), ds.Transform((0.0, 0.0, 20.0)))
    before = env.s.snapshot()
    dry = env.write("align_crop", reference=ref(ref_view), views=[ref(a), ref(b)], dry_run=True)
    assert dry["ok"] is True and dry["committed"] is False and dry["would_change"]["by_status"] == {"aligned": 2}
    assert env.s.snapshot() == before
    b.shape.ShapeSet = True
    skip = env.write("align_crop", reference=ref(ref_view), views=[ref(a), ref(b)], on_error="skip")
    failed(skip, "partial_failure")
    assert ds.box_in_model(a) == pytest.approx(ds.box_in_model(ref_view))
    assert ds.box_in_model(b) != pytest.approx(ds.box_in_model(ref_view))
