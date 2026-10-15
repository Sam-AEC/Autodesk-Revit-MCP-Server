"""Tests for the read-only model bloat audit module (fixture snapshots)."""
import json

import pytest

from revit_mcp_server.modules.model_bloat.module import ModelBloatModule


class WS:
    def __init__(self, tmp_path):
        self.allowed_directories = [tmp_path]


def _el(i, family, type_name, type_uid=None, cls="FamilyInstance", params=None):
    return {"uid": f"e{i}", "element_id": i, "category": "OST_Furniture", "class": cls,
            "family": family, "type_name": type_name, "type_uid": type_uid, "params": params or {}}


def _ty(uid, family, name, source="loadable"):
    return {"uid": uid, "category": "OST_Furniture", "family": family, "type_name": name,
            "family_source": source, "params": {}}


def _write(tmp_path, elements, types, sid="snap1", **extra):
    d = tmp_path / "snapshots"
    d.mkdir(exist_ok=True)
    (d / f"{sid}.json").write_text(json.dumps({"elements": elements, "types": types, **extra}), encoding="utf-8")
    return sid


@pytest.fixture
def fixture_snapshot(tmp_path):
    types = [
        _ty("t1", "Chair", "Std"), _ty("t2", "Chair", "Spare"),       # Chair used, Spare unused
        _ty("t3", "OldTable", "A"), _ty("t4", "OldTable", "B"),       # whole family unused
        _ty("t5", "Mass Blob", "Blob", "inplace"),                    # in-place, used
        _ty("t6", "Wall", "Generic", "system"),                       # system, unused: type-level only
    ] + [_ty(f"d{i}", "Door Mega", f"D{i}") for i in range(30)]       # large family
    elements = [
        _el(1, "Chair", "Std", "t1"), _el(2, "Chair", "Std", "t1"),
        _el(3, "Mass Blob", "Blob", "t5"),
        _el(4, None, "site-plan.dwg", cls="ImportInstance"),
        _el(5, None, "xref.dwg", cls="ImportInstance", params={"IsLinked": {"v": True}}),
    ] + [_el(10 + i, "Door Mega", f"D{i}", f"d{i}") for i in range(30)]
    return _write(tmp_path, elements, types)


def test_flags_everything_and_sorts_by_impact(tmp_path, fixture_snapshot):
    r = ModelBloatModule().audit(snapshot_id=fixture_snapshot, workspace=WS(tmp_path))
    assert r["read_only"] is True and r["usage_counts_available"] is True
    assert [f["family"] for f in r["unused_families"]["items"]] == ["OldTable"]
    unused_types = {(t["family"], t["type_name"]) for t in r["unused_types"]["items"]}
    assert ("Chair", "Spare") in unused_types and ("Wall", "Generic") in unused_types
    assert ("Chair", "Std") not in unused_types
    assert [f["family"] for f in r["in_place_families"]["items"]] == ["Mass Blob"]
    assert r["in_place_families"]["items"][0]["placed_instances"] == 1
    assert r["families_with_very_many_types"]["items"][0]["type_count"] == 30
    cad = {c["name"]: c["kind"] for c in r["imported_cad"]["items"]}
    assert cad == {"site-plan.dwg": "imported", "xref.dwg": "linked"}
    assert r["imported_cad"]["items"][0]["name"] == "site-plan.dwg"  # worst first
    # headline starts with the heaviest issue (imported CAD)
    assert "imported CAD" in r["headline_findings"][0]
    assert 0 <= r["cleanliness"]["score"] < 100
    assert "Nothing has been deleted" in " ".join(r["notes"])
    assert "approved plan" in " ".join(r["notes"])


def test_threshold_and_max_items(tmp_path, fixture_snapshot):
    r = ModelBloatModule().audit(snapshot_id=fixture_snapshot, workspace=WS(tmp_path),
                                 large_type_threshold=40, max_items=1)
    assert r["families_with_very_many_types"]["total"] == 0
    assert r["unused_types"]["total"] == 2 and r["unused_types"]["shown"] == 1


def test_matches_by_family_and_type_name_without_uid(tmp_path):
    sid = _write(tmp_path, [_el(1, "Chair", "Std")], [_ty("t1", "Chair", "Std"), _ty("t2", "Chair", "Spare")])
    r = ModelBloatModule().audit(snapshot_id=sid, workspace=WS(tmp_path))
    assert [t["type_name"] for t in r["unused_types"]["items"]] == ["Spare"]


def test_no_instance_data_is_reported_not_guessed(tmp_path):
    sid = _write(tmp_path, [], [_ty("t1", "Chair", "Std"), _ty("t2", "Blob", "B", "inplace")])
    r = ModelBloatModule().audit(snapshot_id=sid, workspace=WS(tmp_path))
    assert r["usage_counts_available"] is False
    assert r["unused_families"]["total"] is None and r["unused_types"]["items"] == []
    assert r["cleanliness"]["score"] is None
    assert r["in_place_families"]["total"] == 1
    assert r["in_place_families"]["items"][0]["placed_instances"] is None
    assert "could not be worked out" in " ".join(r["notes"])


def test_clean_model(tmp_path):
    sid = _write(tmp_path, [_el(1, "Chair", "Std", "t1")], [_ty("t1", "Chair", "Std")], cad_scanned=True)
    r = ModelBloatModule().audit(snapshot_id=sid, workspace=WS(tmp_path))
    assert r["cleanliness"]["score"] == 100 and r["headline_findings"] == []


def test_missing_snapshot_and_mock_snapshot(tmp_path):
    with pytest.raises(ValueError):
        ModelBloatModule().audit(snapshot_id="nope", workspace=WS(tmp_path))
    r = ModelBloatModule().audit(workspace=WS(tmp_path))
    assert r["read_only"] is True and "summary" in r


def test_module_is_registered_as_read_only_tool(tmp_path):
    from revit_mcp_server.config import Config
    from revit_mcp_server.module_registry import ModuleRegistry
    from revit_mcp_server.providers.module_provider import ModuleProvider
    from revit_mcp_server.security.workspace import WorkspaceMonitor

    cfg = Config(workspace_dir=tmp_path, allowed_directories=[tmp_path],
                 audit_log=tmp_path / "audit.log", enable_user_modules=False)
    registry = ModuleRegistry(config_obj=cfg)
    registry.discover_and_load()
    assert registry.get_module("model_bloat") is not None
    provider = ModuleProvider(module_registry=registry, workspace=WorkspaceMonitor([tmp_path]))
    tools = {c.name: c for c in provider.get_capabilities()}
    assert "model_bloat_audit" in tools
    assert tools["model_bloat_audit"].is_mutating is False


def test_live_snapshot_without_types_is_not_rated_not_100(tmp_path):
    """A real extractor snapshot has elements only: no types, no CAD records."""
    sid = _write(tmp_path, [_el(1, "Chair", "Std", "t1")], [])
    r = ModelBloatModule().audit(snapshot_id=sid, workspace=WS(tmp_path))
    assert r["cleanliness"]["score"] is None
    assert r["cleanliness"]["label"] == "not rated"
    assert "100/100" not in r["summary"] and "not enough data" in r["summary"]
    assert r["checks"]["unused_families_and_types"]["status"] == "not_enough_data"
    assert r["checks"]["in_place_families"]["status"] == "not_enough_data"
    assert "type list" in r["checks"]["in_place_families"]["missing"][0]
    for k in ("unused_families", "unused_types", "in_place_families", "families_with_very_many_types"):
        assert r[k]["status"] == "not_enough_data" and r[k]["total"] is None


def test_no_cad_records_is_unknown_unless_scan_declared(tmp_path):
    types = [_ty("t1", "Chair", "Std")]
    els = [_el(1, "Chair", "Std", "t1")]
    r = ModelBloatModule().audit(snapshot_id=_write(tmp_path, els, types), workspace=WS(tmp_path))
    assert r["checks"]["imported_cad"]["status"] == "not_enough_data"
    assert r["imported_cad"]["total"] is None and r["cleanliness"]["score"] is None
    assert r["checks"]["unused_families_and_types"]["status"] == "ran"
    r2 = ModelBloatModule().audit(snapshot_id=_write(tmp_path, els, types, "s2", cad_scanned=True),
                                  workspace=WS(tmp_path))
    assert r2["checks"]["imported_cad"]["status"] == "ran" and r2["cleanliness"]["score"] == 100
