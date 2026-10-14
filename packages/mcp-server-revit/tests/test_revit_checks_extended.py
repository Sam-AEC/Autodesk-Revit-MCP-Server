"""Execute the retained QA scripts against a stub; this does not validate real Revit geometry."""
from __future__ import annotations

from typing import Any

import pytest

import revit_api_stub as stub
from test_revit_checks import FakeBridge, StubBridge, _load_module
from revit_mcp_server.security.read_mode import validate_read_script
from revit_mcp_server.security.workspace import WorkspaceMonitor


@pytest.fixture
def mod(monkeypatch: pytest.MonkeyPatch) -> Any:
    module = _load_module()
    monkeypatch.setattr(module, "_server_in_mock_mode", lambda: False)
    return module


@pytest.fixture
def ws(tmp_path: Any) -> WorkspaceMonitor:
    return WorkspaceMonitor([tmp_path])


@pytest.fixture
def revit_stub(monkeypatch: pytest.MonkeyPatch):
    with stub.installed(monkeypatch):
        yield

NEW_CALLS = [
    ("audit_openings", {"ids": [1]}),
    ("audit_roofs", {"ids": [1]}),
    ("probe_family", {"ids": [1]}),
    ("system_report", {"ids": [1]}),
    ("check_naming_and_params", {"ids": [1]}),
    ("check_levels_grids", {}),
]


@pytest.mark.parametrize("method,args", NEW_CALLS)
def test_generated_scripts_include_helpers_and_pass_read_mode(mod: Any, method: str, args: dict) -> None:
    bridge = FakeBridge("SUMMARY\tstub\nCOUNT\trow\t0")
    result = getattr(mod.RevitModule(), method)(**args, tool_executor=bridge)
    assert result["ok"] is True
    script = bridge.calls[0][1]["script"]
    assert "class Budget:" in script
    assert bridge.calls[0][1]["mode"] == "read"
    validate_read_script(script)


@pytest.mark.parametrize("method,args", NEW_CALLS[:5])
def test_empty_selection_is_a_structured_error(mod: Any, revit_stub: Any, method: str, args: dict) -> None:
    result = getattr(mod.RevitModule(), method)(**args, tool_executor=StubBridge(stub.Document()))
    assert result["ok"] is False and result["kind"] == "empty_selection"


@pytest.mark.parametrize("method", ["audit_openings", "audit_roofs", "probe_family", "system_report", "check_naming_and_params"])
def test_missing_scope_never_reaches_bridge(mod: Any, method: str) -> None:
    bridge = FakeBridge()
    result = getattr(mod.RevitModule(), method)(tool_executor=bridge)
    assert result["kind"] == "invalid_input"
    assert not bridge.calls


def opening_scene(cut: bool = False) -> tuple[stub.Document, stub.FamilyInstance]:
    wall = stub.Wall(1, (0, 0, 0), (20, 0, 0))
    door = stub.FamilyInstance(2, stub.Category(stub.BuiltInCategory.OST_Doors, "Doors"), (5, 0, 0), wall)
    door.set_param("door_width", 3.0, "Double").set_param("door_height", 7.0, "Double")
    door.bbox = stub.BoundingBox((3.5, -0.25, 0), (6.5, 0.25, 7))
    if cut:
        wall.cut_rects.append((3.5, 6.5, 0, 7))
    return stub.Document([wall, door, stub.View3D(3)]), door


def test_openings_distinguishes_cut_and_host_findings(mod: Any, revit_stub: Any) -> None:
    document, door = opening_scene()
    result = mod.RevitModule().audit_openings(ids=[2], swing=False, tool_executor=StubBridge(document))
    assert result["ok"] is True
    assert any(f.startswith("OPEN_NOT_CUT:") for f in result["fails"])
    document, door = opening_scene(cut=True)
    result = mod.RevitModule().audit_openings(ids=[2], swing=False, tool_executor=StubBridge(document))
    assert not any(f.startswith("OPEN_NOT_CUT:") for f in result["fails"])
    assert result["rows"][0]["cut"] == "cut"
    door.Host = None
    result = mod.RevitModule().audit_openings(ids=[2], tool_executor=StubBridge(document))
    assert any("HOST" in f for f in result["fails"])


def test_roof_missing_geometry_is_unverified(mod: Any, revit_stub: Any) -> None:
    level = stub.Level(1, "Roof", 10)
    roof = stub.RoofBase(2, level)
    roof.bbox = stub.BoundingBox((0, 0, 10), (20, 20, 11))
    result = mod.RevitModule().audit_roofs(ids=[2], tool_executor=StubBridge(stub.Document([level, roof])))
    assert result["ok"] is True and result["verified"] is False
    assert any(i.startswith("UNVERIFIED_ROOF_FACES:") for i in result["info"])
    roof.bbox = None
    result = mod.RevitModule().audit_roofs(ids=[2], tool_executor=StubBridge(stub.Document([level, roof])))
    assert result["verified"] is False and result["rows"] == []


def test_roof_measures_planar_slope(mod: Any, revit_stub: Any) -> None:
    roof = stub.RoofBase(2)
    roof.bbox = stub.BoundingBox((0, 0, 10), (20, 20, 11))
    roof.solids = [stub.Solid(100, [stub.PlanarFace(0.5, 400, [stub.rect_loop(0, 0, 20, 20, 11)])])]
    result = mod.RevitModule().audit_roofs(ids=[2], max_slope_deg=30, tool_executor=StubBridge(stub.Document([roof])))
    assert any(f.startswith("ROOF_SLOPE_STEEP:") for f in result["fails"])
    assert result["rows"][0]["max_slope_deg"] == pytest.approx(60, abs=0.1)


def test_family_probe_closes_document_and_reports_missing_connectors(mod: Any, revit_stub: Any) -> None:
    family = stub.Family(1, "Pump", stub.Category(stub.BuiltInCategory.OST_MechanicalEquipment, "Mechanical Equipment"))
    family.famdoc = stub.Document([stub.GenericForm(3, (0, 0, 0), (1, 1, 1))])
    project = stub.Document([family])
    result = mod.RevitModule().probe_family(ids=[1], tool_executor=StubBridge(project))
    assert project.edit_calls == 1 and family.famdoc.closed
    assert any(f.startswith("FAMILY_NO_CONNECTORS:") for f in result["fails"])
    family.famdoc = None
    result = mod.RevitModule().probe_family(ids=[1], tool_executor=StubBridge(project))
    assert result["verified"] is False
    assert any(i.startswith("UNVERIFIED_FAMILY_DOC:") for i in result["info"])


class WriteOnlyNameSymbol(stub.FamilySymbol):
    """Model the inherited write-only Name descriptor seen in Revit/IronPython."""

    @property
    def Name(self):
        raise AttributeError("Name")

    @Name.setter
    def Name(self, value):
        self.stored_name = value


@pytest.mark.parametrize("scope", [{"ids": [1]}, {"ids": [2]}, {"name": "1000 X 2000"}])
def test_family_probe_reads_symbol_parameter_without_name_descriptor(
    mod: Any, revit_stub: Any, monkeypatch: pytest.MonkeyPatch, scope: dict,
) -> None:
    monkeypatch.setattr(stub.BuiltInParameter, "SYMBOL_NAME_PARAM", "symbol_name", raising=False)
    family = stub.Family(1, "Door")
    symbol = WriteOnlyNameSymbol(2, "1000 x 2000", family)
    symbol.set_param("symbol_name", "1000 x 2000")
    project = stub.Document([family, symbol])
    bridge = StubBridge(project)
    result = mod.RevitModule().probe_family(**scope, deep=False, tool_executor=bridge)
    assert result["ok"] is True and result["fails"] == []
    assert next(r for r in result["rows"] if r["kind"] == "type")["name"] == "1000 x 2000"
    assert not any(i.startswith("UNVERIFIED_TYPE_NAME:") for i in result["info"])
    assert result["verified"] is False  # deep=false remains an incomplete probe
    assert project.edit_calls == 0
    assert bridge.calls[0][1]["mode"] == "read"
    validate_read_script(bridge.calls[0][1]["script"])


def test_family_probe_nested_symbol_uses_parameter_name(
    mod: Any, revit_stub: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stub.BuiltInParameter, "SYMBOL_NAME_PARAM", "symbol_name", raising=False)
    category = stub.Category(stub.BuiltInCategory.OST_GenericModel, "Generic Models")
    family = stub.Family(1, "Assembly", category)
    nested_family = stub.Family(3, "Part", category)
    symbol = WriteOnlyNameSymbol(4, "Part type", nested_family)
    symbol.set_param("symbol_name", "Part type")
    nested = stub.FamilyInstance(5, category, symbol=symbol)
    family.famdoc = stub.Document([nested_family, symbol, nested, stub.GenericForm(6, (0, 0, 0), (1, 1, 1))])
    result = mod.RevitModule().probe_family(ids=[1], allow_nested=True, tool_executor=StubBridge(stub.Document([family])))
    assert result["ok"] is True and result["verified"] is True and result["fails"] == []
    row = next(r for r in result["rows"] if r["kind"] == "nested")
    assert row["name"] == "Part : Part type" and row["category"] == "Generic Models"
    assert family.famdoc.closed


def test_family_probe_symbol_name_fallbacks_and_unreadable_name(
    mod: Any, revit_stub: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    family = stub.Family(1, "Door")
    symbol = stub.FamilySymbol(2, "Readable fallback", family)
    project = stub.Document([family, symbol])
    result = mod.RevitModule().probe_family(name="Readable fallback", deep=False, tool_executor=StubBridge(project))
    assert result["ok"] is True
    assert next(r for r in result["rows"] if r["kind"] == "type")["name"] == "Readable fallback"

    class BaseNameGetter:
        @staticmethod
        def GetValue(element):
            return element.stored_name

    from Autodesk.Revit import DB

    monkeypatch.setattr(DB, "Element", stub.Element, raising=False)
    monkeypatch.setattr(stub.Element, "Name", BaseNameGetter(), raising=False)
    family.symbols = []
    symbol = WriteOnlyNameSymbol(2, "Base getter fallback", family)
    project.elements = [family, symbol]
    result = mod.RevitModule().probe_family(name="Base getter fallback", deep=False, tool_executor=StubBridge(project))
    assert result["ok"] is True
    assert next(r for r in result["rows"] if r["kind"] == "type")["name"] == "Base getter fallback"
    monkeypatch.delattr(stub.Element, "Name")
    result = mod.RevitModule().probe_family(ids=[1], deep=False, tool_executor=StubBridge(project))
    assert result["ok"] is True and result["verified"] is False
    assert next(r for r in result["rows"] if r["kind"] == "type")["name"] == "?"
    assert any(i.startswith("UNVERIFIED_TYPE_NAME:") for i in result["info"])
    unmatched = mod.RevitModule().probe_family(name="?", deep=False, tool_executor=StubBridge(project))
    assert unmatched["kind"] == "empty_selection"


def test_family_probe_parameter_name_takes_priority_and_preserves_limits(
    mod: Any, revit_stub: Any, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stub.BuiltInParameter, "SYMBOL_NAME_PARAM", "symbol_name", raising=False)
    family = stub.Family(1, "Door")
    symbols = [stub.FamilySymbol(i, "Descriptor name", family) for i in range(2, 15)]
    for symbol in symbols:
        symbol.set_param("symbol_name", "Parameter name %d" % symbol.Id.Value)
    project = stub.Document([family] + symbols)
    result = mod.RevitModule().probe_family(ids=[1], deep=False, tool_executor=StubBridge(project))
    type_rows = [r for r in result["rows"] if r["kind"] == "type"]
    assert len(type_rows) == 12 and all(r["name"].startswith("Parameter name") for r in type_rows)
    assert result["limits"]["partial"] is True and result["verified"] is False
    monkeypatch.setattr(stub.Stopwatch, "tick", 20000)
    timed = mod.RevitModule().probe_family(ids=[1], deep=False, tool_executor=StubBridge(project))
    assert timed["limits"]["partial"] is True and timed["verified"] is False and timed["rows"] == []
    assert any("time_budget_s=18" in i for i in timed["info"])


def test_systems_report_open_ends_direction_size_and_islands(mod: Any, revit_stub: Any) -> None:
    system = stub.MepSystem("Heating")
    cat = stub.Category(stub.BuiltInCategory.OST_PipeCurves, "Pipes")
    a = stub.Connector(radius_ft=0.1, direction="Out", system=system)
    b = stub.Connector(radius_ft=0.2, direction="Out", system=system)
    pipes = [stub.MEPCurve(1, cat, [a], system), stub.MEPCurve(2, cat, [b], system),
             stub.MEPCurve(3, cat, [stub.Connector(system=system)], system)]
    a.connect(b)
    result = mod.RevitModule().system_report(ids=[1, 2, 3], tool_executor=StubBridge(stub.Document(pipes)))
    for code in ("SYS_OPEN_END:", "SYS_FLOW_MISMATCH:", "SYS_SIZE_MISMATCH:", "SYS_ISLAND"):
        assert any(f.startswith(code) for f in result["fails"]), result
    waived = mod.RevitModule().system_report(ids=[1, 2, 3], allow_open_ids=[3], tool_executor=StubBridge(stub.Document(pipes)))
    assert not any(f.startswith("SYS_OPEN_END:") for f in waived["fails"])


def test_naming_reports_missing_empty_duplicate_and_bad_regex(mod: Any, revit_stub: Any) -> None:
    cat = stub.Category(stub.BuiltInCategory.OST_Doors, "Doors")
    a, b = stub.Element(1, cat), stub.Element(2, cat)
    a.set_param("mark", "D1").set_param("description", "")
    b.set_param("mark", "D1")
    bridge = StubBridge(stub.Document([a, b]))
    result = mod.RevitModule().check_naming_and_params(ids=[1, 2], required=["Description"], name_pattern="^Door", tool_executor=bridge)
    for code in ("PARAM_MISSING:", "PARAM_EMPTY:", "PARAM_DUPLICATE:", "NAME_PATTERN:"):
        assert any(f.startswith(code) for f in result["fails"])
    assert mod.RevitModule().check_naming_and_params(ids=[1], name_pattern="[", tool_executor=bridge)["kind"] == "invalid_input"


def test_levels_reports_duplicates_missing_plans_and_grid_overlap(mod: Any, revit_stub: Any) -> None:
    levels = [stub.Level(1, "A", 0), stub.Level(2, "B", 0.01)]
    grids = [stub.Grid(4, "1", (0, 0, 0), (10, 0, 0)), stub.Grid(5, "2", (10, 0, 0), (0, 0, 0))]
    result = mod.RevitModule().check_levels_grids(tool_executor=StubBridge(stub.Document(levels + grids + [stub.ViewPlan(3, "A", levels[0])])))
    for code in ("LEVEL_NO_PLAN:", "LEVEL_DUPLICATE:", "GRID_DUPLICATE:"):
        assert any(f.startswith(code) for f in result["fails"])


@pytest.mark.parametrize("method,args", NEW_CALLS)
def test_mock_never_claims_verification(mod: Any, monkeypatch: Any, method: str, args: dict) -> None:
    monkeypatch.setattr(mod, "_server_in_mock_mode", lambda: True)
    result = getattr(mod.RevitModule(), method)(**args)
    assert result["mock"] is True and result["verified"] is False


def test_review_distinguishes_fail_incomplete_and_empty_scope(mod: Any, revit_stub: Any) -> None:
    result = mod.RevitModule().review(checks=["joins", "warnings"], tool_executor=StubBridge(stub.Document()))
    assert result["verdict"] == "INCOMPLETE" and result["verified"] is False
    result = mod.RevitModule().review(ids=[1], checks=["roofs"], tool_executor=StubBridge(stub.Document()))
    assert result["verdict"] == "INCOMPLETE" and result["skipped"]
    document, _ = opening_scene()
    result = mod.RevitModule().review(ids=[2], checks=["openings"], tool_executor=StubBridge(document))
    assert result["verdict"] == "FAIL" and result["fails_total"] > 0
    assert result["verified"] is False  # no plan view to measure swing


def test_review_does_not_call_an_incomplete_check_a_pass(mod: Any, revit_stub: Any) -> None:
    roof = stub.RoofBase(1)
    result = mod.RevitModule().review(ids=[1], checks=["roofs"], tool_executor=StubBridge(stub.Document([roof])))
    assert result["verdict"] == "INCOMPLETE"
    assert result["checks"][0]["status"] == "not_verified"


def test_review_reports_script_failure_and_mock(mod: Any, revit_stub: Any, monkeypatch: Any) -> None:
    class BrokenLevel(stub.Level):
        @property
        def Elevation(self):
            raise RuntimeError("broken elevation")

        @Elevation.setter
        def Elevation(self, value):
            pass

    result = mod.RevitModule().review(checks=["levels_grids"], tool_executor=StubBridge(stub.Document([BrokenLevel(1, "A", 0)])))
    assert result["verdict"] == "INCOMPLETE" and "broken elevation" in result["not_verified"][0]
    monkeypatch.setattr(mod, "_server_in_mock_mode", lambda: True)
    result = mod.RevitModule().review(checks=["levels_grids"])
    assert result["mock"] is True and result["verified"] is False


def test_levels_cap_and_zero_tolerance_are_truthful(mod: Any, revit_stub: Any) -> None:
    levels = [stub.Level(1, "A", 0), stub.Level(2, "B", 0.001)]
    document = stub.Document(levels)
    capped = mod.RevitModule().check_levels_grids(max_elements=1, tool_executor=StubBridge(document))
    assert capped["limits"]["partial"] is True and capped["verified"] is False
    assert len(capped["rows"]) == 1
    exact = mod.RevitModule().check_levels_grids(tolerance_mm=0, tool_executor=StubBridge(document))
    assert not any(f.startswith("LEVEL_DUPLICATE:") for f in exact["fails"])
    empty = mod.RevitModule().check_levels_grids(tool_executor=StubBridge(stub.Document()))
    assert empty["verified"] is False


def test_time_budget_is_incomplete_and_review_can_pass_a_measured_check(mod: Any, revit_stub: Any) -> None:
    element = stub.Element(1, stub.Category(stub.BuiltInCategory.OST_Doors, "Doors"))
    element.set_param("mark", "D1")
    stub.Stopwatch.tick = 20000
    partial = mod.RevitModule().check_naming_and_params(ids=[1], time_budget_s=1, tool_executor=StubBridge(stub.Document([element])))
    assert partial["limits"]["partial"] is True and partial["verified"] is False
    stub.Stopwatch.tick = 0
    clean = mod.RevitModule().review(ids=[1], checks=["naming_params"], tool_executor=StubBridge(stub.Document([element])))
    assert clean["verdict"] == "PASS" and clean["verified"] is True


def test_family_caps_and_close_errors_prevent_full_verification(mod: Any, revit_stub: Any) -> None:
    class Unclosable(stub.Document):
        def Close(self, save):
            raise RuntimeError("close failed")

    family = stub.Family(1, "Pump")
    family.famdoc = Unclosable([stub.GenericForm(3, (0, 0, 0), (1, 1, 1))])
    project = stub.Document([family])
    result = mod.RevitModule().probe_family(ids=[1], tool_executor=StubBridge(project))
    assert result["verified"] is False
    assert any(i.startswith("UNVERIFIED_FAMILY_CLOSE:") for i in result["info"])
    family.Name = "Pump A"
    other = stub.Family(2, "Pump B")
    result = mod.RevitModule().probe_family(name="Pump", max_families=1, deep=False, tool_executor=StubBridge(stub.Document([family, other])))
    assert result["limits"]["partial"] is True and result["verified"] is False


def test_systems_without_readable_connectors_are_incomplete(mod: Any, revit_stub: Any) -> None:
    cat = stub.Category(stub.BuiltInCategory.OST_PipeCurves, "Pipes")
    pipe = stub.MEPCurve(1, cat, [stub.Connector()])
    unreadable = stub.Element(2, cat)
    result = mod.RevitModule().system_report(ids=[1, 2], tool_executor=StubBridge(stub.Document([pipe, unreadable])))
    assert result["verified"] is False
    assert any(i.startswith("NO_CONNECTORS:") for i in result["info"])


def test_new_tools_are_registered_as_read_only(ws: Any) -> None:
    from revit_mcp_server.registry_factory import build_registry

    registry, _approval, _jobs, _modules, _workspace = build_registry(ws)
    tools = {t.name: t for t in registry.get_all_tools()}
    for method, _args in NEW_CALLS + [("review", {})]:
        tool = tools["revit_" + method]
        assert tool.is_mutating is False
        assert "plan_id" not in tool.input_schema.get("properties", {})
