"""A tiny stand-in for the Revit API, just big enough to run the embedded check scripts under CPython.

It is NOT Revit. It proves the scripts' control flow, line protocol and arithmetic (join status, sweep
broad phase, probe point, baseline rows). It cannot prove that the real Revit API behaves the way the
stub assumes; that needs a live Revit (see the report of the change that added these tools).
"""
from __future__ import annotations

import contextlib
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


BuiltInParameter = _Enum(ALL_MODEL_INSTANCE_COMMENTS="comments", ROOM_NAME="room_name")
BuiltInCategory = _Enum(
    OST_Walls=-2000011, OST_Floors=-2000032, OST_Rooms=-2000160, OST_Roofs=-2000035, OST_Columns=-2000100
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
    def __init__(self, value: str) -> None:
        self._v = value

    def AsString(self) -> str:
        return self._v


class Element:
    def __init__(self, eid: int, category: Optional[Category], comments: str = "") -> None:
        self.Id = ElementId(eid)
        self.Category = category
        self.comments = comments
        self.bbox: Optional[BoundingBox] = None
        self.solids: List[Any] = []
        self.Host: Optional[Element] = None

    def get_Parameter(self, which: str) -> Optional[_Param]:
        return _Param(self.comments) if which == "comments" else None

    def get_BoundingBox(self, view: Any) -> Optional["BoundingBox"]:
        return self.bbox

    def get_Geometry(self, opt: Any) -> List[Any]:
        return list(self.solids)


class BoundingBox:
    def __init__(self, lo: tuple, hi: tuple) -> None:
        self.Min, self.Max = XYZ(*lo), XYZ(*hi)


class Curve:
    def __init__(self, p0: tuple, p1: tuple) -> None:
        self.p0, self.p1 = XYZ(*p0), XYZ(*p1)

    def GetEndPoint(self, end: int) -> XYZ:
        return self.p0 if end == 0 else self.p1

    def Evaluate(self, t: float, normalized: bool) -> XYZ:
        return XYZ(
            self.p0.X + (self.p1.X - self.p0.X) * t,
            self.p0.Y + (self.p1.Y - self.p0.Y) * t,
            self.p0.Z + (self.p1.Z - self.p0.Z) * t,
        )


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
        self.Location = LocationCurve(Curve(p0, p1), {})
        self.WallType = _WallType(function)
        self.Orientation = XYZ(*orientation)
        self.Flipped = False
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
    def __init__(self, volume: float) -> None:
        self.Volume = volume

    def ComputeCentroid(self) -> XYZ:
        return XYZ(1.0, 2.0, 3.0)


class GeometryInstance:
    pass


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


class FilteredElementCollector:
    def __init__(self, document: "Document") -> None:
        self._doc = document
        self._cats: Optional[List[int]] = None

    def OfCategory(self, bic: int) -> "FilteredElementCollector":
        self._cats = [bic]
        return self

    def WhereElementIsNotElementType(self) -> "FilteredElementCollector":
        return self

    def WherePasses(self, flt: ElementMulticategoryFilter) -> "FilteredElementCollector":
        self._cats = flt.cats
        return self

    def __iter__(self) -> Iterator[Element]:
        for e in self._doc.elements:
            if self._cats is None or (e.Category is not None and e.Category.Id.Value in self._cats):
                yield e


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

    def GetElement(self, eid: ElementId) -> Optional[Element]:
        for e in self.elements:
            if e.Id.Value == eid.Value:
                return e
        return None

    def GetWarnings(self) -> List[_Failure]:
        return list(self._warnings)


Failure = _Failure


class _Stopwatch:
    ElapsedMilliseconds = 0


class Stopwatch:
    @staticmethod
    def StartNew() -> _Stopwatch:
        return _Stopwatch()


class _List(list):
    def Add(self, item: Any) -> None:
        self.append(item)


class _GenericList:
    def __getitem__(self, _: Any) -> Any:
        return _List


class App:
    VersionNumber = "2024"


@contextlib.contextmanager
def installed(monkeypatch: Any) -> Iterator[None]:
    """Make ``import clr / System / Autodesk.Revit.DB`` resolve to this stub for the duration of a test."""
    db = types.ModuleType("Autodesk.Revit.DB")
    for name in (
        "XYZ", "ElementId", "BuiltInParameter", "BuiltInCategory", "ViewDetailLevel", "BooleanOperationsType",
        "Options", "Wall", "LocationCurve", "WallUtils", "Solid", "GeometryInstance", "Mesh",
        "BooleanOperationsUtils", "ElementMulticategoryFilter", "FilteredElementCollector",
    ):
        setattr(db, name, globals()[name])
    modules = {
        "clr": types.ModuleType("clr"),
        "System": types.ModuleType("System"),
        "System.Collections": types.ModuleType("System.Collections"),
        "System.Collections.Generic": types.ModuleType("System.Collections.Generic"),
        "System.Diagnostics": types.ModuleType("System.Diagnostics"),
        "Autodesk": types.ModuleType("Autodesk"),
        "Autodesk.Revit": types.ModuleType("Autodesk.Revit"),
        "Autodesk.Revit.DB": db,
    }
    modules["System.Collections.Generic"].List = _GenericList()  # type: ignore[attr-defined]
    modules["System.Diagnostics"].Stopwatch = Stopwatch  # type: ignore[attr-defined]
    for name, mod in modules.items():
        monkeypatch.setitem(sys.modules, name, mod)
    yield


def run_script(script: str, document: Document) -> str:
    """Execute a built script like the add-in does (``doc`` and ``app`` in scope) and return ``__output__``."""
    scope: Dict[str, Any] = {"doc": document, "app": App(), "__output__": "", "__name__": "__ipy__"}
    exec(compile(script, "<embedded-script>", "exec"), scope)  # noqa: S102 - test-only stub execution
    return str(scope["__output__"])


