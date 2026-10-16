"""Stand-in for the Revit API, big enough to run the revit_mep hanger scripts under CPython.

It builds on ``revit_api_stub`` and ``revit_mep_stub`` (pipes, ducts, fittings, connectors, transactions with an undo
journal, Extensible Storage) and adds what hangers need: cable trays, box shaped hosts (floors, beams, ceilings) in the
active model and in a linked model, a ``ReferenceIntersector`` that casts a ray straight up, level based hanger families
with instance parameters, ``NewFamilyInstance`` and ``ElementTransformUtils.RotateElement``, and a collector that takes a
view.

It is NOT Revit. It proves the scripts' control flow, arithmetic, budgets, the rule handling, the idempotent placement,
rollback and the line protocol; it cannot prove that Revit accepts the same calls (see the module docstring of revit_mep).
"""
from __future__ import annotations

import contextlib
import math
import sys
import types
from typing import Any, Dict, Iterator, List, Optional, Tuple

import revit_api_stub as stub
import revit_mep_stub as rs
from revit_api_stub import XYZ, Category, ElementId

M = 0.3048  # metres per foot
Vec = Tuple[float, float, float]

BuiltInCategory = types.SimpleNamespace(
    **stub.BuiltInCategory.__dict__, OST_CableTray=-2008130, OST_CableTrayFitting=-2008131, OST_ConduitFitting=-2008133,
    OST_StructuralFraming=-2001320, OST_Ceilings=-2000038, OST_SpecialityEquipment=-2001350, OST_RvtLinks=-2001352,
)
BuiltInParameter = types.SimpleNamespace(
    **rs.BuiltInParameter.__dict__, RBS_PIPE_OUTER_DIAMETER="pipe_od", RBS_CABLETRAY_WIDTH_PARAM="tray_w",
    RBS_CABLETRAY_HEIGHT_PARAM="tray_h", RBS_REFERENCE_INSULATION_THICKNESS="insul", RBS_SYSTEM_NAME_PARAM="sys_name",
    RBS_START_LEVEL_PARAM="start_level",
)


def ft(p: Vec) -> Vec:
    """A point in metres -> feet."""
    return (p[0] / M, p[1] / M, p[2] / M)


# --------------------------------------------------------------------------- #
# Hosts, links, rays
# --------------------------------------------------------------------------- #
class HostBox(stub.Element):
    """A floor, beam or ceiling as a box (feet). A ray from below hits its underside."""

    def __init__(self, eid: int, bic: int, name: str, lo: Vec, hi: Vec) -> None:
        super().__init__(eid, Category(bic, name))
        self.bbox = stub.BoundingBox(lo, hi)
        self.lo, self.hi = lo, hi


class LinkDoc(stub.Document):
    Title = "Linked.rvt"


class HLink(stub.Element):
    def __init__(self, eid: int, name: str, link_doc: LinkDoc, offset: Vec) -> None:
        super().__init__(eid, Category(BuiltInCategory.OST_RvtLinks, "RVT Links"))
        self.Name, self._doc, self.offset = name, link_doc, offset

    def GetLinkDocument(self) -> LinkDoc:
        return self._doc

    def GetTotalTransform(self) -> Any:
        return types.SimpleNamespace(OfPoint=lambda p: XYZ(p.X + self.offset[0], p.Y + self.offset[1], p.Z + self.offset[2]))


class _Reference:
    def __init__(self, element_id: ElementId, linked_id: ElementId) -> None:
        self.ElementId, self.LinkedElementId = element_id, linked_id


class _WithContext:
    def __init__(self, proximity: float, ref: _Reference) -> None:
        self.Proximity, self._ref = proximity, ref

    def GetReference(self) -> _Reference:
        return self._ref


class FindReferenceTarget:
    Element = "Element"


class ReferenceIntersector:
    """Ray straight up against HostBox elements of the chosen categories, in the model and (when asked) in its links."""

    rays = 0

    def __init__(self, flt: Any, target: Any, view: Any) -> None:
        self.cats = list(flt.cats)
        self.view = view
        self.FindReferencesInRevitLinks = False

    @staticmethod
    def _hit(box: HostBox, origin: XYZ, offset: Vec) -> Optional[float]:
        lo = [box.lo[i] + offset[i] for i in range(3)]
        hi = [box.hi[i] + offset[i] for i in range(3)]
        if not (lo[0] <= origin.X <= hi[0] and lo[1] <= origin.Y <= hi[1]):
            return None
        if origin.Z > lo[2]:
            return None  # starts inside or above: no underside to hit
        return lo[2] - origin.Z

    def Find(self, origin: XYZ, direction: XYZ) -> List[_WithContext]:
        ReferenceIntersector.rays += 1
        assert direction.Z == 1.0 and direction.X == 0.0 and direction.Y == 0.0
        world = rs.WORLD["w"]
        out: List[_WithContext] = []
        for e in world.elements:
            if isinstance(e, HostBox) and e.Category.Id.Value in self.cats:
                d = self._hit(e, origin, (0.0, 0.0, 0.0))
                if d is not None:
                    out.append(_WithContext(d, _Reference(e.Id, ElementId(-1))))
            elif isinstance(e, HLink) and self.FindReferencesInRevitLinks:
                for le in e.GetLinkDocument().elements:
                    if isinstance(le, HostBox) and le.Category.Id.Value in self.cats:
                        d = self._hit(le, origin, e.offset)
                        if d is not None:
                            out.append(_WithContext(d, _Reference(e.Id, le.Id)))
        out.sort(key=lambda r: r.Proximity)
        return out


# --------------------------------------------------------------------------- #
# Cable trays
# --------------------------------------------------------------------------- #
class StubTray(rs.PipeLike):
    domain = "DomainElectrical"
    kind_word = "tray"
    cat_bic = BuiltInCategory.OST_CableTray
    size_key = BuiltInParameter.RBS_CABLETRAY_WIDTH_PARAM
    sys_key = "tray_sys"

    def _add_size_params(self) -> None:
        self.parameters[BuiltInParameter.RBS_CABLETRAY_WIDTH_PARAM] = rs.Param(self, BuiltInParameter.RBS_CABLETRAY_WIDTH_PARAM, 0.5)
        self.parameters[BuiltInParameter.RBS_CABLETRAY_HEIGHT_PARAM] = rs.Param(self, BuiltInParameter.RBS_CABLETRAY_HEIGHT_PARAM, 0.1)

    def apply_param(self, key: str, value: Any) -> None:
        pass


# --------------------------------------------------------------------------- #
# Hanger families
# --------------------------------------------------------------------------- #
class HFamily(stub.Family):
    def __init__(self, eid: int, name: str, category: Category, placement: str, params: Dict[str, Tuple[Any, str, bool]], connectors: bool) -> None:
        super().__init__(eid, name, category)
        self.FamilyPlacementType, self.instance_params, self.has_connectors = placement, params, connectors


class HSymbol(stub.FamilySymbol):
    def __init__(self, eid: int, name: str, family: HFamily) -> None:
        super().__init__(eid, name, family)
        self.IsActive = False

    def Activate(self) -> None:
        self.IsActive = True


class HInstance(rs.Taggable, stub.FamilyInstance):
    def __init__(self, eid: int, symbol: HSymbol, point: Vec, level: Any) -> None:
        stub.FamilyInstance.__init__(self, eid, Category(BuiltInCategory.OST_GenericModel, "Generic Models"), point, None, symbol=symbol)
        self._init_taggable()
        self.parameters = {"comments": rs.Param(self, "comments", "", "String")}
        self.named = {n: rs.Param(self, n, v, kind, ro) for n, (v, kind, ro) in symbol.Family.instance_params.items()}
        self.LevelId = level.Id
        self.angle = 0.0
        self.HandOrientation, self.FacingOrientation = XYZ(1.0, 0.0, 0.0), XYZ(0.0, 1.0, 0.0)
        if symbol.Family.has_connectors:
            self.MEPModel = types.SimpleNamespace(ConnectorManager=rs.ConnManager([rs.MepConnector("DomainPiping", point, "Vent")]))

    @property
    def Parameters(self) -> List[Any]:
        return [types.SimpleNamespace(Definition=types.SimpleNamespace(Name=n)) for n in self.named]

    def apply_param(self, key: str, value: Any) -> None:
        pass


class ElementTransformUtils:
    @staticmethod
    def RotateElement(document: Any, element_id: ElementId, axis: Any, angle: float) -> None:
        w = rs.WORLD["w"]
        inst = w.GetElement(element_id)
        before = (inst.HandOrientation, inst.FacingOrientation, inst.angle)
        c, s = math.cos(angle), math.sin(angle)

        def turn(v: XYZ) -> XYZ:
            return XYZ(c * v.X - s * v.Y, s * v.X + c * v.Y, v.Z)

        inst.HandOrientation, inst.FacingOrientation, inst.angle = turn(inst.HandOrientation), turn(inst.FacingOrientation), inst.angle + angle

        def undo() -> None:
            inst.HandOrientation, inst.FacingOrientation, inst.angle = before

        w.log(undo)


class _HCreator(rs._Creator):
    def NewFamilyInstance(self, point: XYZ, symbol: HSymbol, level: Any, structural: Any) -> HInstance:
        w = self.w
        w.maybe_fail("place_hanger")
        if not symbol.IsActive:
            raise RuntimeError("the family symbol is not active")
        inst = HInstance(w.next_id(), symbol, (point.X, point.Y, point.Z), level)
        w.add(inst)
        return inst


class HCollector(rs.Collector):
    def __init__(self, document: Any, view_id: Any = None) -> None:
        super().__init__(document)
        self._view = None if view_id is None else view_id.Value

    def _matches(self, e: Any) -> bool:
        if self._view is not None and e.Id.Value not in rs.WORLD["w"].view_members.get(self._view, ()):
            return False
        return super()._matches(e)


class HWorld(rs.World):
    def __init__(self) -> None:
        super().__init__()
        self.Create = _HCreator(self)
        self.view_members: Dict[int, List[int]] = {}

    # -- scene helpers (metres) ------------------------------------------------ #
    def put(self, e: Any) -> Any:
        self.elements.append(e)
        return e

    def view3d(self) -> stub.View3D:
        return self.put(stub.View3D(self.next_id()))

    def host(self, kind: str, lo: Vec, hi: Vec, into: Optional[stub.Document] = None, name: str = "") -> HostBox:
        bic = {"floor": BuiltInCategory.OST_Floors, "beam": BuiltInCategory.OST_StructuralFraming, "ceiling": BuiltInCategory.OST_Ceilings}[kind]
        box = HostBox(self.next_id(), bic, name or kind, ft(lo), ft(hi))
        (into if into is not None else self).elements.append(box)
        return box

    def link(self, offset_m: Vec = (0.0, 0.0, 0.0)) -> Tuple[HLink, LinkDoc]:
        ld = LinkDoc()
        li = self.put(HLink(self.next_id(), "Structure link", ld, ft(offset_m)))
        return li, ld

    def pipe(self, p0_m: Vec, p1_m: Vec, dia_mm: float = 32.0, level: int = 0, system_name: str = "", insulation_mm: float = 0.0) -> rs.StubPipe:
        p = rs.StubPipe(self.next_id(), ft(p0_m), ft(p1_m), "SupplyHydronic", 0, 0, level)
        p.parameters[rs.BuiltInParameter.RBS_PIPE_DIAMETER_PARAM].value = dia_mm / 304.8
        p.diameter = dia_mm / 304.8
        if insulation_mm:
            p.parameters[BuiltInParameter.RBS_REFERENCE_INSULATION_THICKNESS] = rs.Param(p, BuiltInParameter.RBS_REFERENCE_INSULATION_THICKNESS, insulation_mm / 304.8)
        if system_name:
            p.parameters[BuiltInParameter.RBS_SYSTEM_NAME_PARAM] = rs.Param(p, BuiltInParameter.RBS_SYSTEM_NAME_PARAM, system_name, "String")
        return self.put(p)

    def duct(self, p0_m: Vec, p1_m: Vec, width_mm: float = 0.0, height_mm: float = 0.0, dia_mm: float = 200.0) -> rs.StubDuct:
        d = rs.StubDuct(self.next_id(), ft(p0_m), ft(p1_m), "SupplyAir", 0, 0, 0)
        if width_mm:
            d.apply_param(rs.BuiltInParameter.RBS_CURVE_WIDTH_PARAM, width_mm / 304.8)
            d.apply_param(rs.BuiltInParameter.RBS_CURVE_HEIGHT_PARAM, height_mm / 304.8)
            d.parameters[rs.BuiltInParameter.RBS_CURVE_WIDTH_PARAM].value = width_mm / 304.8
            d.parameters[rs.BuiltInParameter.RBS_CURVE_HEIGHT_PARAM].value = height_mm / 304.8
        else:
            d.parameters[rs.BuiltInParameter.RBS_CURVE_DIAMETER_PARAM].value = dia_mm / 304.8
        return self.put(d)

    def tray(self, p0_m: Vec, p1_m: Vec, width_mm: float = 300.0, height_mm: float = 60.0) -> StubTray:
        t = StubTray(self.next_id(), ft(p0_m), ft(p1_m), "PowerCircuit", 0, 0, 0)
        t.parameters[BuiltInParameter.RBS_CABLETRAY_WIDTH_PARAM].value = width_mm / 304.8
        t.parameters[BuiltInParameter.RBS_CABLETRAY_HEIGHT_PARAM].value = height_mm / 304.8
        return self.put(t)

    def fit_at(self, run: rs.PipeLike, end: int) -> rs.Fitting:
        """An elbow fitting connected to one end (0 or 1) of a pipe or duct."""
        conn = run.c0 if end == 0 else run.c1
        fc = rs.MepConnector(conn.Domain, (conn.Origin.X, conn.Origin.Y, conn.Origin.Z), conn.sys, conn.Radius)
        f = rs.Fitting(self.next_id(), conn.Domain, [fc], "pipe")
        self.put(f)
        conn.ConnectTo(fc)
        return f

    def tap_at(self, run: rs.PipeLike, along_m: float) -> rs.Fitting:
        """A tap fitting on the run at a distance from its start: an extra connector of the run that is connected."""
        p0, p1 = (run.Location.Curve.p0.X, run.Location.Curve.p0.Y, run.Location.Curve.p0.Z), (run.Location.Curve.p1.X, run.Location.Curve.p1.Y, run.Location.Curve.p1.Z)
        n = math.dist(p0, p1)
        d = tuple((p1[i] - p0[i]) / n for i in range(3))
        pt = tuple(p0[i] + d[i] * along_m / M for i in range(3))
        tap = rs.MepConnector(run.c0.Domain, pt, run.c0.sys, run.c0.Radius, owner=run)
        run.ConnectorManager.Connectors.append(tap)
        fc = rs.MepConnector(run.c0.Domain, pt, run.c0.sys, run.c0.Radius)
        f = rs.Fitting(self.next_id(), run.c0.Domain, [fc], "pipe")
        self.put(f)
        tap.ConnectTo(fc)
        return f

    def hanger_family(self, name: str = "Rod hanger", type_name: str = "Standard", category: Optional[int] = None, placement: str = "OneLevelBased",
                      params: Optional[Dict[str, Tuple[Any, str, bool]]] = None, connectors: bool = False) -> HSymbol:
        bic = BuiltInCategory.OST_GenericModel if category is None else category
        params = params if params is not None else {"Rod length": (0.0, "Double", False)}
        fam = self.put(HFamily(self.next_id(), name, Category(bic, "Cat"), placement, params, connectors))
        return self.put(HSymbol(self.next_id(), type_name, fam))

    def instances_of(self, symbol: HSymbol) -> List[HInstance]:
        return [e for e in self.elements if isinstance(e, HInstance) and e.Symbol is symbol]


@contextlib.contextmanager
def installed_hangers(monkeypatch: Any) -> Iterator[HWorld]:
    """installed_mep, with a world that places hanger families, plus rays, hosts, links, trays and views."""
    monkeypatch.setattr(rs, "World", HWorld)
    monkeypatch.setattr(stub.Line, "CreateBound", staticmethod(lambda a, b: stub.Line((a.X, a.Y, a.Z), (b.X, b.Y, b.Z))), raising=False)
    with rs.installed_mep(monkeypatch) as world:
        db = sys.modules["Autodesk.Revit.DB"]
        for name, value in {
            "BuiltInCategory": BuiltInCategory, "BuiltInParameter": BuiltInParameter, "FilteredElementCollector": HCollector,
            "ReferenceIntersector": ReferenceIntersector, "FindReferenceTarget": FindReferenceTarget, "View3D": stub.View3D,
            "ElementTransformUtils": ElementTransformUtils, "Element": stub.Element,
        }.items():
            setattr(db, name, value)
        structure = types.ModuleType("Autodesk.Revit.DB.Structure")
        structure.StructuralType = rs._Names("NonStructural")  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "Autodesk.Revit.DB.Structure", structure)
        ReferenceIntersector.rays = 0
        yield world  # type: ignore[misc]
