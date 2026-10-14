"""Tests for the read-only clash triage module (see docs/clash-triage.md, slice A). Fixtures only; no live Revit or Navisworks."""
import importlib.util
import json
from pathlib import Path

import pytest

from revit_mcp_server.semantic.engine import generate_mock_snapshot


def _load_mod():
    # Import under its package name so coverage (source_pkgs) measures it.
    return importlib.import_module("revit_mcp_server.modules.clash_triage.module")


ClashTriageModule = _load_mod().ClashTriageModule

WALL = "c0326e0e-473d-4952-b8ec-f23696541f43-wall-1"
DOOR = "c0326e0e-473d-4952-b8ec-f23696541f44-door-1"


class WS:
    def __init__(self, p):
        self.allowed_directories = [p]


def _item(name, guid, instance="11111111-1111-1111-1111-111111111111"):
    return {"displayName": name, "className": "LcRevitNode", "instanceGuid": instance, "ifcGuid": guid}


def _clash(guid, i1, i2, name="Clash1"):
    return {"displayName": name, "guid": guid, "status": "New", "distance": -0.05, "item1": i1, "item2": i2}


@pytest.fixture
def mod():
    return ClashTriageModule()


@pytest.fixture
def ws(tmp_path):
    return WS(tmp_path)


def _write_snapshot(tmp_path, elements):
    snap = generate_mock_snapshot()
    data = json.loads(snap.model_dump_json(by_alias=True))
    data["elements"] = elements
    (tmp_path / "snapshots").mkdir(exist_ok=True)
    (tmp_path / "snapshots" / "snap1.json").write_text(json.dumps(data), encoding="utf-8")
    return "snap1"


def test_exact_by_unique_id_mock_mode(mod, ws):
    res = {"results": [_clash("c1", _item("Wall", WALL), _item("Door", DOOR))]}
    out = mod.match_clashes(clash_results=res, workspace=ws)
    c = out["clashes"][0]
    assert out["read_only"] is True
    assert c["confidence"] == "exact"
    assert c["item1"]["element"]["uid"] == WALL
    assert c["item1"]["match_kind"] == "unique_id"
    assert out["summary"] == {"exact": 1, "ambiguous": 0, "unmatched": 0}


def test_exact_by_ifc_guid_parameter(mod, ws, tmp_path):
    els = [{"uid": "u-1", "element_id": 1, "category": "OST_Walls",
            "params": {"IfcGUID": {"v": "2O2Fr$t4X7Zf8NOew3FLOH", "storage": "String"}}},
           {"uid": "u-2", "element_id": 2, "category": "OST_Doors", "params": {}}]
    sid = _write_snapshot(tmp_path, els)
    res = [_clash("c1", _item("Wall", "2O2Fr$t4X7Zf8NOew3FLOH"), _item("Door", "u-2"))]
    out = mod.match_clashes(clash_results=res, snapshot_id=sid, workspace=ws)
    c = out["clashes"][0]
    assert c["confidence"] == "exact"
    assert c["item1"]["match_kind"] == "ifc_guid"
    assert c["item2"]["match_kind"] == "unique_id"


def test_ambiguous_when_guid_hits_two_elements(mod, ws, tmp_path):
    els = [{"uid": "u-1", "element_id": 1, "category": "OST_Walls",
            "params": {"IfcGUID": {"v": "DUPLICATE", "storage": "String"}}},
           {"uid": "u-2", "element_id": 2, "category": "OST_Walls",
            "params": {"IfcGUID": {"v": "DUPLICATE", "storage": "String"}}},
           {"uid": "u-3", "element_id": 3, "category": "OST_Doors", "params": {}}]
    sid = _write_snapshot(tmp_path, els)
    res = [_clash("c1", _item("Wall", "DUPLICATE"), _item("Door", "u-3"))]
    c = mod.match_clashes(clash_results=res, snapshot_id=sid, workspace=ws)["clashes"][0]
    assert c["confidence"] == "ambiguous"
    assert c["item1"]["element"] is None  # nothing chosen silently
    assert len(c["item1"]["candidates"]) == 2


def test_unmatched_and_never_uses_instance_guid_or_element_id(mod, ws):
    # InstanceGuid equals a real UniqueId and 200 is a real ElementId: neither may match.
    item = _item("Wall", None, instance=WALL)
    item["elementId"] = 200
    res = [_clash("c1", item, _item("Ghost", "no-such-guid"))]
    c = mod.match_clashes(clash_results=res, workspace=ws)["clashes"][0]
    assert c["confidence"] == "unmatched"
    assert c["item1"]["element"] is None and "no GUID" in c["item1"]["reason"]
    assert c["item2"]["confidence"] == "unmatched"


def test_overall_is_worst_of_both_sides(mod, ws):
    res = [_clash("c1", _item("Wall", WALL), _item("Ghost", "nope"))]
    c = mod.match_clashes(clash_results=res, workspace=ws)["clashes"][0]
    assert c["item1"]["confidence"] == "exact"
    assert c["confidence"] == "unmatched"


def test_issues_recorded_and_listed_without_duplicates(mod, ws):
    res = {"results": [_clash("c1", _item("Wall", WALL), _item("Door", DOOR)),
                       _clash("c2", _item("Wall", WALL), _item("Ghost", "nope"), name="Clash2")]}
    assert mod.match_clashes(clash_results=res, workspace=ws)["issues_recorded"] == 2
    mod.match_clashes(clash_results=res, workspace=ws)  # re-run updates, not duplicates
    assert mod.list_clash_issues(workspace=ws)["total"] == 2
    assert mod.list_clash_issues(match="unmatched", workspace=ws)["total"] == 1
    exact = mod.list_clash_issues(match="exact", workspace=ws)["issues"][0]
    assert exact["element_uid_a"] == WALL and exact["element_uid_b"] == DOOR


def test_record_issues_false_writes_nothing(mod, ws, tmp_path):
    res = [_clash("c1", _item("Wall", WALL), _item("Door", DOOR))]
    out = mod.match_clashes(clash_results=res, record_issues=False, workspace=ws)
    assert out["issues_recorded"] == 0
    assert not (tmp_path / "clash_triage.db").exists()


def test_bridge_mode_rejects_missing_snapshot(mod, ws, monkeypatch):
    from revit_mcp_server.config import BridgeMode, config
    monkeypatch.setattr(config, "mode", BridgeMode.bridge)
    res = [_clash("c1", _item("Wall", WALL), _item("Door", DOOR))]
    with pytest.raises(ValueError, match="requires a snapshot_id"):
        mod.match_clashes(clash_results=res, workspace=ws)


def test_unknown_snapshot_and_bad_input(mod, ws):
    with pytest.raises(ValueError, match="not found"):
        mod.match_clashes(clash_results=[], snapshot_id="missing", workspace=ws)
    with pytest.raises(ValueError):
        mod.match_clashes(clash_results={"oops": 1}, workspace=ws)


def test_module_declares_no_mutating_commands():
    p = Path(__file__).parent.parent / "src/revit_mcp_server/modules/clash_triage/module.json"
    manifest = json.loads(p.read_text(encoding="utf-8"))
    assert manifest["permissions"] == ["model.read"]
    assert all(c["is_mutating"] is False for c in manifest["commands"])


def test_snapshot_id_cannot_escape_snapshots_dir(mod, ws, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"elements": [{"uid": WALL}], "source": {"doc_guid": "x"}}), encoding="utf-8")
    (tmp_path / "snapshots").mkdir(exist_ok=True)
    res = [_clash("c1", _item("Wall", WALL), _item("Door", DOOR))]
    for bad in ("../outside", str(tmp_path / "outside")):
        with pytest.raises(ValueError):
            mod.match_clashes(clash_results=res, snapshot_id=bad, workspace=ws)


def test_list_clash_issues_does_not_create_the_database(mod, ws, tmp_path):
    out = mod.list_clash_issues(workspace=ws)
    assert out == {"total": 0, "issues": []}
    assert not (tmp_path / "clash_triage.db").exists()

