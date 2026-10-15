"""Tests for the sheet_view_audit module (fixtures are synthetic snapshots)."""
import json

import pytest


import revit_mcp_server.modules.sheet_view_audit.module as _mod


class WS:
    def __init__(self, path):
        self.allowed_directories = [path]


def _snapshot(tmp_path, data, sid="snap1"):
    d = tmp_path / "snapshots"
    d.mkdir(exist_ok=True)
    (d / f"{sid}.json").write_text(json.dumps(data), encoding="utf-8")
    return sid


def _run(tmp_path, data, **kw):
    sid = _snapshot(tmp_path, data)
    return _mod.SheetViewAuditModule().run_audit(snapshot_id=sid, workspace=WS(tmp_path), **kw)


def _by_check(result):
    return {f["check"]: f for f in result["findings"]}


CLEAN = {
    "sheets": [
        {"uid": "s1", "number": "A-101", "name": "Plan", "view_uids": ["v1"]},
        {"uid": "s2", "number": "S-101", "name": "Framing", "view_uids": ["v2"]},
    ],
    "views": [
        {"uid": "v1", "name": "Level 1 Plan", "view_type": "FloorPlan"},
        {"uid": "v2", "name": "Framing L1", "view_type": "FloorPlan"},
    ],
}


def test_clean_snapshot_has_no_findings(tmp_path):
    r = _run(tmp_path, CLEAN)
    assert r["total_findings"] == 0
    assert r["sheets_per_discipline_prefix"] == {"A": 1, "S": 1}


def test_empty_sheet(tmp_path):
    data = {**CLEAN, "sheets": CLEAN["sheets"] + [{"uid": "s3", "number": "A-102", "name": "Empty", "view_uids": []}]}
    f = _by_check(_run(tmp_path, data))["empty_sheets"]
    assert f["unique_ids"] == ["s3"]
    assert f["severity"] == "warning" and f["next_step"]


def test_view_with_sheet_uid_counts_as_placed(tmp_path):
    data = {
        "sheets": [{"uid": "s1", "number": "A-1", "name": "x"}],
        "views": [{"uid": "v1", "name": "Plan", "view_type": "FloorPlan", "sheet_uid": "s1"}],
    }
    assert _run(tmp_path, data)["total_findings"] == 0


def test_unplaced_views_skip_templates_and_browsers(tmp_path):
    data = {
        **CLEAN,
        "views": CLEAN["views"] + [
            {"uid": "v3", "name": "Working Plan", "view_type": "FloorPlan"},
            {"uid": "v4", "name": "Tmpl", "view_type": "FloorPlan", "is_template": True},
            {"uid": "v5", "name": "Project Browser", "view_type": "ProjectBrowser"},
        ],
    }
    f = _by_check(_run(tmp_path, data))["views_not_on_sheet"]
    assert f["unique_ids"] == ["v3"]


def test_duplicate_sheet_numbers_case_insensitive(tmp_path):
    data = {**CLEAN, "sheets": CLEAN["sheets"] + [{"uid": "s3", "number": "a-101", "name": "Dup", "view_uids": ["v1"]}]}
    f = _by_check(_run(tmp_path, data))["duplicate_sheet_numbers"]
    assert f["unique_ids"] == ["s1", "s3"]
    assert f["severity"] == "error"


def test_missing_default_required_parameters(tmp_path):
    data = {**CLEAN, "sheets": CLEAN["sheets"] + [{"uid": "s3", "number": "A-9", "name": " ", "view_uids": ["v1"]}]}
    f = _by_check(_run(tmp_path, data))["missing_sheet_parameter"]
    assert f["unique_ids"] == ["s3"]
    assert "Sheet Name" in f["message"]


def test_configurable_required_parameters(tmp_path):
    data = {
        "sheets": [
            {"uid": "s1", "number": "A-1", "name": "x", "view_uids": ["v1"], "params": {"Drawn By": {"v": "SM"}}},
            {"uid": "s2", "number": "A-2", "name": "y", "view_uids": ["v1"], "params": {"Drawn By": {"v": ""}}},
            {"uid": "s3", "number": "A-3", "name": "z", "view_uids": ["v1"]},
        ],
        "views": [{"uid": "v1", "name": "P", "view_type": "FloorPlan"}],
    }
    r = _run(tmp_path, data, required_sheet_parameters=["Drawn By"])
    assert _by_check(r)["missing_sheet_parameter"]["unique_ids"] == ["s2", "s3"]
    # An empty list turns the check off.
    assert _run(tmp_path, data, required_sheet_parameters=[])["total_findings"] == 0


@pytest.mark.parametrize("name,flagged", [
    ("Copy of Level 1", True),
    ("Level 1 Copy 1", True),
    ("{3D}", True),
    ("Section 1", True),
    ("Detail 12", True),
    ("Section 1 - Stair", False),
    ("Level 1 Plan", False),
])
def test_default_view_names(tmp_path, name, flagged):
    data = {
        "sheets": [{"uid": "s1", "number": "A-1", "name": "x", "view_uids": ["v1"]}],
        "views": [{"uid": "v1", "name": name, "view_type": "Section"}],
    }
    assert ("default_view_names" in _by_check(_run(tmp_path, data))) is flagged


def test_counts_per_discipline_prefix(tmp_path):
    data = {
        "sheets": [
            {"uid": "1", "number": "A-101", "name": "a", "view_uids": ["v"]},
            {"uid": "2", "number": "A102", "name": "a", "view_uids": ["v"]},
            {"uid": "3", "number": "AE-1", "name": "a", "view_uids": ["v"]},
            {"uid": "4", "number": "101", "name": "a", "view_uids": ["v"]},
        ],
        "views": [{"uid": "v", "name": "P", "view_type": "FloorPlan", "discipline": "Architectural"}],
    }
    r = _run(tmp_path, data)
    assert r["sheets_per_discipline_prefix"] == {"(none)": 1, "A": 2, "AE": 1}
    assert r["views_per_discipline"] == {"Architectural": 1}


def test_findings_sorted_by_severity(tmp_path):
    data = {
        "sheets": [
            {"uid": "1", "number": "A-1", "name": "a", "view_uids": []},
            {"uid": "2", "number": "A-1", "name": "a", "view_uids": []},
        ],
        "views": [{"uid": "v", "name": "Section 1", "view_type": "Section"}],
    }
    sev = [f["severity"] for f in _run(tmp_path, data)["findings"]]
    assert sev == sorted(sev, key=lambda s: ["error", "warning", "info"].index(s))


def test_snapshot_without_sheet_data_says_so(tmp_path):
    r = _run(tmp_path, {"elements": []})
    assert r["status"] == "no_sheet_view_data"
    assert r["findings"] == []


def test_missing_snapshot_errors(tmp_path):
    with pytest.raises(ValueError):
        _mod.SheetViewAuditModule().run_audit(snapshot_id="nope", workspace=WS(tmp_path))
    with pytest.raises(ValueError):
        _mod.SheetViewAuditModule().run_audit(workspace=WS(tmp_path))


def _live_el(uid, cls, **params):
    return {"uid": uid, "element_id": 1, "category": "OST_Sheets", "class": cls, "family": "", "type_name": "",
            "params": {k: {"v": v, "storage": "String"} for k, v in params.items()}}


LIVE = {"schema": "amb.snapshot/1", "elements": [
    _live_el("s1", "ViewSheet", **{"Sheet Number": "A-101", "Sheet Name": "Plan"}),
    _live_el("s2", "ViewSheet", **{"Sheet Number": "A-101", "Sheet Name": ""}),
    _live_el("d1", "ViewDrafting", **{"View Name": "Copy of Detail"}),
]}


def test_live_snapshot_runs_what_it_can_and_names_the_rest(tmp_path):
    """Real snapshots have only ViewSheet/ViewDrafting elements, no placement info."""
    r = _run(tmp_path, LIVE)
    assert r["status"] == "partial"
    assert r["sheet_count"] == 2
    found = _by_check(r)
    assert "duplicate_sheet_numbers" in found and "missing_sheet_parameter" in found
    assert "default_view_names" in found
    assert "empty_sheets" not in found and "views_not_on_sheet" not in found
    for k in ("empty_sheets", "views_not_on_sheet"):
        assert r["checks"][k]["status"] == "not_enough_data"
        assert r["checks"][k]["reason"] and r["checks"][k]["missing"]
    assert "NOT run" in r["message"]


def test_live_snapshot_with_sheets_never_reports_all_clear_for_unchecked(tmp_path):
    data = {"elements": [_live_el("s1", "ViewSheet", **{"Sheet Number": "A-1", "Sheet Name": "x"})]}
    r = _run(tmp_path, data)
    assert r["status"] == "partial" and r["total_findings"] == 0
    assert r["checks"]["empty_sheets"]["status"] == "not_enough_data"


def test_snapshot_without_sheets_or_views_is_no_data(tmp_path):
    r = _run(tmp_path, {"elements": [_live_el("w1", "Wall")]})
    assert r["status"] == "no_sheet_view_data"


def test_full_data_reports_all_checks_ran(tmp_path):
    r = _run(tmp_path, CLEAN)
    assert r["status"] == "ok"
    assert all(c["status"] == "ran" for c in r["checks"].values())


def test_snapshot_id_declared_required():
    import json
    from pathlib import Path
    mj = Path(_mod.__file__).with_name("module.json")
    cmd = json.loads(mj.read_text(encoding="utf-8"))["commands"][0]
    assert cmd["input_schema"]["required"] == ["snapshot_id"]
