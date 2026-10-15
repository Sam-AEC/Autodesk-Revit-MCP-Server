"""Tests for the model_changes module ("What changed since yesterday")."""
import json
import time
from pathlib import Path

import pytest

from revit_mcp_server.modules.model_changes.module import ModelChangesModule


class WS:
    def __init__(self, tmp_path: Path):
        self.allowed_directories = [tmp_path]


def _el(uid, category="Doors", mark="D1", **extra):
    el = {
        "uid": uid, "element_id": 1, "category": category, "class": "FamilyInstance",
        "family": "Single", "type_name": "900x2100", "level_uid": "L1",
        "location": {"kind": "point", "xyz": [0.0, 0.0, 0.0], "rotation": 0.0},
        "params": {"Mark": {"v": mark, "storage": "String"}},
    }
    el.update(extra)
    return el


def _write(ws, sid, elements, taken_at, source=None):
    d = ws.allowed_directories[0] / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.json").write_text(json.dumps({
        "schema": "amb.snapshot/1", "snapshot_id": sid, "taken_at": taken_at, "elements": elements,
        **({"source": source} if source is not None else {}),
    }), encoding="utf-8")


@pytest.fixture
def ws(tmp_path):
    return WS(tmp_path)


@pytest.fixture
def mod():
    return ModelChangesModule()


def test_added_removed_modified_unchanged(mod, ws):
    _write(ws, "old", [_el("a"), _el("b"), _el("c", mark="X"), _el("d", "Walls")], "2026-10-08T09:00:00+00:00")
    _write(ws, "new", [_el("a"), _el("c", mark="Y"), _el("e", "Walls"), _el("d", "Walls", location={"kind": "point", "xyz": [1, 0, 0]})],
           "2026-10-09T09:00:00+00:00")
    r = mod.compare_snapshots("old", "new", workspace=ws)
    assert r["totals"] == {"added": 1, "removed": 1, "modified": 2, "unchanged": 1, "parameter_changes": 1}
    assert [e["uid"] for e in r["added"]] == ["e"]
    assert [e["uid"] for e in r["removed"]] == ["b"]
    change = r["parameter_changes"][0]
    assert (change["uid"], change["parameter"], change["old"], change["new"]) == ("c", "Mark", "X", "Y")
    moved = next(m for m in r["modified"] if m["uid"] == "d")
    assert moved["other_changes"] == ["location"]
    assert r["counts_per_category"]["Doors"]["removed"] == 1
    assert r["counts_per_category"]["Walls"]["added"] == 1
    assert r["mock"] is False
    assert "1 element added" in r["summary"] and "1 element removed" in r["summary"]


def test_unchanged_summary(mod, ws):
    _write(ws, "o", [_el("a")], "2026-10-08T00:00:00+00:00")
    _write(ws, "n", [_el("a")], "2026-10-09T00:00:00+00:00")
    r = mod.compare_snapshots("o", "n", workspace=ws)
    assert r["totals"]["unchanged"] == 1
    assert r["summary"].startswith("No changes")


def test_latest_and_previous_and_listing(mod, ws):
    _write(ws, "s1", [_el("a")], "2026-10-07T00:00:00Z")
    _write(ws, "s3", [_el("a"), _el("b")], "2026-10-09T00:00:00Z")
    _write(ws, "s2", [_el("a")], "2026-10-08T00:00:00Z")
    listed = mod.list_snapshots(workspace=ws)
    assert [s["snapshot_id"] for s in listed["snapshots"]] == ["s3", "s2", "s1"]
    assert listed["snapshots"][0]["alias"] == "latest" and listed["snapshots"][1]["alias"] == "previous"
    assert listed["snapshots"][0]["element_count"] == 2
    r = mod.compare_snapshots("previous", "latest", workspace=ws)
    assert (r["older_snapshot_id"], r["newer_snapshot_id"]) == ("s2", "s3")
    assert r["totals"]["added"] == 1


def test_list_empty_and_latest_needs_two(mod, ws):
    assert mod.list_snapshots(workspace=ws)["snapshots"] == []
    _write(ws, "only", [_el("a")], "2026-10-09T00:00:00Z")
    with pytest.raises(ValueError, match="only 1 saved snapshot"):
        mod.compare_snapshots("previous", "latest", workspace=ws)


def test_missing_id_raises_clear_error(mod, ws):
    _write(ws, "here", [_el("a")], "2026-10-09T00:00:00Z")
    with pytest.raises(ValueError, match="'nope' not found"):
        mod.compare_snapshots("here", "nope", workspace=ws)
    with pytest.raises(ValueError, match="both"):
        mod.compare_snapshots("here", "", workspace=ws)
    with pytest.raises(ValueError, match="Invalid snapshot id"):
        mod.compare_snapshots("here", "../x", workspace=ws)


def test_no_ids_rejected_in_bridge_mode(mod, ws, monkeypatch):
    from revit_mcp_server.config import BridgeMode, config

    monkeypatch.setattr(config, "mode", BridgeMode.bridge)
    with pytest.raises(ValueError, match="requires a snapshot_id"):
        mod.compare_snapshots(workspace=ws)


def test_mock_mode_is_labelled(mod, ws, monkeypatch):
    from revit_mcp_server.config import BridgeMode, config

    monkeypatch.setattr(config, "mode", BridgeMode.mock)
    r = mod.compare_snapshots(workspace=ws)
    assert r["mock"] is True
    assert "MOCK DATA" in r["data_source"] and r["summary"].startswith("[MOCK DATA]")


def test_max_items_truncates_but_totals_are_complete(mod, ws):
    _write(ws, "o", [], "2026-10-08T00:00:00Z")
    _write(ws, "n", [_el(f"u{i}") for i in range(50)], "2026-10-09T00:00:00Z")
    r = mod.compare_snapshots("o", "n", max_items=5, workspace=ws)
    assert r["totals"]["added"] == 50 and len(r["added"]) == 5 and r["truncated"] is True


def test_large_snapshot_performance(mod, ws):
    n = 20000
    old = [_el(f"u{i}", "Doors" if i % 2 else "Walls", mark=str(i)) for i in range(n)]
    new = [_el(f"u{i}", "Doors" if i % 2 else "Walls", mark=str(i) if i % 10 else "chg") for i in range(n - 500)]
    new += [_el(f"new{i}") for i in range(300)]
    _write(ws, "o", old, "2026-10-08T00:00:00Z")
    _write(ws, "n", new, "2026-10-09T00:00:00Z")
    start = time.perf_counter()
    r = mod.compare_snapshots("o", "n", workspace=ws)
    elapsed = time.perf_counter() - start
    assert r["totals"]["added"] == 300 and r["totals"]["removed"] == 500
    assert r["totals"]["modified"] == sum(1 for i in range(n - 500) if i % 10 == 0 and str(i) != "chg")
    assert elapsed < 10


def _nl(uid):
    el = _el(uid)
    el.pop("location")
    return el


def test_different_documents_refused(mod, ws):
    _write(ws, "a", [_el("x")], "2026-10-08T00:00:00Z", {"doc_guid": "G1", "doc_title": "Tower"})
    _write(ws, "b", [_el("y")], "2026-10-09T00:00:00Z", {"doc_guid": "G2", "doc_title": "Annex"})
    with pytest.raises(ValueError, match="different Revit models"):
        mod.compare_snapshots("a", "b", workspace=ws)
    with pytest.raises(ValueError, match="different Revit models"):
        mod.compare_snapshots("previous", "latest", workspace=ws)


def test_same_document_ok_and_missing_guid_warns(mod, ws):
    src = {"doc_guid": "G1"}
    _write(ws, "a", [_el("x")], "2026-10-08T00:00:00Z", src)
    _write(ws, "b", [_el("x")], "2026-10-09T00:00:00Z", src)
    assert mod.compare_snapshots("a", "b", workspace=ws)["warnings"] == []
    _write(ws, "c", [_el("x")], "2026-10-10T00:00:00Z")
    r = mod.compare_snapshots("a", "c", workspace=ws)
    assert "same Revit model" in r["warnings"][0]


def test_rotation_change_is_a_location_change(mod, ws):
    def rot(r):
        return {"kind": "point", "xyz": [0.0, 0.0, 0.0], "rotation": r}

    _write(ws, "o", [_el("a", location=rot(0.0))], "2026-10-08T00:00:00Z")
    _write(ws, "n", [_el("a", location=rot(1.57))], "2026-10-09T00:00:00Z")
    r = mod.compare_snapshots("o", "n", workspace=ws)
    assert r["totals"]["modified"] == 1 and r["totals"]["unchanged"] == 0
    assert r["modified"][0]["other_changes"] == ["location"]


def test_missing_location_is_not_enough_data(mod, ws):
    _write(ws, "o", [_nl("a")], "2026-10-08T00:00:00Z")
    _write(ws, "n", [_nl("a")], "2026-10-09T00:00:00Z")
    r = mod.compare_snapshots("o", "n", workspace=ws)
    assert r["location_checked"] is False
    assert r["not_enough_data"][0]["check"] == "location"
    assert "Not enough data" in r["summary"]
    assert "location" in r["not_enough_data"][0]["reason"]


def test_location_present_has_no_caveat(mod, ws):
    _write(ws, "o", [_el("a")], "2026-10-08T00:00:00Z")
    _write(ws, "n", [_el("a")], "2026-10-09T00:00:00Z")
    r = mod.compare_snapshots("o", "n", workspace=ws)
    assert r["location_checked"] is True and r["not_enough_data"] == []
