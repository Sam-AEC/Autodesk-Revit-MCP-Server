"""A tiny stand-in for the Revit API, just big enough to run the embedded check scripts under CPython.

It is NOT Revit. It proves the scripts' control flow, line protocol and arithmetic (join status, sweep
broad phase, probe point, baseline rows). It cannot prove that the real Revit API behaves the way the
stub assumes; that needs a live Revit (see the report of the change that added these tools).
"""
from __future__ import annotations

import contextlib
import math
import re
import sys
import types
from typing import Any, Dict, Iterator, List, Optional


class XYZ:
    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.X, self.Y, self.Z = x, y, z


class ElementId:
    InvalidElementId: "ElementId"

    def __init__(self, value: int) -> None:
        self.Value = int(value)


ElementId.InvalidElementId = ElementId(-1)


class _Enum:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


BuiltInParameter = _Enum(
    ALL_MODEL_INSTANCE_COMMENTS="comments", ROOM_NAME="room_name", ALL_MODEL_MARK="mark", ALL_MODEL_TYPE_MARK="type_mark",
    ALL_MODEL_TYPE_COMMENTS="type_comments", ALL_MODEL_DESCRIPTION="description", ALL_MODEL_MANUFACTURER="manufacturer",
    ALL_MODEL_MODEL="model", ROOM_NUMBER="room_number", DOOR_WIDTH="door_width", DOOR_HEIGHT="door_height",
    WINDOW_WIDTH="window_width", WINDOW_HEIGHT="window_height", FAMILY_WIDTH_PARAM="fam_width", FAMILY_HEIGHT_PARAM="fam_height",
    FAMILY_ROUGH_WIDTH_PARAM="rough_width", FAMILY_ROUGH_HEIGHT_PARAM="rough_height", HOST_VOLUME_COMPUTED="host_volume",
    ROOF_BASE_LEVEL_PARAM="roof_level", INSTANCE_SILL_HEIGHT_PARAM="sill_height",
)
BuiltInCategory = _Enum(
    OST_Walls=-2000011, OST_Floors=-2000032, OST_Rooms=-2000160, OST_Roofs=-2000035, OST_Columns=-2000100,
    OST_Doors=-2000023, OST_Windows=-2000014, OST_Stairs=-2000120, OST_Levels=-2000240, OST_Grids=-2000220,
    OST_PipeCurves=-2008044, OST_DuctCurves=-2008000, OST_PipeFitting=-2008049, OST_DuctFitting=-2008010,
    OST_PipeAccessory=-2008055, OST_DuctAccessory=-2008016, OST_MechanicalEquipment=-2001140, OST_PlumbingFixtures=-2001160,
    OST_DuctTerminal=-2008013, OST_FlexPipeCurves=-2008050, OST_FlexDuctCurves=-2008020, OST_ElectricalEquipment=-2001040,
    OST_LightingFixtures=-2001120, OST_ElectricalFixtures=-2001060, OST_GenericModel=-2000151,
)
ViewDetailLevel = _Enum(Fine="Fine")
BooleanOperationsType = _Enum(Intersect="Intersect")


class Options:
    DetailLevel = None
    ComputeReferences = False


class Category:
    def __init__(self, bic: int, name: str) -> None:
        self.Id = ElementId(bic)
        self.Name = name


class _Param:
    """A parameter. ``kind`` is the Revit StorageType name; ``text`` is what AsValueString shows."""

    def __init__(self, value: Any, kind: str = "String", text: Optional[str] = None) -> None:
        self._v = value
        self.StorageType = kind
        self.HasValue = value is not None and value != ""
        self._text = text

    def AsString(self) -> Optional[str]:
        return self._v if self.StorageType == "String" else None

    def AsValueString(self) -> Optional[str]:
        if self._text is not None:
            return self._text
        return None if self.StorageType == "String" else str(self._v)

    def AsDouble(self) -> float:
        return float(self._v)

    def AsInteger(self) -> int:
        return int(self._v)

    def AsElementId(self) -> "ElementId":
        return ElementId(int(self._v))


class Element:
    def __init__(self, eid: int, category: Optional[Category], comments: str = "") -> None:
        self.Id = ElementId(eid)
        self.Category = category
        self.comments = comments
        self.bbox: Optional[BoundingBox] = None
        self.solids: List[Any] = []
        self.Host: Optional[Element] = None
        self.params: Dict[str, _Param] = {}  # by built-in key, e.g. "mark"
        self.named: Dict[str, _Param] = {}  # by LookupParameter name
        self.type_el: Optional[Element] = None
        self.Name = ""
        self.is_type = False

    def get_Parameter(self, which: str) -> Optional[_Param]:
        if which in self.params:
            return self.params[which]
        return _Param(self.comments) if which == "comments" else None

    def LookupParameter(self, name: str) -> Optional[_Param]:
        return self.named.get(name)

    def GetTypeId(self) -> "ElementId":
        return self.type_el.Id if self.type_el is not None else ElementId(-1)

    def set_param(self, key: str, value: Any, kind: str = "String", text: Optional[str] = None) -> "Element":
        self.params[key] = _Param(value, kind, text)
        return self

    def get_BoundingBox(self, view: Any) -> Optional["BoundingBox"]:
        return self.bbox

    def get_Geometry(self, opt: Any) -> List[Any]:
        return list(self.solids)


class BoundingBox:
    def __init__(self, lo: tuple, hi: tuple) -> None:
        self.Min, self.Max = XYZ(*lo), XYZ(*hi)


class _Projection:
    def __init__(self, distance: float, parameter: float, point: XYZ) -> None:
        self.Distance, self.Parameter, self.XYZPoint = distance, parameter, point


class Curve:
    def __init__(self, p0: tuple, p1: tuple) -> None:
        self.p0, self.p1 = XYZ(*p0), XYZ(*p1)

    @property
    def Length(self) -> float:
        return math.dist((self.p0.X, self.p0.Y, self.p0.Z), (self.p1.X, self.p1.Y, self.p1.Z))

    def Project(self, pt: XYZ) -> _Projection:
        dx, dy = self.p1.X - self.p0.X, self.p1.Y - self.p0.Y
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, ((pt.X - self.p0.X) * dx + (pt.Y - self.p0.Y) * dy) / l2))
        q = XYZ(self.p0.X + dx * t, self.p0.Y + dy * t, self.p0.Z)
        return _Projection(math.dist((pt.X, pt.Y, pt.Z), (q.X, q.Y, q.Z)), t * self.Length, q)

    def ComputeNormalizedParameter(self, raw: float) -> float:
        return raw / self.Length if self.Length else 0.0

    def Tessellate(self) -> List[XYZ]:
        return [self.p0, self.p1]

    def GetEndPoint(self, end: int) -> XYZ:
        return self.p0 if end == 0 else self.p1

    def Evaluate(self, t: float, normalized: bool) -> XYZ:
        return XYZ(
            self.p0.X + (self.p1.X - self.p0.X) * t,
            self.p0.Y + (self.p1.Y - self.p0.Y) * t,
            self.p0.Z + (self.p1.Z - self.p0.Z) * t,
        )


class Line(Curve):
    pass


class Arc:
    """A plan swing arc: only what the openings audit reads."""

    def __init__(self, centre: tuple, radius_ft: float, mid: tuple) -> None:
        self.Center, self.Radius, self._mid = XYZ(*centre), radius_ft, XYZ(*mid)

    def Evaluate(self, t: float, normalized: bool) -> XYZ:
        return self._mid


class LocationPoint:
    def __init__(self, point: tuple) -> None:
        self.Point = XYZ(*point)


class LocationCurve:
    def __init__(self, curve: Curve, joins: Dict[int, List["Wall"]]) -> None:
        self.Curve = curve
        self._joins = joins

    def get_ElementsAtJoin(self, end: int) -> List["Wall"]:
        return list(self._joins.get(end, []))

    def get_JoinType(self, end: int) -> str:
        return "Miter"


class _WallType:
    def __init__(self, function: str) -> None:
        self.Function = function


class Wall(Element):
    def __init__(self, eid: int, p0: tuple, p1: tuple, comments: str = "", function: str = "Exterior",
                 orientation: tuple = (0.0, 1.0, 0.0), z: tuple = (0.0, 10.0)) -> None:
        super().__init__(eid, Category(BuiltInCategory.OST_Walls, "Walls"), comments)
        self.Location = LocationCurve(Line(p0, p1), {})
        self.WallType = _WallType(function)
        self.Orientation = XYZ(*orientation)
        self.Flipped = False
        self.Width = 0.5
        self.cut_rects: List[tuple] = []  # (along_lo, along_hi, z_lo, z_hi) in feet: where the wall is really open
        self.join_allowed = {0: True, 1: True}
        self.bbox = BoundingBox((min(p0[0], p1[0]), min(p0[1], p1[1]), z[0]), (max(p0[0], p1[0]), max(p0[1], p1[1]), z[1]))

    def join(self, end: int, other: "Wall") -> None:
        self.Location._joins.setdefault(end, []).append(other)
        self.Location._joins[end].append(self)  # Revit lists the wall itself too; the script must ignore it


class WallUtils:
    @staticmethod
    def IsWallJoinAllowedAtEnd(wall: Wall, end: int) -> bool:
        return wall.join_allowed[end]


class Room(Element):
    def __init__(self, eid: int, lo: tuple, hi: tuple, number: str = "1") -> None:
        super().__init__(eid, Category(BuiltInCategory.OST_Rooms, "Rooms"))
        self.Area = 10.0
        self.Number = number
        self.bbox = BoundingBox(lo, hi)

    def IsPointInRoom(self, pt: XYZ) -> bool:
        lo, hi = self.bbox.Min, self.bbox.Max
        return lo.X <= pt.X <= hi.X and lo.Y <= pt.Y <= hi.Y and lo.Z <= pt.Z <= hi.Z

    def get_Parameter(self, which: str) -> Optional[_Param]:
        return _Param("Room " + self.Number) if which == "room_name" else None


class Solid:
    def __init__(self, volume: float, faces: Optional[List[Any]] = None) -> None:
        self.Volume = volume
        self.Faces = list(faces or [])

    def ComputeCentroid(self) -> XYZ:
        return XYZ(1.0, 2.0, 3.0)


class GeometryInstance:
    def __init__(self, items: Optional[List[Any]] = None) -> None:
        self._items = list(items or [])

    def GetInstanceGeometry(self) -> List[Any]:
        return list(self._items)


class Mesh:
    pass


class BooleanOperationsUtils:
    overlap: Dict[tuple, float] = {}

    @staticmethod
    def ExecuteBooleanOperation(a: Solid, b: Solid, kind: Any) -> Optional[Solid]:
        vol = BooleanOperationsUtils.overlap.get((id(a), id(b)), BooleanOperationsUtils.overlap.get((id(b), id(a)), 0.0))
        return Solid(vol)


class ElementMulticategoryFilter:
    def __init__(self, cats: List[int]) -> None:
        self.cats = list(cats)


class FamilyInstanceFilter:
    def __init__(self, document: "Document", symbol_id: ElementId) -> None:
        self.symbol_id = symbol_id.Value


class FilteredElementCollector:
    def __init__(self, document: "Document") -> None:
        self._doc = document
        self._cats: Optional[List[int]] = None
        self._cls: Optional[type] = None
        self._symbol: Optional[int] = None
        self._not_types = False

    def OfCategory(self, bic: int) -> "FilteredElementCollector":
        self._cats = [bic]
        return self

    def OfClass(self, cls: type) -> "FilteredElementCollector":
        self._cls = cls
        return self

    def WhereElementIsNotElementType(self) -> "FilteredElementCollector":
        self._not_types = True
        return self

    def WhereElementIsElementType(self) -> "FilteredElementCollector":
        self._only_types = True
        return self

    def WherePasses(self, flt: Any) -> "FilteredElementCollector":
        if isinstance(flt, FamilyInstanceFilter):
            self._symbol = flt.symbol_id
            self._cls = FamilyInstance
        else:
            self._cats = flt.cats
        return self

    def _matches(self, e: Element) -> bool:
        if self._not_types and e.is_type:
            return False
        if getattr(self, "_only_types", False) and not e.is_type:
            return False
        if self._cls is not None and not isinstance(e, self._cls):
            return False
        if self._cats is not None and not (e.Category is not None and e.Category.Id.Value in self._cats):
            return False
        if self._symbol is not None and not (isinstance(e, FamilyInstance) and e.Symbol is not None and e.Symbol.Id.Value == self._symbol):
            return False
        return True

    def __iter__(self) -> Iterator[Element]:
        for e in self._doc.elements:
            if self._matches(e):
                yield e

    def GetElementCount(self) -> int:
        return sum(1 for _ in self)


class _Failure:
    def __init__(self, description: str, severity: str, failing: List[int], additional: Optional[List[int]] = None) -> None:
        self._d, self._s, self._f, self._a = description, severity, failing, additional or []

    def GetDescriptionText(self) -> str:
        return self._d

    def GetSeverity(self) -> str:
        return self._s

    def GetFailingElements(self) -> List[ElementId]:
        return [ElementId(i) for i in self._f]

    def GetAdditionalElements(self) -> List[ElementId]:
        return [ElementId(i) for i in self._a]


class Document:
    Title = "Villa.rvt"
    CreationGUID = "11111111-2222-3333-4444-555555555555"

    def __init__(self, elements: Optional[List[Element]] = None, warnings: Optional[List[_Failure]] = None) -> None:
        self.elements: List[Element] = list(elements or [])
        self._warnings = list(warnings or [])
        self.closed = False
        self.FamilyManager = _FamilyManager([])
        self.edit_calls = 0

    def GetElement(self, eid: ElementId) -> Optional[Element]:
        for e in self.elements:
            if e.Id.Value == eid.Value:
                return e
        return None

    def GetWarnings(self) -> List[_Failure]:
        return list(self._warnings)

    def EditFamily(self, family: "Family") -> "Document":
        self.edit_calls += 1
        if family.famdoc is None:
            raise RuntimeError("the family document cannot be opened")
        return family.famdoc

    def Close(self, save: bool) -> bool:
        assert save is False, "a read-only probe must never save"
        self.closed = True
        return True


Failure = _Failure


class _Stopwatch:
    """ElapsedMilliseconds grows by ``Stopwatch.tick`` on every read, so tests can force a time budget to run out."""

    @property
    def ElapsedMilliseconds(self) -> int:
        Stopwatch.reads += 1
        return Stopwatch.reads * Stopwatch.tick


class Stopwatch:
    tick = 0
    reads = 0

    @staticmethod
    def StartNew() -> _Stopwatch:
        Stopwatch.reads = 0
        return _Stopwatch()


class _List(list):
    def Add(self, item: Any) -> None:
        self.append(item)


class _GenericList:
    def __getitem__(self, _: Any) -> Any:
        return _List


class App:
    VersionNumber = "2024"


# --------------------------------------------------------------------------- #
# Levels, views, grids, openings, roofs, MEP, families
# --------------------------------------------------------------------------- #
class Level(Element):
    def __init__(self, eid: int, name: str, elevation_ft: float) -> None:
        super().__init__(eid, Category(BuiltInCategory.OST_Levels, "Levels"))
        self.Name, self.Elevation, self.Pinned = name, elevation_ft, True


class ViewPlan(Element):
    def __init__(self, eid: int, name: str, level: Optional[Level], view_type: str = "FloorPlan", template: bool = False) -> None:
        super().__init__(eid, None)
        self.Name, self.GenLevel, self.ViewType, self.IsTemplate = name, level, view_type, template


class View3D(Element):
    def __init__(self, eid: int, template: bool = False, perspective: bool = False) -> None:
        super().__init__(eid, None)
        self.IsTemplate, self.IsPerspective = template, perspective


class Grid(Element):
    def __init__(self, eid: int, name: str, p0: tuple, p1: tuple) -> None:
        super().__init__(eid, Category(BuiltInCategory.OST_Grids, "Grids"))
        self.Name, self.Curve, self.Pinned = name, Line(p0, p1), True


class FindReferenceTarget:
    Element = "Element"


class ReferenceIntersector:
    """Ray against one wall: a hit unless the ray passes through a cut rectangle, past the wall ends or its height."""

    def __init__(self, target: ElementId, kind: Any, view: View3D) -> None:
        if _CURRENT["doc"] is None:
            raise RuntimeError("no document")
        self.wall = _CURRENT["doc"].GetElement(target)

    def Find(self, origin: XYZ, direction: XYZ) -> List[Any]:
        w = self.wall
        if w is None or getattr(w, "ray_blind", False):
            return []
        p0, p1 = w.Location.Curve.p0, w.Location.Curve.p1
        dx, dy = p1.X - p0.X, p1.Y - p0.Y
        length = math.hypot(dx, dy)
        dx, dy = dx / length, dy / length
        denom = direction.X * dy - direction.Y * dx
        if abs(denom) < 1e-9:
            return []
        # origin + s * n = p0 + a * d, solved for s (distance along the ray)
        s = ((p0.X - origin.X) * dy - (p0.Y - origin.Y) * dx) / denom
        a = (origin.X + s * direction.X - p0.X) * dx + (origin.Y + s * direction.Y - p0.Y) * dy
        if s <= 0 or a < 0 or a > length or not (w.bbox.Min.Z <= origin.Z <= w.bbox.Max.Z):
            return []
        for lo, hi, zlo, zhi in w.cut_rects:
            if lo <= a <= hi and zlo <= origin.Z <= zhi:
                return []
        return [object()]


class PlanarFace:
    def __init__(self, normal_z: float, area: float, loops: List[List[tuple]]) -> None:
        self.FaceNormal = XYZ(0.0, 0.0, normal_z)
        self.Area = area
        self._loops = loops

    def GetEdgesAsCurveLoops(self) -> List[List[Curve]]:
        out = []
        for pts in self._loops:
            out.append([Line(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))])
        return out


class RoofBase(Element):
    def __init__(self, eid: int, level: Optional[Level] = None, comments: str = "") -> None:
        super().__init__(eid, Category(BuiltInCategory.OST_Roofs, "Roofs"), comments)
        if level is not None:
            self.params["roof_level"] = _Param(level.Id.Value, "ElementId")


def rect_loop(x0: float, y0: float, x1: float, y1: float, z: float = 0.0) -> List[tuple]:
    return [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]


class FamilyInstance(Element):
    def __init__(self, eid: int, category: Category, point: tuple = (0.0, 0.0, 0.0), host: Optional[Element] = None,
                 comments: str = "", symbol: Optional["FamilySymbol"] = None) -> None:
        super().__init__(eid, category, comments)
        self.Location = LocationPoint(point)
        self.Host = host
        self.Symbol = symbol
        self.LevelId = ElementId(-1)
        self.arcs: List[Arc] = []
        self.sub_components: List[int] = []
        self.MEPModel: Any = None

    def get_Geometry(self, opt: Any) -> List[Any]:
        items: List[Any] = list(self.solids)
        if getattr(opt, "View", None) is not None:
            items += self.arcs
        return items

    def GetSubComponentIds(self) -> List[ElementId]:
        return [ElementId(i) for i in self.sub_components]


class Family(Element):
    def __init__(self, eid: int, name: str, category: Optional[Category] = None) -> None:
        super().__init__(eid, None)
        self.Name = name
        self.FamilyCategory = category
        self.symbols: List["FamilySymbol"] = []
        self.famdoc: Optional[Document] = None
        self.IsInPlace = False
        self.IsEditable = True

    def GetFamilySymbolIds(self) -> List[ElementId]:
        return [s.Id for s in self.symbols]


class FamilySymbol(Element):
    def __init__(self, eid: int, name: str, family: Family) -> None:
        super().__init__(eid, None)
        self.Name, self.Family = name, family
        family.symbols.append(self)
        self.is_type = True


class GenericForm(Element):
    def __init__(self, eid: int, lo: tuple, hi: tuple, solid: bool = True) -> None:
        super().__init__(eid, None)
        self.bbox = BoundingBox(lo, hi)
        self.IsSolid = solid


class _CoordSys:
    def __init__(self, basis_z: tuple) -> None:
        self.BasisZ = XYZ(*basis_z)


class ConnectorElement(Element):
    def __init__(self, eid: int, domain: str, system: str, radius: float = 0.0, width: float = 0.0, height: float = 0.0,
                 shape: str = "Round", origin: tuple = (0.0, 0.0, 0.0), basis_z: tuple = (0.0, 0.0, 1.0), direction: str = "Bidirectional") -> None:
        super().__init__(eid, None)
        self.Domain, self.SystemClassification, self.Radius, self.Width, self.Height = domain, system, radius, width, height
        self.Shape, self.Origin, self.CoordinateSystem, self.Direction = shape, XYZ(*origin), _CoordSys(basis_z), direction


class _FamParam:
    def __init__(self, name: str, instance: bool = False, kind: str = "Length", formula: Optional[str] = None) -> None:
        self.Definition = types.SimpleNamespace(Name=name)
        self.IsInstance, self.StorageType, self.Formula, self.IsShared = instance, kind, formula, False


class _FamilyManager:
    def __init__(self, params: List[_FamParam]) -> None:
        self.Parameters = list(params)


class MepSystem:
    def __init__(self, name: str, type_el: Optional[Element] = None) -> None:
        self.Name, self._type = name, type_el

    def GetTypeId(self) -> ElementId:
        return self._type.Id if self._type is not None else ElementId(-1)


class Connector:
    def __init__(self, domain: str = "DomainPiping", kind: str = "End", origin: tuple = (0.0, 0.0, 0.0), radius_ft: float = 0.0,
                 direction: str = "Bidirectional", system: Optional[MepSystem] = None, owner: Optional[Element] = None,
                 shape: str = "Round", width: float = 0.0, height: float = 0.0) -> None:
        self.Domain, self.ConnectorType, self.Origin = domain, kind, XYZ(*origin)
        self.Radius, self.Direction, self.MEPSystem, self.Owner = radius_ft, direction, system, owner
        self.Shape, self.Width, self.Height = shape, width, height
        self.AllRefs: List["Connector"] = []
        self.CoordinateSystem = _CoordSys((0.0, 0.0, 1.0))

    @property
    def IsConnected(self) -> bool:
        return bool(self.AllRefs)

    def connect(self, other: "Connector") -> None:
        self.AllRefs.append(other)
        other.AllRefs.append(self)


class _ConnectorManager:
    def __init__(self, connectors: List[Connector]) -> None:
        self.Connectors = list(connectors)


class MEPCurve(Element):
    def __init__(self, eid: int, category: Category, connectors: List[Connector], system: Optional[MepSystem] = None, comments: str = "") -> None:
        super().__init__(eid, category, comments)
        self.ConnectorManager = _ConnectorManager(connectors)
        self.MEPSystem = system
        for c in connectors:
            c.Owner = self


def mep_instance(eid: int, category: Category, connectors: List[Connector], comments: str = "") -> FamilyInstance:
    inst = FamilyInstance(eid, category, comments=comments)
    inst.MEPModel = types.SimpleNamespace(ConnectorManager=_ConnectorManager(connectors))
    for c in connectors:
        c.Owner = inst
    return inst


def _math_namespace() -> Any:
    return types.SimpleNamespace(Acos=math.acos, PI=math.pi)


class _Regex:
    @staticmethod
    def IsMatch(text: str, pattern: str) -> bool:
        return re.search(pattern, text) is not None


_CURRENT: Dict[str, Any] = {"doc": None}


@contextlib.contextmanager
def installed(monkeypatch: Any) -> Iterator[None]:
    """Make ``import clr / System / Autodesk.Revit.DB`` resolve to this stub for the duration of a test."""
    db = types.ModuleType("Autodesk.Revit.DB")
    for name in (
        "XYZ", "ElementId", "BuiltInParameter", "BuiltInCategory", "ViewDetailLevel", "BooleanOperationsType",
        "Options", "Wall", "LocationCurve", "LocationPoint", "WallUtils", "Solid", "GeometryInstance", "Mesh",
        "BooleanOperationsUtils", "ElementMulticategoryFilter", "FilteredElementCollector", "FamilyInstanceFilter",
        "Level", "ViewPlan", "View3D", "Grid", "Line", "Arc", "ReferenceIntersector", "FindReferenceTarget", "PlanarFace",
        "RoofBase", "FamilyInstance", "Family", "FamilySymbol", "GenericForm", "ConnectorElement", "MEPCurve",
    ):
        setattr(db, name, globals()[name])
    system = types.ModuleType("System")
    system.Math = _math_namespace()  # type: ignore[attr-defined]
    regex_mod = types.ModuleType("System.Text.RegularExpressions")
    regex_mod.Regex = _Regex  # type: ignore[attr-defined]
    modules = {
        "clr": types.ModuleType("clr"),
        "System": system,
        "System.Collections": types.ModuleType("System.Collections"),
        "System.Collections.Generic": types.ModuleType("System.Collections.Generic"),
        "System.Diagnostics": types.ModuleType("System.Diagnostics"),
        "System.Text": types.ModuleType("System.Text"),
        "System.Text.RegularExpressions": regex_mod,
        "Autodesk": types.ModuleType("Autodesk"),
        "Autodesk.Revit": types.ModuleType("Autodesk.Revit"),
        "Autodesk.Revit.DB": db,
    }
    modules["System.Collections.Generic"].List = _GenericList()  # type: ignore[attr-defined]
    modules["System.Diagnostics"].Stopwatch = Stopwatch  # type: ignore[attr-defined]
    for name, mod in modules.items():
        monkeypatch.setitem(sys.modules, name, mod)
    Stopwatch.tick = 0
    yield
    Stopwatch.tick = 0
    _CURRENT["doc"] = None


def run_script(script: str, document: Document, app: Any = None) -> str:
    """Execute a built script like the add-in does (``doc`` and ``app`` in scope) and return ``__output__``."""
    _CURRENT["doc"] = document
    scope: Dict[str, Any] = {"doc": document, "app": app if app is not None else App(), "__output__": "", "__name__": "__ipy__"}
    exec(compile(script, "<embedded-script>", "exec"), scope)  # noqa: S102 - test-only stub execution
    return str(scope["__output__"])


# --------------------------------------------------------------------------- #
# Write-side stand-ins for the family builder (tests/test_revit_family_scripts.py)
# --------------------------------------------------------------------------- #
# Just enough of the Revit API to run scripts/make_family.ipy of the revit_family module under CPython: a family
# document that records what is built in it, a project document that can load a saved family, transactions that can
# be rolled back, and System.IO on the real file system (tests give it a temp folder). Everything is opt-in through
# install_family_write_api(); the read-side stubs above are not changed.
XYZ.BasisZ = XYZ(0.0, 0.0, 1.0)


class FLine(Line):
    @staticmethod
    def CreateBound(a: XYZ, b: XYZ) -> "FLine":
        return FLine((a.X, a.Y, a.Z), (b.X, b.Y, b.Z))


class CurveArray:
    def __init__(self) -> None:
        self.items: List[Any] = []

    def Append(self, curve: Any) -> None:
        self.items.append(curve)


class CurveArrArray:
    def __init__(self) -> None:
        self.items: List[CurveArray] = []

    def Append(self, arr: CurveArray) -> None:
        self.items.append(arr)


class Plane:
    @staticmethod
    def CreateByNormalAndOrigin(normal: XYZ, origin: XYZ) -> Any:
        return types.SimpleNamespace(Normal=normal, Origin=origin)


class SketchPlane:
    @staticmethod
    def Create(document: Any, plane: Any) -> Any:
        return types.SimpleNamespace(Plane=plane)


class SaveAsOptions:
    OverwriteExistingFile = False


class IFailuresPreprocessor:
    pass


class IFamilyLoadOptions:
    pass


class _WParam:
    """A connector parameter the script can set."""

    def __init__(self, store: Dict[str, Any], key: str, read_only: bool = False) -> None:
        self._store, self._key, self.IsReadOnly = store, key, read_only

    def Set(self, value: Any) -> None:
        self._store[self._key] = value


class _FaceRef:
    def __init__(self, extrusion: "FExtrusion", key: str) -> None:
        self.extrusion, self.key = extrusion, key


class _BoxFace(PlanarFace):
    def __init__(self, extrusion: "FExtrusion", key: str) -> None:
        super().__init__(0.0, 1.0, [])
        axis, sign = key[1], 1.0 if key[0] == "+" else -1.0
        self.FaceNormal = XYZ(sign if axis == "x" else 0.0, sign if axis == "y" else 0.0, sign if axis == "z" else 0.0)
        self.Reference = _FaceRef(extrusion, key)


class FExtrusion(GenericForm):
    """The box NewExtrusion makes: six planar faces with references, a bounding box in feet."""

    def get_Geometry(self, opt: Any) -> List[Any]:
        return [Solid(1.0, [_BoxFace(self, k) for k in ("+x", "-x", "+y", "-y", "+z", "-z")])]


class FConnector(ConnectorElement):
    """ConnectorElement with the Create* factories and the size / flow parameters a family builder sets."""

    def __init__(self, eid: int, domain: str, system: str, ref: Any, fam: "FamilyDoc") -> None:
        super().__init__(eid, domain, system)
        self.ref = ref
        self.values: Dict[str, Any] = {}
        self._fam = fam

    def get_Parameter(self, which: Any) -> Any:
        app = self._fam.app
        if which in ("connector_diameter", "connector_radius"):
            return None if app.refuse_size else _WParam(self.values, which)
        if which in ("pipe_flow", "duct_flow"):
            return None if app.refuse_flow else _WParam(self.values, which)
        return None

    @staticmethod
    def _make(fam: "FamilyDoc", domain: str, system: Any, ref: Any) -> "FConnector":
        ce = FConnector(fam.next_id(), domain, str(system), ref, fam)
        fam.elements.append(ce)
        return ce

    @staticmethod
    def CreatePipeConnector(fam: "FamilyDoc", system: Any, ref: Any) -> "FConnector":
        return FConnector._make(fam, "DomainPiping", system, ref)

    @staticmethod
    def CreateDuctConnector(fam: "FamilyDoc", system: Any, profile: Any, ref: Any) -> "FConnector":
        return FConnector._make(fam, "DomainHvac", system, ref)

    @staticmethod
    def CreateElectricalConnector(fam: "FamilyDoc", system: Any, ref: Any) -> "FConnector":
        return FConnector._make(fam, "DomainElectrical", system, ref)


class _FamilyCreate:
    def __init__(self, fam: "FamilyDoc") -> None:
        self._fam = fam

    def NewExtrusion(self, solid: bool, profile: CurveArrArray, plane: Any, height_ft: float) -> FExtrusion:
        pts = [p for curve in profile.items[0].items for p in (curve.p0, curve.p1)]
        z0 = plane.Plane.Origin.Z
        lo = (min(p.X for p in pts), min(p.Y for p in pts), z0)
        hi = (max(p.X for p in pts), max(p.Y for p in pts), z0 + height_ft)
        ex = FExtrusion(self._fam.next_id(), lo, hi, solid)
        self._fam.elements.append(ex)
        return ex


class _Types:
    def __init__(self) -> None:
        self.names: List[str] = []

    @property
    def Size(self) -> int:
        return len(self.names)


class _FamManager:
    def __init__(self) -> None:
        self.Types = _Types()
        self.Parameters: List[Any] = []
        self.CurrentType: Any = None

    def NewType(self, name: str) -> str:
        self.Types.names.append(name)
        return name


class _Categories:
    def get_Item(self, bic: int) -> Category:
        return Category(bic, "Category %s" % bic)


class FTransaction:
    def __init__(self, document: Any, name: str = "") -> None:
        self.doc, self.name, self.started = document, name, False

    def Start(self) -> None:
        self.started = True
        self.doc.open_txns += 1

    def GetFailureHandlingOptions(self) -> Any:
        return types.SimpleNamespace(SetFailuresPreprocessor=lambda p: None)

    def SetFailureHandlingOptions(self, opts: Any) -> None:
        return None

    def HasStarted(self) -> bool:
        return self.started

    def Commit(self) -> str:
        self.started = False
        self.doc.open_txns -= 1
        if self.doc.refuse_commit:
            self.doc.rolled_back_txns.append(self.name)
            return "RolledBack"
        self.doc.committed_txns.append(self.name)
        return "Committed"

    def RollBack(self) -> str:
        self.started = False
        self.doc.open_txns -= 1
        self.doc.rolled_back_txns.append(self.name)
        return "RolledBack"


class FTransactionGroup:
    def __init__(self, document: Any, name: str = "") -> None:
        self.doc, self.name, self.started, self.snapshot = document, name, False, []

    def Start(self) -> None:
        self.started, self.snapshot = True, list(self.doc.elements)

    def HasStarted(self) -> bool:
        return self.started

    def RollBack(self) -> str:
        self.started = False
        self.doc.elements = list(self.snapshot)
        self.doc.group_log.append("RolledBack")
        return "RolledBack"

    def Assimilate(self) -> str:
        self.started = False
        self.doc.group_log.append("Assimilated")
        return "Committed"


class FamilyDoc(Document):
    """A family document made by FakeApp.NewFamilyDocument."""

    def __init__(self, app: "FakeApp", template: str) -> None:
        super().__init__()
        self.app, self.template, self.IsFamilyDocument = app, template, True
        self._ids = 1000
        self.OwnerFamily = types.SimpleNamespace(FamilyCategory=app.template_category)
        self.Settings = types.SimpleNamespace(Categories=_Categories())
        self.FamilyCreate = _FamilyCreate(self)
        self.FamilyManager = _FamManager()
        self.open_txns, self.committed_txns, self.rolled_back_txns, self.group_log = 0, [], [], []
        self.refuse_commit = False
        self.saved_to: Optional[str] = None
        self.elements.extend(app.template_nested)

    def next_id(self) -> int:
        self._ids += 1
        return self._ids

    def Regenerate(self) -> None:
        return None

    def SaveAs(self, path: str, options: Any) -> None:
        if self.app.fail_save:
            raise RuntimeError("disk is full")
        with open(path, "wb") as fh:
            fh.write(b"RFA")
        self.saved_to = path
        self.app.saved[path] = self.OwnerFamily.FamilyCategory

    def Close(self, save: bool) -> bool:
        assert save is False, "the builder must never close with save=True"
        self.closed = True
        return True


class ProjectDoc(Document):
    """The project document: loads a family saved by a FamilyDoc and supports transactions and groups."""

    def __init__(self, app: "FakeApp") -> None:
        super().__init__()
        self.app, self.IsFamilyDocument = app, False
        self.open_txns, self.committed_txns, self.rolled_back_txns, self.group_log = 0, [], [], []
        self.refuse_commit = False
        self._ids = 500
        self.load_calls: List[str] = []

    def LoadFamily(self, path: str, options: Any) -> Any:
        self.load_calls.append(path)
        if self.app.refuse_load:
            return (False, None)
        category = self.app.saved.get(path)
        if category is None:
            raise RuntimeError("not a family file: %s" % path)
        name = path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        existing = [e for e in self.elements if isinstance(e, Family) and e.Name == name]
        if existing:
            if not options.OnFamilyFound(True, False):
                return (False, existing[0])
            existing[0].FamilyCategory = category
            return (True, existing[0])
        self._ids += 1
        fam = Family(self._ids, name, category)
        self._ids += 1
        FamilySymbol(self._ids, name, fam)
        self.elements.append(fam)
        self.elements.extend(fam.symbols)
        return (True, fam)


class FakeApp(App):
    """Application with a template folder, NewFamilyDocument and switches to make the builder fail."""

    def __init__(self, template_folder: str = "") -> None:
        self.FamilyTemplatePath = template_folder
        self.template_category = Category(BuiltInCategory.OST_GenericModel, "Generic Models")
        self.template_nested: List[Element] = []
        self.family_docs: List[FamilyDoc] = []
        self.saved: Dict[str, Category] = {}
        self.refuse_size = self.refuse_flow = self.fail_save = self.refuse_load = False

    def NewFamilyDocument(self, template: str) -> FamilyDoc:
        import os

        if not os.path.isfile(template):
            raise RuntimeError("the template file does not exist: %s" % template)
        fd = FamilyDoc(self, template)
        self.family_docs.append(fd)
        return fd


class _IoDirectory:
    @staticmethod
    def Exists(path: str) -> bool:
        import os

        return os.path.isdir(path)

    @staticmethod
    def GetFiles(folder: str, pattern: str = "*", option: Any = None) -> List[str]:
        import pathlib

        walk = pathlib.Path(folder).rglob(pattern) if option else pathlib.Path(folder).glob(pattern)
        return [str(p) for p in walk if p.is_file()]

    @staticmethod
    def CreateDirectory(path: str) -> None:
        import os

        os.makedirs(path, exist_ok=True)


class _IoFile:
    @staticmethod
    def Exists(path: str) -> bool:
        import os

        return os.path.isfile(path)

    @staticmethod
    def Delete(path: str) -> None:
        import os

        os.remove(path)


class _IoFileInfo:
    def __init__(self, path: str) -> None:
        import os

        self.Length = os.path.getsize(path)


class _IoPath:
    @staticmethod
    def Combine(a: str, b: str) -> str:
        import os

        return os.path.join(a, b)

    @staticmethod
    def GetFileName(p: str) -> str:
        import os

        return os.path.basename(p)

    @staticmethod
    def GetFileNameWithoutExtension(p: str) -> str:
        import os

        return os.path.splitext(os.path.basename(p))[0]


@contextlib.contextmanager
def install_family_write_api(monkeypatch: Any) -> Iterator[None]:
    """``installed()`` plus the write-side names the family builder imports (Transaction, SketchPlane, System.IO, ...)."""
    with installed(monkeypatch):
        db = sys.modules["Autodesk.Revit.DB"]
        extra = {
            "Line": FLine, "ConnectorElement": FConnector, "CurveArray": CurveArray, "CurveArrArray": CurveArrArray, "Plane": Plane,
            "SketchPlane": SketchPlane, "SaveAsOptions": SaveAsOptions, "IFailuresPreprocessor": IFailuresPreprocessor,
            "IFamilyLoadOptions": IFamilyLoadOptions, "Transaction": FTransaction, "TransactionGroup": FTransactionGroup,
            "TransactionStatus": _Enum(Committed="Committed", RolledBack="RolledBack", Started="Started"),
            "FailureSeverity": _Enum(Warning="Warning", Error="Error"),
            "FailureProcessingResult": _Enum(Continue="Continue", ProceedWithRollBack="ProceedWithRollBack"),
            "ConnectorProfileType": _Enum(Round="Round", Rectangular="Rectangular"),
            "BuiltInParameter": _Enum(
                **BuiltInParameter.__dict__, CONNECTOR_DIAMETER="connector_diameter", CONNECTOR_RADIUS="connector_radius",
                RBS_PIPE_FLOW_DIRECTION_PARAM="pipe_flow", RBS_DUCT_FLOW_DIRECTION_PARAM="duct_flow",
            ),
        }
        for name, value in extra.items():
            setattr(db, name, value)
        system_io = types.ModuleType("System.IO")
        for name, value in {"Directory": _IoDirectory, "File": _IoFile, "FileInfo": _IoFileInfo, "Path": _IoPath, "SearchOption": _Enum(AllDirectories=True)}.items():
            setattr(system_io, name, value)
        monkeypatch.setitem(sys.modules, "System.IO", system_io)
        for module, names in (
            ("Autodesk.Revit.DB.Plumbing", {"PipeSystemType": ["DomesticColdWater", "DomesticHotWater", "Sanitary", "Vent", "SupplyHydronic", "ReturnHydronic"]}),
            ("Autodesk.Revit.DB.Mechanical", {"DuctSystemType": ["SupplyAir", "ReturnAir", "ExhaustAir", "OtherAir"]}),
            ("Autodesk.Revit.DB.Electrical", {"ElectricalSystemType": ["PowerCircuit", "Data"]}),
        ):
            mod = types.ModuleType(module)
            for enum, members in names.items():
                setattr(mod, enum, _Enum(**{m: m for m in members}))
            monkeypatch.setitem(sys.modules, module, mod)
        yield
