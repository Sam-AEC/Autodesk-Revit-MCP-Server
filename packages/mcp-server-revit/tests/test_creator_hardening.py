"""The old create_* tools were hardened in place: type arguments are forwarded and the add-in picks safe defaults.

Source guards read the add-in C# text (no C# test project exists); mapping tests run the Python wrappers.
"""
import re
from pathlib import Path

import pytest
from revit_mcp_server.config import BridgeMode
from revit_mcp_server.providers import RevitProvider
from revit_mcp_server.security.workspace import WorkspaceMonitor

FACTORY = Path(__file__).resolve().parents[3] / "packages" / "revit-bridge-addin" / "src" / "Bridge" / "BridgeCommandFactory.cs"


@pytest.fixture
def mapping(tmp_path):
    provider = RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.mock)
    return {name: builder for name, (_, builder) in provider._tool_mapping.items()}


def _body(source: str, name: str) -> str:
    start = source.index(f"private static object {name}(")
    end = source.index("[BridgeCommand(", start)
    return source[start:end]


def test_wall_forwards_type_and_reverse_only_when_given(mapping):
    build = mapping["revit_create_wall"]
    base = {"start_x": 0, "start_y": 0, "end_x": 10, "end_y": 0}
    assert "wall_type" not in build(base) and "reverse" not in build(base)
    payload = build({**base, "wall_type": "Generic - 200mm", "reverse": True})
    assert payload["wall_type"] == "Generic - 200mm" and payload["reverse"] is True
    assert build({**base, "reverse": False})["reverse"] is False


def test_floor_and_roof_forward_types_and_slope(mapping):
    pts = [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 5}]
    assert mapping["revit_create_floor"]({"points": pts, "floor_type": "Slab 200"})["floor_type"] == "Slab 200"
    assert "floor_type" not in mapping["revit_create_floor"]({"points": pts})
    roof = mapping["revit_create_roof"]({"points": pts, "level": "L2", "roof_type": "Basic Roof", "slope": 0.4})
    assert roof["roof_type"] == "Basic Roof" and roof["slope"] == 0.4


def test_roof_has_no_hidden_default_slope(mapping):
    # The old wrapper sent slope 0.5 that the add-in never read; an omitted slope must stay omitted.
    assert "slope" not in mapping["revit_create_roof"]({"points": [], "level": "L2"})


def test_level_plan_view_is_on_unless_declined(mapping):
    build = mapping["revit_create_level"]
    assert "create_plan_view" not in build({"name": "L3", "elevation": 20})
    assert build({"name": "L3", "elevation": 20, "create_plan_view": False})["create_plan_view"] is False


def test_add_in_never_defaults_to_a_foundation_slab():
    source = FACTORY.read_text(encoding="utf-8")
    match = re.search(r"private static FloorType GetDefaultFloorType\(Document doc\)(.*?)\n    }\n", source, re.S)
    assert match and "IsFoundationSlab" in match.group(1)
    assert "FirstOrDefault();\n\n                if (defaultFloorType" not in source, "old first-floor-type default is back"


def test_creators_use_defaults_checks_and_plan_view():
    source = FACTORY.read_text(encoding="utf-8")
    wall = _body(source, "ExecuteCreateWall")
    assert "GetDefaultWallType(doc)" in wall and '"reverse"' in wall and "reverse, false)" in wall
    roof = _body(source, "ExecuteCreateRoof")
    assert "GetDefaultRoofType(doc)" in roof, "a null roof type was the cause of B-02"
    assert "set_DefinesSlope" in roof and "set_SlopeAngle" in roof
    level = _body(source, "ExecuteCreateLevel")
    assert "ViewPlan.Create(" in level and "CommitChecked" in level
