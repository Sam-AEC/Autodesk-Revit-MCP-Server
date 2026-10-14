"""revit_ifc_check: the IFC half against real ifcopenshell (tiny files made here), the Revit half against the Revit API
stub (tests/revit_api_stub.py), and the wiring through the real ModuleProvider and approval gate.

The stub proves the script's control flow and line protocol, not that Revit answers the same way: that is UNVERIFIED.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import ifcopenshell
import ifcopenshell.guid
import pytest

import revit_api_stub as stub
from revit_mcp_server.module_registry import ModuleInstance, ModuleManifest
from revit_mcp_server.modules.revit_ifc import module as ifcmod
from revit_mcp_server.providers.module_provider import ModuleProvider
from revit_mcp_server.security.approval import ApprovalGate
from revit_mcp_server.security.dispatch import run_gated_tool
from revit_mcp_server.security.read_mode import validate_read_script
from revit_mcp_server.security.workspace import WorkspaceMonitor

BIC = stub.BuiltInCategory
EPISODE = "0b5c0a8e-6c1e-4b2a-9d3f-1a2b3c4d5e6f"


def uid_of(element_id: int) -> str:
    return "%s-%08x" % (EPISODE, element_id)


# --------------------------------------------------------------------------- #
# A tiny IFC4 file
# --------------------------------------------------------------------------- #
class IfcBuilder:
    def __init__(self, schema: str = "IFC4", millimetres: bool = True) -> None:
        self.f = ifcopenshell.file(schema=schema)
        f = self.f
        unit = f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Prefix="MILLI" if millimetres else None, Name="METRE")
        self.scale = 1000.0 if millimetres else 1.0
        ctx = f.create_entity("IfcGeometricRepresentationContext", ContextType="Model", CoordinateSpaceDimension=3, Precision=1e-5,
                              WorldCoordinateSystem=self.axis((0, 0, 0)))
        self.project = f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="P",
                                       UnitsInContext=f.create_entity("IfcUnitAssignment", Units=[unit]), RepresentationContexts=[ctx])
        self.site = f.create_entity("IfcSite", GlobalId=ifcopenshell.guid.new(), Name="Site", ObjectPlacement=self.place((100.0, 200.0, 0.0)))
        self.building = f.create_entity("IfcBuilding", GlobalId=ifcopenshell.guid.new(), Name="B", ObjectPlacement=self.place((0, 0, 0)))
        self.aggregate(self.project, [self.site])
        self.aggregate(self.site, [self.building])
        self.storeys: Dict[str, Any] = {}
        self.nlsfb = f.create_entity("IfcClassification", Name="NL-SfB")
        self.concrete = f.create_entity("IfcMaterial", Name="Concrete")

    def axis(self, xyz):
        return self.f.create_entity("IfcAxis2Placement3D", Location=self.f.create_entity("IfcCartesianPoint", Coordinates=[float(v) for v in xyz]))

    def place(self, xyz_m):
        return self.f.create_entity("IfcLocalPlacement", RelativePlacement=self.axis([v * self.scale for v in xyz_m]))

    def aggregate(self, whole, parts):
        self.f.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=whole, RelatedObjects=parts)

    def storey(self, name: str, elevation_m: float):
        s = self.f.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name=name, Elevation=elevation_m * self.scale,
                                 ObjectPlacement=self.place((0, 0, elevation_m)))
        self.aggregate(self.building, [s])
        self.storeys[name] = s
        return s

    def element(self, cls: str, *, guid: Optional[str] = None, tag: Optional[str] = None, storey: Optional[str] = None, at=(0.0, 0.0, 0.0),
                code: Optional[str] = None, material: bool = True, props: Optional[Dict[str, Any]] = None, name: str = "E"):
        f = self.f
        el = f.create_entity(cls, GlobalId=guid or ifcopenshell.guid.new(), Name=name, Tag=tag, ObjectPlacement=self.place(at))
        if storey:
            f.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(), RelatingStructure=self.storeys[storey], RelatedElements=[el])
        if code:
            key = "ItemReference" if f.schema == "IFC2X3" else "Identification"
            ref = f.create_entity("IfcClassificationReference", ReferencedSource=self.nlsfb, **{key: code})
            f.create_entity("IfcRelAssociatesClassification", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[el], RelatingClassification=ref)
        if material:
            f.create_entity("IfcRelAssociatesMaterial", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[el], RelatingMaterial=self.concrete)
        if props:
            values = []
            for k, v in props.items():
                nominal = f.create_entity("IfcLabel", str(v)) if isinstance(v, str) else f.create_entity("IfcReal", float(v))
                values.append(f.create_entity("IfcPropertySingleValue", Name=k, NominalValue=nominal))
            pset = f.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name="Pset_Common", HasProperties=values)
            f.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(), RelatedObjects=[el], RelatingPropertyDefinition=pset)
        return el

    def write(self, path: Path) -> Path:
        self.f.write(str(path))
        return path


def full_ifc(path: Path) -> Path:
    b = IfcBuilder()
    b.storey("L0", 0.0)
    b.storey("L1", 3.0)
    b.element("IfcWall", tag="101", storey="L0", code="21.12", props={"FireRating": "60"})
    # matched through the GlobalId derived from the UniqueId (no Tag); the export dropped its material
    b.element("IfcWall", guid=ifcmod.ifc_guid_from_unique_id(uid_of(102)), storey="L0", at=(5, 0, 0), code="21.12", material=False)
    # the floor sits on L0 in the IFC but on L1 in Revit, and its FireRating changed
    b.element("IfcSlab", tag="301", storey="L0", at=(0, 0, 3), code="23.11", props={"FireRating": "30"})
    return b.write(path)


# --------------------------------------------------------------------------- #
# The Revit side on the stub
# --------------------------------------------------------------------------- #
class El(stub.Element):
    def __init__(self, eid: int, cat, level=None, materials=(), comments: str = "") -> None:
        super().__init__(eid, cat, comments)
        self.UniqueId = uid_of(eid)
        self.LevelId = stub.ElementId(level.Id.Value) if level is not None else stub.ElementId(-1)
        self._materials = list(materials)

    def GetMaterialIds(self, paint: bool):
        return [stub.ElementId(m.Id.Value) for m in self._materials]


class Point:
    def __init__(self, internal, shared) -> None:
        self.Position, self.SharedPosition = stub.XYZ(*internal), stub.XYZ(*shared)


class BasePoint:
    @staticmethod
    def GetSurveyPoint(doc):
        return Point((0, 0, 0), (0, 0, 0))

    @staticmethod
    def GetProjectBasePoint(doc):
        return Point((0, 0, 0), (10 / 0.3048, 0, 0))


def model(with_door: bool = True, with_excluded: bool = True):
    walls, floors, doors = stub.Category(BIC.OST_Walls, "Walls"), stub.Category(BIC.OST_Floors, "Floors"), stub.Category(BIC.OST_Doors, "Doors")
    l0, l1 = stub.Level(1, "L0", 0.0), stub.Level(2, "L1", 10.0)
    concrete = stub.Element(900, None)
    concrete.Name = "Concrete"
    wtype = stub.Element(800, None)
    wtype.is_type = True
    wtype.named["Assembly Code"] = stub._Param("21.12")
    w1 = El(101, walls, l0, [concrete])
    w1.type_el = wtype
    w1.named["FireRating"] = stub._Param("60")
    w2 = El(102, walls, l0, [concrete])
    w2.type_el = wtype
    w2.named["FireRating"] = stub._Param("60")
    fl = El(301, floors, l1, [concrete])
    fl.named["FireRating"] = stub._Param("60")
    elements = [l0, l1, concrete, wtype, w1, w2, fl]
    if with_door:
        elements.append(El(201, doors, l0))
    if with_excluded:
        ex = El(202, doors, l0)
        ex.named["IfcExportAs"] = stub._Param("DontExport")
        elements.append(ex)
    return stub.Document(elements)


class StubBridge:
    def __init__(self, document) -> None:
        self.document, self.calls = document, []

    def __call__(self, name: str, args: Dict[str, Any]) -> Any:
        self.calls.append((name, args))
        assert name == "revit_execute_python"
        return {"success": True, "output": stub.run_script(args["script"], self.document), "error": ""}


@pytest.fixture()
def revit(monkeypatch):
    monkeypatch.setattr(ifcmod, "_server_in_mock_mode", lambda: False)
    with stub.installed(monkeypatch):
        monkeypatch.setattr(sys.modules["Autodesk.Revit.DB"], "BasePoint", BasePoint, raising=False)
        yield


@pytest.fixture()
def ws(tmp_path):
    return WorkspaceMonitor([tmp_path])


def check(ws, bridge=None, **args):
    return ifcmod.RevitIfcModule().check(workspace=ws, tool_executor=bridge, **args)


def problems(result) -> List[tuple]:
    return sorted((r.get("id"), r["problem"]) for r in result["rows"])


# --------------------------------------------------------------------------- #
# Join: IFC vs model
# --------------------------------------------------------------------------- #
def test_join_reports_what_the_export_dropped(revit, ws, tmp_path):
    path = full_ifc(tmp_path / "out.ifc")
    bridge = StubBridge(model())
    result = check(ws, bridge, path=str(path), expect_parameters=["FireRating"], limit=500)
    assert result["ok"] is True, result
    assert result["verdict"] == "FAIL" and result["verified"] is True
    assert problems(result) == sorted([
        (201, "not_exported"),
        (102, "no_material"),
        (102, "param_missing"),
        (301, "storey_mismatch"),
        (301, "param_mismatch"),
    ])
    walls, floors, doors = (result["per_category"][k] for k in ("Walls", "Floors", "Doors"))
    assert (walls["model"], walls["exported"], walls["no_material"]) == (2, 2, 1)
    assert (doors["model"], doors["missing"], doors["excluded"]) == (1, 1, 1)
    assert floors["storey_mismatch"] == 1 and floors["param_mismatch"] == 1
    assert result["join"]["matched_by_tag"] == 2 and result["join"]["matched_by_guid"] == 1
    material_row = next(r for r in result["rows"] if r["problem"] == "no_material")
    assert "Concrete" in material_row["detail"]
    assert any(f.startswith("NOT_EXPORTED: Doors: 1") for f in result["fails"])
    assert any(i.startswith("EXCLUDED: 1") for i in result["info"])
    # origin: IFC site at (100, 200, 0) m, survey point at shared (0, 0, 0)
    assert result["origin"]["offset_to_survey_point_m"] == [100.0, 200.0, 0.0]
    assert result["ifc"]["schema"] == "IFC4" and [s["name"] for s in result["ifc"]["storeys"]] == ["L0", "L1"]
    assert result["ifc"]["storeys"][1]["elevation_m"] == 3.0
    assert result["ifc"]["by_class"] == {"IfcSlab": 1, "IfcWall": 2}
    assert [c[1]["mode"] for c in bridge.calls] == ["read"]


def test_clean_export_passes(revit, ws, tmp_path):
    b = IfcBuilder()
    b.storey("L0", 0.0)
    b.element("IfcWall", tag="101", storey="L0", code="21.12")
    path = b.write(tmp_path / "clean.ifc")
    walls = stub.Category(BIC.OST_Walls, "Walls")
    l0 = stub.Level(1, "L0", 0.0)
    doc = stub.Document([l0, El(101, walls, l0)])
    result = check(ws, StubBridge(doc), path=str(path), categories=["Walls"])
    assert result["verdict"] == "PASS" and result["verified"] is True, result
    assert result["fails"] == [] and result["limits"]["partial"] is False


def test_truncated_revit_side_is_never_pass(revit, ws, tmp_path):
    b = IfcBuilder()
    b.storey("L0", 0.0)
    for i in (101, 102):
        b.element("IfcWall", tag=str(i), storey="L0", code="21.12", at=(i, 0, 0))
    path = b.write(tmp_path / "t.ifc")
    walls, l0 = stub.Category(BIC.OST_Walls, "Walls"), stub.Level(1, "L0", 0.0)
    doc = stub.Document([l0, El(101, walls, l0), El(102, walls, l0)])
    result = check(ws, StubBridge(doc), path=str(path), categories=["Walls"], max_elements=1)
    assert result["truncated"] is True and result["limits"]["partial"] is True
    assert result["verdict"] == "UNVERIFIED" and result["verified"] is False
    assert any(i.startswith("TRUNCATED") for i in result["info"])


def test_time_budget_makes_it_partial(revit, ws, tmp_path):
    path = full_ifc(tmp_path / "out.ifc")
    stub.Stopwatch.tick = 100000  # every read of the watch is past any budget
    result = check(ws, StubBridge(model(with_door=False, with_excluded=False)), path=str(path), categories=["Walls"], time_budget_s=1)
    assert result["limits"]["partial"] is True and result["verdict"] != "PASS"


def test_level_and_unknown_category(revit, ws, tmp_path):
    path = full_ifc(tmp_path / "out.ifc")
    result = check(ws, StubBridge(model()), path=str(path), level="L1")
    assert {r["category"] for r in result["rows"] if r.get("id")} == {"Floors"}
    bad = check(ws, StubBridge(model()), path=str(path), categories=["NoSuchThing"])
    assert bad["ok"] is False and bad["kind"] == "invalid_input" and bad["verdict"] == "UNVERIFIED"


# --------------------------------------------------------------------------- #
# IFC only, unreadable files, the sandbox
# --------------------------------------------------------------------------- #
def test_ifc_only_never_asks_revit_and_says_what_it_skipped(ws, tmp_path):
    b = IfcBuilder(schema="IFC2X3", millimetres=False)
    b.storey("L0", 0.0)
    b.element("IfcWall", storey="L0", code="21.12")
    b.element("IfcDoor", at=(1, 0, 0), material=False)  # no storey, no classification, no material
    b.element("IfcColumn", storey="L0", at=(2, 0, 0), code="28.1")
    b.element("IfcColumn", storey="L0", at=(2, 0, 0), code="28.1")  # duplicate
    path = b.write(tmp_path / "only.ifc")
    calls: List[Any] = []
    result = check(ws, lambda *a: calls.append(a), path=str(path), ifc_only=True)
    assert calls == []
    assert result["ok"] is True and result["verdict"] == "FAIL" and result["verified"] is False
    assert sorted(r["problem"] for r in result["rows"]) == ["duplicate_placement", "no_classification", "no_material", "no_storey"]
    assert result["not_checked"] and all(i.startswith("NOT_CHECKED") for i in result["info"])
    assert result["ifc"]["schema"] == "IFC2X3" and result["origin"]["ifc"]["site_m"] == [100.0, 200.0, 0.0]


def test_ifc_only_without_defects_is_unverified(ws, tmp_path):
    b = IfcBuilder()
    b.storey("L0", 0.0)
    b.element("IfcWall", storey="L0", code="21.12")
    result = check(ws, None, path=str(b.write(tmp_path / "ok.ifc")), ifc_only=True)
    assert result["verdict"] == "UNVERIFIED" and result["fails"] == []


def test_unreadable_ifc_is_unverified(ws, tmp_path):
    path = tmp_path / "broken.ifc"
    path.write_text("this is not an IFC file", encoding="utf-8")
    calls: List[Any] = []
    result = check(ws, lambda *a: calls.append(a), path=str(path))
    assert result["ok"] is False and result["kind"] == "ifc_unreadable" and result["verdict"] == "UNVERIFIED"
    assert calls == []


@pytest.mark.parametrize("where", ["outside", "plans", "proofs", "missing", "wrong_ext"])
def test_path_goes_through_the_sandbox(ws, tmp_path, tmp_path_factory, where):
    if where == "outside":
        p = tmp_path_factory.mktemp("elsewhere") / "x.ifc"
        full_ifc(p)
    elif where in ("plans", "proofs"):
        (tmp_path / where).mkdir()
        p = full_ifc(tmp_path / where / "x.ifc")
    elif where == "missing":
        p = tmp_path / "nope.ifc"
    else:
        p = tmp_path / "x.txt"
        p.write_text("x", encoding="utf-8")
    calls: List[Any] = []
    result = check(ws, lambda *a: calls.append(a), path=str(p), ifc_only=where != "missing")
    assert result["ok"] is False and calls == []
    expected = {"outside": "path_outside_workspace", "plans": "path_outside_workspace", "proofs": "path_outside_workspace",
                "missing": "file_not_found", "wrong_ext": "invalid_input"}[where]
    assert result["kind"] == expected


def test_bridge_failure_is_unverified_with_the_ifc_summary(ws, tmp_path, monkeypatch):
    monkeypatch.setattr(ifcmod, "_server_in_mock_mode", lambda: False)
    path = full_ifc(tmp_path / "out.ifc")

    def down(name, args):
        raise RuntimeError("connection refused")

    result = check(ws, down, path=str(path))
    assert result["ok"] is False and result["verdict"] == "UNVERIFIED" and result["ifc"]["objects"] == 3


def test_guid_derivation_round_trip():
    guid = ifcmod.ifc_guid_from_unique_id(uid_of(0x1234))
    assert guid is not None and len(guid) == 22
    expanded = ifcopenshell.guid.expand(guid)
    assert expanded[-8:] == "%08x" % (int(EPISODE[-8:], 16) ^ 0x1234)
    assert ifcmod.ifc_guid_from_unique_id("not-a-uid") is None


@pytest.mark.parametrize("revit_value,ifc_value,expected", [
    ("60", "60", "same"), ("Yes", True, "same"), ("No", True, "different"), ("3000 mm", 3.0, "not_compared"),
    ("2.5", 2.5, "same"), ("EI 60", "EI 30", "different"),
])
def test_compare_values(revit_value, ifc_value, expected):
    assert ifcmod.compare_values(revit_value, ifc_value) == expected


# --------------------------------------------------------------------------- #
# Read-only: no plan, read mode, the script passes the read-mode validator
# --------------------------------------------------------------------------- #
def test_script_is_read_mode_and_has_no_transaction():
    script = ifcmod.build_script({"ids": [], "tag": "", "categories": ["Walls"], "default_categories": [], "level": "",
                                  "params": ["Fire Rating ü"], "max_elements": 10, "time_budget_s": 5.0})
    validate_read_script(script)
    assert "Transaction" not in script and "u'Fire Rating \\u00fc'" in script


def test_manifest_documents_every_parameter_and_is_read_only():
    manifest = json.loads((ifcmod.MODULE_DIR / "module.json").read_text(encoding="utf-8"))
    (command,) = manifest["commands"]
    assert command["mcp_tool"] == "revit_ifc_check" and command["is_mutating"] is False
    assert "requires_plan" not in command
    for name, prop in command["input_schema"]["properties"].items():
        assert prop.get("description"), name
    for word in ("revit_export", "revit_check_"):
        assert word in command["title"]


class FakeRevit:
    def __init__(self, output: str) -> None:
        self.output, self.calls = output, []

    async def execute_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"success": True, "output": self.output}

    def call_is_read_only(self, name, arguments):
        return arguments.get("mode") == "read"


def test_needs_no_plan_even_when_approval_is_required(tmp_path, monkeypatch):
    path = full_ifc(tmp_path / "out.ifc")
    inst = ModuleInstance(ModuleManifest(**json.loads((ifcmod.MODULE_DIR / "module.json").read_text(encoding="utf-8"))), ifcmod.MODULE_DIR)
    monkeypatch.setattr(inst.code_module, "_server_in_mock_mode", lambda: False)
    modules = SimpleNamespace(get_all_modules=lambda: [inst], config=SimpleNamespace(allow_python_host=False))
    gate = ApprovalGate(tmp_path, "required")
    out = "SUMMARY\tread 1 element(s)\nROW\tid=101\tuid=x\tcategory=Walls\tlevel=L0\tassembly=\tmaterials=\tifc_guid=\texport_as=\texport_flag=\nMETA\ttruncated\t0\nCOUNT\trow\t1"
    revit = FakeRevit(out)
    provider = ModuleProvider(modules, WorkspaceMonitor([tmp_path]))
    capabilities = {tool.name: tool for tool in provider.get_capabilities()}
    assert capabilities["revit_ifc_check"].is_mutating is False
    capabilities["revit_execute_python"] = SimpleNamespace(is_mutating=True)
    registry = SimpleNamespace(
        lookup_tool=lambda name: capabilities.get(name),
        lookup_tool_provider=lambda name: provider if name in capabilities and name != "revit_execute_python" else revit,
        get_provider=lambda name: SimpleNamespace(gate=gate) if name == "approval" else None,
    )
    provider.tool_registry = registry
    result = asyncio.run(run_gated_tool(registry, gate, "revit_ifc_check", {"path": str(path), "categories": ["Walls"]}))
    assert result["ok"] is True and result["verdict"] == "PASS", result
    assert [c[1]["mode"] for c in revit.calls] == ["read"]
    validate_read_script(revit.calls[0][1]["script"])
