"""A small stand-in for the Revit API, big enough to run the revit_cleanup audit script under CPython.

It is NOT Revit. It proves the script's control flow, the line protocol and the arithmetic of its rules. It cannot prove
that the real Revit API behaves the way the stub assumes (see the UNVERIFIED list in revit_cleanup/module.py).

One trap of the real IronPython engine is copied on purpose: ``Name`` of an element TYPE raises AttributeError, and only
``Element.Name.GetValue(type)`` works. A script that reads ``symbol.Name`` therefore fails here too.
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


BuiltInParameter = _Enum()
BuiltInCategory = _Enum(
    OST_Walls=-2000011, OST_Floors=-2000032, OST_Rooms=-2000160, OST_Areas=-2000290, OST_Doors=-2000023,
    OST_Windows=-2000014, OST_Levels=-2000240, OST_Grids=-2000220, OST_GenericModel=-2000151, OST_Furniture=-2000080,
    OST_ProfileFamilies=-2000710, OST_StairsRailingBaluster=-2000138, OST_DoorTags=-2000450, OST_Lines=-2000051,
)


class Category:
    def __init__(self, bic: int, name: str) -> None:
        self.Id = ElementId(bic)
        self.Name = name


CAT = {
    "walls": Category(BuiltInCategory.OST_Walls, "Walls"), "doors": Category(BuiltInCategory.OST_Doors, "Doors"),
    "rooms": Category(BuiltInCategory.OST_Rooms, "Rooms"), "areas": Category(BuiltInCategory.OST_Areas, "Areas"),
    "furniture": Category(BuiltInCategory.OST_Furniture, "Furniture"), "levels": Category(BuiltInCategory.OST_Levels, "Levels"),
    "profiles": Category(BuiltInCategory.OST_ProfileFamilies, "Profiles"), "tags": Category(BuiltInCategory.OST_DoorTags, "Door Tags"),
    "generic": Category(BuiltInCategory.OST_GenericModel, "Generic Models"), "grids": Category(BuiltInCategory.OST_Grids, "Grids"),
}


class _NameSlot:
    """``Element.Name`` on the class is a property object with GetValue; on a type instance it raises (IronPython trap)."""

    def __get__(self, obj: Any, cls: Any) -> Any:
        if obj is None:
            return self
        if obj.is_type:
            raise AttributeError("'Name'")
        return obj._name

    @staticmethod
    def GetValue(element: Any) -> str:
        return element._name


class Element:
    Name = _NameSlot()

    def __init__(self, eid: int, name: str = "", category: Optional[Category] = None, type_el: Optional["Element"] = None) -> None:
        self.Id = ElementId(eid)
        self._name = name
        self.Category = category
        self.type_el = type_el
        self.is_type = False
        self.visible_in: set = set()
        self.Location: Any = None
        self.bbox: Optional[BoundingBox] = None
        self.dependents: Optional[List[Element]] = []

    def GetTypeId(self) -> ElementId:
        return self.type_el.Id if self.type_el is not None else ElementId(-1)

    def get_BoundingBox(self, view: Any) -> Optional["BoundingBox"]:
        return self.bbox

    def GetDependentElements(self, flt: Any) -> List[ElementId]:
        if self.dependents is None:
            raise RuntimeError("dependents cannot be read")
        return [d.Id for d in self.dependents if flt is None or flt.matches(d)]


class BoundingBox:
    def __init__(self, lo: tuple, hi: tuple) -> None:
        self.Min, self.Max = XYZ(*lo), XYZ(*hi)


class Curve:
    def __init__(self, p0: tuple, p1: tuple) -> None:
        self.p0, self.p1 = XYZ(*p0), XYZ(*p1)

    def GetEndPoint(self, end: int) -> XYZ:
        return self.p0 if end == 0 else self.p1

    def Evaluate(self, t: float, normalized: bool) -> XYZ:
        return XYZ(*(a + (b - a) * t for a, b in ((self.p0.X, self.p1.X), (self.p0.Y, self.p1.Y), (self.p0.Z, self.p1.Z))))


class LocationPoint:
    def __init__(self, point: tuple) -> None:
        self.Point = XYZ(*point)


class LocationCurve:
    def __init__(self, curve: Curve) -> None:
        self.Curve = curve


class Level(Element):
    def __init__(self, eid: int, name: str, elevation_ft: float) -> None:
        super().__init__(eid, name, CAT["levels"])
        self.Elevation = elevation_ft


class Grid(Element):
    def __init__(self, eid: int, name: str, p0: tuple, p1: tuple) -> None:
        super().__init__(eid, name, CAT["grids"])
        self.Curve = Curve(p0, p1)


class Dimension(Element):
    pass


class View(Element):
    def __init__(self, eid: int, name: str, view_type: str = "FloorPlan", template: bool = False) -> None:
        super().__init__(eid, name)
        self.ViewType, self.IsTemplate = view_type, template
        self.ViewTemplateId = ElementId(-1)
        self.dependent_views: List[View] = []

    def GetDependentViewIds(self) -> List[ElementId]:
        return [v.Id for v in self.dependent_views]


class ViewPlan(View):
    def __init__(self, eid: int, name: str, level: Optional[Level], view_type: str = "FloorPlan", template: bool = False) -> None:
        super().__init__(eid, name, view_type, template)
        self.GenLevel = level


class ViewSection(View):
    pass


class ViewDrafting(View):
    pass


class ViewSchedule(View):
    pass


class ViewSheet(View):
    def __init__(self, eid: int, number: str, name: str, placeholder: bool = False) -> None:
        super().__init__(eid, name, "DrawingSheet")
        self.SheetNumber, self.IsPlaceholder = number, placeholder
        self.placed: List[View] = []

    def GetAllPlacedViews(self) -> List[ElementId]:
        return [v.Id for v in self.placed]


class Viewport(Element):
    def __init__(self, eid: int, view: View, sheet: ViewSheet) -> None:
        super().__init__(eid)
        self.ViewId = view.Id
        self.visible_in.add(sheet.Id.Value)


class ScheduleSheetInstance(Element):
    def __init__(self, eid: int, schedule: View, sheet: ViewSheet) -> None:
        super().__init__(eid)
        self.ScheduleId = schedule.Id
        self.visible_in.add(sheet.Id.Value)


class ViewFamilyType(Element):
    def __init__(self, eid: int, name: str, default_template: Optional[View] = None) -> None:
        super().__init__(eid, name)
        self.is_type = True
        self.DefaultTemplateId = default_template.Id if default_template is not None else ElementId(-1)


class ImportInstance(Element):
    def __init__(self, eid: int, type_el: Element, linked: bool, view: Optional[View] = None) -> None:
        super().__init__(eid, "", None, type_el)
        self.IsLinked = linked
        self.OwnerViewId = view.Id if view is not None else ElementId(-1)
        if view is not None:
            self.visible_in.add(view.Id.Value)


class GroupType(Element):
    def __init__(self, eid: int, name: str) -> None:
        super().__init__(eid, name)
        self.is_type = True


class Group(Element):
    def __init__(self, eid: int, group_type: GroupType) -> None:
        super().__init__(eid, "", None, group_type)
        self.GroupType = group_type


class CurveElement(Element):
    def __init__(self, eid: int, kind: str, view: View) -> None:
        super().__init__(eid, "", CAT["generic"])
        self.CurveElementType, self.OwnerViewId = kind, view.Id
        self.visible_in.add(view.Id.Value)


class Family(Element):
    def __init__(self, eid: int, name: str, category: Optional[Category] = None, in_place: bool = False) -> None:
        super().__init__(eid, name)
        self.FamilyCategory, self.IsInPlace = category, in_place
        self.symbols: List[FamilySymbol] = []

    def GetFamilySymbolIds(self) -> List[ElementId]:
        return [s.Id for s in self.symbols]


class FamilySymbol(Element):
    def __init__(self, eid: int, name: str, family: Family) -> None:
        super().__init__(eid, name)
        self.is_type = True
        self.Family = family
        family.symbols.append(self)
        self.Category = family.FamilyCategory


class Room(Element):
    def __init__(self, eid: int, name: str, placed: bool = True, area: float = 120.0, category: Optional[Category] = None) -> None:
        super().__init__(eid, name, category or CAT["rooms"])
        self.Location = LocationPoint((1.0, 1.0, 0.0)) if placed else None
        self.Area = area


class Failure:
    def __init__(self, description: str, failing: List[int], severity: str = "Warning") -> None:
        self._d, self._f, self._s = description, failing, severity

    def GetDescriptionText(self) -> str:
        return self._d

    def GetFailingElements(self) -> List[ElementId]:
        return [ElementId(i) for i in self._f]

    def GetSeverity(self) -> str:
        return self._s


class Document:
    Title = "Villa.rvt"
    CreationGUID = "11111111-2222-3333-4444-555555555555"

    def __init__(self) -> None:
        self.elements: List[Element] = []
        self.warnings: List[Failure] = []
        self.broken_warnings = False
        self.mutations = 0

    def add(self, *items: Element) -> None:
        self.elements.extend(items)

    def GetElement(self, eid: ElementId) -> Optional[Element]:
        for e in self.elements:
            if e.Id.Value == eid.Value:
                return e
        return None

    def GetWarnings(self) -> List[Failure]:
        if self.broken_warnings:
            raise RuntimeError("warnings cannot be read")
        return list(self.warnings)


class ElementClassFilter:
    def __init__(self, cls: type) -> None:
        self.cls = cls

    def matches(self, e: Element) -> bool:
        return isinstance(e, self.cls)


class ElementMulticategoryFilter:
    def __init__(self, cats: List[int]) -> None:
        self.cats = list(cats)


class ElementLevelFilter:
    def __init__(self, level_id: ElementId) -> None:
        self.level = level_id.Value


class FilteredElementCollector:
    def __init__(self, document: Document, view_id: Optional[ElementId] = None) -> None:
        self._doc, self._view = document, (view_id.Value if view_id is not None else None)
        self._cls: Optional[type] = None
        self._cats: Optional[List[int]] = None
        self._level: Optional[int] = None
        self._not_types = False

    def OfClass(self, cls: type) -> "FilteredElementCollector":
        self._cls = cls
        return self

    def OfCategory(self, bic: int) -> "FilteredElementCollector":
        self._cats = [bic]
        return self

    def WhereElementIsNotElementType(self) -> "FilteredElementCollector":
        self._not_types = True
        return self

    def WherePasses(self, flt: Any) -> "FilteredElementCollector":
        if isinstance(flt, ElementMulticategoryFilter):
            self._cats = flt.cats
        elif isinstance(flt, ElementLevelFilter):
            self._level = flt.level
        return self

    def _ok(self, e: Element) -> bool:
        if self._not_types and e.is_type:
            return False
        if self._cls is not None and not isinstance(e, self._cls):
            return False
        if self._cats is not None and not (e.Category is not None and e.Category.Id.Value in self._cats):
            return False
        if self._level is not None and not (getattr(e, "LevelId", None) is not None and e.LevelId.Value == self._level):
            return False
        if self._view is not None and self._view not in e.visible_in:
            return False
        return True

    def __iter__(self) -> Iterator[Element]:
        return iter([e for e in self._doc.elements if self._ok(e)])

    def GetElementCount(self) -> int:
        return len(list(iter(self)))


class _Stopwatch:
    def __init__(self) -> None:
        self.reads = 0

    @property
    def ElapsedMilliseconds(self) -> int:
        self.reads += 1
        return self.reads * Stopwatch.tick


class Stopwatch:
    tick = 0

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


_EXPORTS = (
    "XYZ", "ElementId", "BuiltInParameter", "BuiltInCategory", "Element", "Level", "Grid", "Dimension", "View", "ViewPlan",
    "ViewSection", "ViewDrafting", "ViewSchedule", "ViewSheet", "Viewport", "ScheduleSheetInstance", "ViewFamilyType",
    "ImportInstance", "GroupType", "Group", "CurveElement", "Family", "FamilySymbol", "Room", "ElementClassFilter",
    "ElementMulticategoryFilter", "ElementLevelFilter", "FilteredElementCollector", "LocationPoint", "LocationCurve",
)


@contextlib.contextmanager
def installed(monkeypatch: Any) -> Iterator[None]:
    """Make ``import clr / System / Autodesk.Revit.DB`` resolve to this stub for the duration of a test."""
    db = types.ModuleType("Autodesk.Revit.DB")
    for name in _EXPORTS:
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
    Stopwatch.tick = 0
    yield
    Stopwatch.tick = 0


def run_script(script: str, document: Document) -> str:
    """Execute a built script like the add-in does (``doc`` and ``app`` in scope) and return ``__output__``."""
    scope: Dict[str, Any] = {"doc": document, "app": App(), "__output__": "", "__name__": "__ipy__"}
    exec(compile(script, "<embedded-script>", "exec"), scope)  # noqa: S102 - test-only stub execution
    return str(scope["__output__"])


def box(lo: tuple, hi: tuple) -> BoundingBox:
    return BoundingBox(lo, hi)


def wall(eid: int, p0: tuple, p1: tuple, type_el: Element, z: tuple = (0.0, 10.0), thickness: float = 0.5) -> Element:
    w = Element(eid, "", CAT["walls"], type_el)
    w.Location = LocationCurve(Curve(p0, p1))
    w.bbox = box((min(p0[0], p1[0]) - thickness / 2, min(p0[1], p1[1]) - thickness / 2, z[0]),
                 (max(p0[0], p1[0]) + thickness / 2, max(p0[1], p1[1]) + thickness / 2, z[1]))
    return w


def point_element(eid: int, point: tuple, type_el: Element, category: Category) -> Element:
    e = Element(eid, "", category, type_el)
    e.Location = LocationPoint(point)
    e.bbox = box((point[0] - 1, point[1] - 1, point[2]), (point[0] + 1, point[1] + 1, point[2] + 7))
    return e

