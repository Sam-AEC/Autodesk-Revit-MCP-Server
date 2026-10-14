from pathlib import Path

import ifcopenshell
import pytest
from revit_mcp_server.config import BridgeMode
from revit_mcp_server.errors import BridgeError
from revit_mcp_server.providers import FakeProvider, IfcProvider, ProviderRegistry, RevitProvider
from revit_mcp_server.security.workspace import WorkspaceMonitor


def create_sample_ifc(path: Path):
    """Programmatically generate a minimal valid IFC2X3 file for testing."""
    file = ifcopenshell.file(schema="IFC2X3")

    project = file.create_entity("IfcProject", GlobalId="0000000000000000000001", Name="Test Project")
    site = file.create_entity(
        "IfcSite",
        GlobalId="0000000000000000000002",
        Name="Test Site",
        RefLatitude=(52, 30, 0, 0),
        RefLongitude=(4, 45, 0, 0),
        RefElevation=10.0,
    )
    building = file.create_entity("IfcBuilding", GlobalId="0000000000000000000003", Name="Test Building")
    storey = file.create_entity("IfcBuildingStorey", GlobalId="0000000000000000000004", Name="Test Storey")

    file.create_entity(
        "IfcRelAggregates", GlobalId="0000000000000000000005", RelatingObject=project, RelatedObjects=[site]
    )
    file.create_entity(
        "IfcRelAggregates", GlobalId="0000000000000000000006", RelatingObject=site, RelatedObjects=[building]
    )
    file.create_entity(
        "IfcRelAggregates", GlobalId="0000000000000000000007", RelatingObject=building, RelatedObjects=[storey]
    )

    # Create a wall
    wall = file.create_entity("IfcWall", GlobalId="0x1234567890abcdef123456", Name="Sample Wall")
    file.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId="0000000000000000000008",
        RelatingStructure=storey,
        RelatedElements=[wall],
    )

    # Add some properties to the wall
    pset = file.create_entity("IfcPropertySet", GlobalId="0000000000000000000009", Name="Pset_WallCommon")
    prop = file.create_entity(
        "IfcPropertySingleValue", Name="LoadBearing", NominalValue=file.create_entity("IfcBoolean", True)
    )
    pset.HasProperties = [prop]
    file.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId="0000000000000000000010",
        RelatedObjects=[wall],
        RelatingPropertyDefinition=pset,
    )

    file.write(str(path))


def test_provider_registry():
    registry = ProviderRegistry()
    fake = FakeProvider()
    registry.register(fake)

    assert registry.get_provider("fake") is fake
    assert len(registry.get_all_providers()) == 1
    assert len(registry.get_all_tools()) == 1
    assert registry.get_all_tools()[0].name == "fake_tool"

    provider = registry.lookup_tool_provider("fake_tool")
    assert provider is fake


@pytest.mark.anyio
async def test_revit_provider_mock_mode(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    provider = RevitProvider(workspace=workspace, mode=BridgeMode.mock)

    health = await provider.check_health()
    assert health["status"] == "healthy"

    capabilities = provider.get_capabilities()
    assert len(capabilities) >= 100

    # Verify execution of legacy dot notation
    res1 = await provider.execute_tool("revit.health", {"request_id": "test-1"})
    assert res1["status"] == "healthy"

    # Verify execution of underscore notation
    res2 = await provider.execute_tool("revit_health", {"request_id": "test-2"})
    assert res2["status"] == "healthy"


def test_revit_wall_placement_preserves_nested_location_z(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    provider = RevitProvider(workspace=workspace, mode=BridgeMode.mock)

    for tool_name in ("revit_place_window", "revit_place_door"):
        _, build_payload = provider._tool_mapping[tool_name]
        payload = build_payload(
            {
                "wall_id": 1245580,
                "family_name": "Window-Double-Hung",
                "type_name": '26" x 42"',
                "location": {"x": -25.0, "y": -50.0, "z": 33.0},
            }
        )

        assert payload["location"] == {"x": -25.0, "y": -50.0, "z": 33.0}


def test_revit_wall_placement_keeps_flat_coordinates_compatible(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    provider = RevitProvider(workspace=workspace, mode=BridgeMode.mock)

    _, build_payload = provider._tool_mapping["revit_place_window"]
    payload = build_payload({"wall_id": 1245580, "x": 1.0, "y": 2.0, "z": 3.0})

    assert payload["location"] == {"x": 1.0, "y": 2.0, "z": 3.0}


def test_revit_select_by_unique_ids_is_registered_and_not_mutating(tmp_path):
    """The panel selects a flagged element by its stable UniqueId (not the
    session-scoped integer ElementId revit_set_selection expects), and must
    never require an approved plan just to change what's on screen."""
    workspace = WorkspaceMonitor([tmp_path])
    provider = RevitProvider(workspace=workspace, mode=BridgeMode.mock)

    tools = {tool.name: tool for tool in provider.get_capabilities()}
    assert "revit_select_by_unique_ids" in tools
    assert tools["revit_select_by_unique_ids"].is_mutating is False


@pytest.mark.anyio
async def test_revit_select_by_unique_ids_passes_uids_through(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    provider = RevitProvider(workspace=workspace, mode=BridgeMode.mock)

    result = await provider.execute_tool(
        "revit_select_by_unique_ids", {"element_uids": ["abc-123", "def-456"]}
    )

    assert result["tool"] == "revit.select_by_unique_ids"
    assert result["payload"]["element_uids"] == ["abc-123", "def-456"]


def test_revit_provider_explicit_bridge_url_takes_precedence(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    calls = []

    class DummyBridge:
        def initialize(self):
            calls.append(("initialize", None))

    provider = RevitProvider(
        workspace=workspace,
        mode=BridgeMode.bridge,
        bridge_url="http://bridge",
        host_version="2024",
        bridge_factory=lambda url, token=None: calls.append((url, token)) or DummyBridge(),
    )

    assert provider.bridge_url == "http://bridge"
    assert calls[0] == ("http://bridge", None)


@pytest.mark.anyio
async def test_revit_provider_missing_requested_host_version_reports_available(tmp_path, monkeypatch):
    workspace = WorkspaceMonitor([tmp_path])

    monkeypatch.setattr("revit_mcp_server.bridge.discovery.select_switch", lambda provider_id, host_version, **_k: None)
    monkeypatch.setattr("revit_mcp_server.bridge.discovery.available_host_versions", lambda provider_id, **_k: ["2024", "2026"])

    provider = RevitProvider(workspace=workspace, mode=BridgeMode.bridge, host_version="2025")
    health = await provider.check_health()

    assert health["status"] == "unhealthy"
    assert "No live Revit 2025 bridge found" in health["error"]
    assert "2024, 2026" in health["error"]

    with pytest.raises(BridgeError, match="No live Revit 2025 bridge found"):
        await provider.execute_tool("revit_health", {})


@pytest.mark.anyio
async def test_ifc_provider_tools(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    provider = IfcProvider(workspace=workspace)

    # Generate fixture file
    ifc_file_path = tmp_path / "model.ifc"
    create_sample_ifc(ifc_file_path)

    # Health
    health = await provider.execute_tool("ifc_health", {})
    assert health["status"] == "healthy"

    # Metadata
    meta = await provider.execute_tool("ifc_get_metadata", {"ifc_path": str(ifc_file_path)})
    assert meta["schema"] == "IFC2X3"
    assert meta["project_name"] == "Test Project"
    assert "georeferencing" in meta
    assert meta["georeferencing"]["latitude"] is not None

    # Spatial structure
    spatial = await provider.execute_tool("ifc_get_spatial_structure", {"ifc_path": str(ifc_file_path)})
    struct = spatial["spatial_structure"]
    assert struct["name"] == "Test Project"
    assert len(struct["children"]) == 1  # Site
    assert struct["children"][0]["name"] == "Test Site"

    # Query elements
    query = await provider.execute_tool("ifc_query_elements", {"ifc_path": str(ifc_file_path), "ifc_class": "IfcWall"})
    elements = query["elements"]
    assert len(elements) == 1
    assert elements[0]["name"] == "Sample Wall"
    assert elements[0]["guid"] == "0x1234567890abcdef123456"

    # Properties
    props = await provider.execute_tool(
        "ifc_get_properties", {"ifc_path": str(ifc_file_path), "element_id": "0x1234567890abcdef123456"}
    )
    assert "property_sets" in props
    assert "Pset_WallCommon" in props["property_sets"]
    assert props["property_sets"]["Pset_WallCommon"]["LoadBearing"] is True

    # Bounding Box
    bbox = await provider.execute_tool(
        "ifc_get_bounding_box", {"ifc_path": str(ifc_file_path), "element_id": "0x1234567890abcdef123456"}
    )
    assert "element" in bbox

    # Validation
    val = await provider.execute_tool("ifc_validate", {"ifc_path": str(ifc_file_path)})
    assert "is_valid" in val


@pytest.mark.anyio
async def test_ifc_provider_path_traversal_protection(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    provider = IfcProvider(workspace=workspace)

    # File outside workspace
    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    outside_file = outside_dir / "unauthorized.ifc"

    with pytest.raises(Exception) as exc:
        await provider.execute_tool("ifc_get_metadata", {"ifc_path": str(outside_file)})

    # Pydantic or WorkspaceMonitor raises ValueError or related custom errors for paths outside workspace
    assert "outside the allowed workspace" in str(exc.value).lower()


def test_revit_preview_tools_registered_and_not_mutating(tmp_path):
    from revit_mcp_server.tool_metadata import DESCRIPTIONS

    provider = RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.mock)
    tools = {tool.name: tool for tool in provider.get_capabilities()}
    for name in ("revit_preview_elements", "revit_clear_preview"):
        assert name in tools
        assert tools[name].is_mutating is False
        assert len(DESCRIPTIONS[name]) >= 40


@pytest.mark.anyio
async def test_revit_preview_elements_maps_arguments(tmp_path):
    provider = RevitProvider(workspace=WorkspaceMonitor([tmp_path]), mode=BridgeMode.mock)

    result = await provider.execute_tool(
        "revit_preview_elements", {"element_uids": ["u1"], "element_ids": [7], "isolate": False}
    )
    assert result["tool"] == "revit.preview_elements"
    assert result["payload"] == {"element_uids": ["u1"], "element_ids": [7], "isolate": False}

    default = await provider.execute_tool("revit_preview_elements", {"element_uids": ["u1"]})
    assert default["payload"]["isolate"] is True
    assert default["payload"]["element_ids"] == []

    cleared = await provider.execute_tool("revit_clear_preview", {})
    assert cleared["tool"] == "revit.clear_preview"
    assert cleared["payload"] == {}


def test_revit_opening_tools_forward_swing_flips(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    provider = RevitProvider(workspace=workspace, mode=BridgeMode.mock)

    for tool_name in ("revit_place_window", "revit_place_door"):
        _, build_payload = provider._tool_mapping[tool_name]
        payload = build_payload({"wall_id": 7, "x": 1, "y": 2, "hand_flipped": True, "facing_flipped": False})
        assert payload["hand_flipped"] is True
        assert payload["facing_flipped"] is False
        # Omitted flips stay None so the add-in leaves the family default alone.
        bare = build_payload({"wall_id": 7, "x": 1, "y": 2})
        assert bare["hand_flipped"] is None and bare["facing_flipped"] is None
        assert bare["family_name"] is None and bare["type_name"] is None


def test_revit_opening_and_clash_schemas_describe_new_inputs(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    provider = RevitProvider(workspace=workspace, mode=BridgeMode.mock)
    tools = {tool.name: tool for tool in provider.get_capabilities()}

    for name in ("revit_place_door", "revit_place_window"):
        props = tools[name].input_schema["properties"]
        assert props["hand_flipped"]["type"] == "boolean"
        assert props["facing_flipped"]["type"] == "boolean"
        assert "first loaded" in props["family_name"]["description"]

    props = tools["revit_check_clashes"].input_schema["properties"]
    assert props["max_pairs"]["default"] == 200000
    assert props["time_budget_s"]["default"] == 20
    assert "feet" in props["tolerance"]["description"]


def test_revit_check_clashes_forwards_budget(tmp_path):
    workspace = WorkspaceMonitor([tmp_path])
    provider = RevitProvider(workspace=workspace, mode=BridgeMode.mock)
    _, build_payload = provider._tool_mapping["revit_check_clashes"]

    default = build_payload({"category1": "walls", "category2": "doors"})
    assert default["max_pairs"] == 200000 and default["time_budget_s"] == 20

    custom = build_payload({"category1": "walls", "category2": "doors", "max_pairs": 500, "time_budget_s": 3.5})
    assert custom["max_pairs"] == 500 and custom["time_budget_s"] == 3.5
