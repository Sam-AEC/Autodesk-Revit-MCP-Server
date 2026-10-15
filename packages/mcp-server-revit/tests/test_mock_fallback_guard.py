"""Mock-data fallback guard for selection_tools, model_inspector, familytype_mapper."""
import importlib.util
from pathlib import Path

import pytest

from revit_mcp_server.config import BridgeMode, config

_ROOT = Path(__file__).parent.parent / "src/revit_mcp_server/modules"


def _load(name: str, cls: str):
    spec = importlib.util.spec_from_file_location(f"_{name}_guard", _ROOT / name / "module.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, cls)()


class WS:
    def __init__(self, p):
        self.allowed_directories = [p]


@pytest.fixture
def ws(tmp_path):
    return WS(tmp_path)


CALLS = [
    ("selection_tools", "SelectionToolsModule", "select_by_query", {"filter": {"category": "OST_Doors"}}),
    ("selection_tools", "SelectionToolsModule", "_find_group", {"group_uid": "g1"}),
    ("model_inspector", "ModelInspectorModule", "summarize_model", {}),
    ("model_inspector", "ModelInspectorModule", "ask", {"filter": {"category": "OST_Doors"}}),
    ("model_inspector", "ModelInspectorModule", "list_groups", {}),
    ("model_inspector", "ModelInspectorModule", "inspect_selection", {"element_uids": ["x"]}),
    ("familytype_mapper", "FamilytypeMapperModule", "audit_families", {}),
    ("familytype_mapper", "FamilytypeMapperModule", "list_type_mappings", {}),
]
IDS = [f"{c[0]}.{c[2]}" for c in CALLS]


@pytest.mark.parametrize("mod,cls,method,kwargs", CALLS, ids=IDS)
def test_bridge_mode_without_snapshot_raises(mod, cls, method, kwargs, ws, monkeypatch):
    monkeypatch.setattr(config, "mode", BridgeMode.bridge)
    with pytest.raises(ValueError, match="requires a snapshot_id"):
        getattr(_load(mod, cls), method)(snapshot_id="", workspace=ws, **kwargs)


@pytest.mark.parametrize("mod,cls,method,kwargs", CALLS, ids=IDS)
def test_mock_mode_without_snapshot_works_and_is_labelled(mod, cls, method, kwargs, ws, monkeypatch):
    monkeypatch.setattr(config, "mode", BridgeMode.mock)
    out = getattr(_load(mod, cls), method)(snapshot_id="", workspace=ws, **kwargs)
    assert out["data_source"] == "mock"
