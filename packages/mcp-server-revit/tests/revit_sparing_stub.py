"""Stand-in for the Revit API, big enough to run the revit_sparing scripts under CPython.

It builds on ``revit_api_stub`` (elements, collector, line protocol) and ``revit_mep_stub`` (transactions with an undo
journal, Extensible Storage, failure injection) and adds what sparingen need: box solids with holes that answer
IntersectWithCurve, walls and floors made of them, straight MEP curves with size parameters, linked models with a
rotation + translation transform, native openings that cut a hole, sparing families of the four placement types and
the bounding-box filter.

It is NOT Revit. It proves the scripts' control flow, arithmetic, budgets, ownership/replace rules, rollback and the
line protocol; it cannot prove that Revit accepts the same calls (see the module docstring of revit_sparing).
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

MM = 304.8  # millimetres per foot
Vec = Tuple[float, float, float]

BuiltInCategory = types.SimpleNamespace(
    **stub.BuiltInCategory.__dict__, OST_Conduit=-2008132, OST_CableTray=-2008130, OST_StructuralFraming=-2001320,
    OST_SWallRectOpening=-2000999, OST_FloorOpening=-2000898, OST_RvtLinks=-2001352, OST_SpecialityEquipment=-2001350,
)
BuiltInParameter = types.SimpleNamespace(
    **rs.BuiltInParameter.__dict__, RBS_PIPE_OUTER_DIAMETER="pipe_od", RBS_CONDUIT_OUTER_DIAM_PARAM="conduit_od",
    RBS_CONDUIT_DIAMETER_PARAM="conduit_d", RBS_CABLETRAY_WIDTH_PARAM="tray_w", RBS_CABLETRAY_HEIGHT_PARAM="tray_h",
    RBS_REFERENCE_INSULATION_THICKNESS="insul", RBS_SYSTEM_NAME_PARAM="sys_name", RBS_START_LEVEL_PARAM="start_level",
    FLOOR_ATTR_THICKNESS_PARAM="floor_t", ROOF_ATTR_THICKNESS_PARAM="roof_t", RBS_CTC_SERVICE_TYPE="service",
)


def ft(p: Vec) -> Vec:
    """A point or length triple in millimetres -> feet."""
    return (p[0] / MM, p[1] / MM, p[2] / MM)


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a: Vec) -> Vec:
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def _t(p: Any) -> Vec:
    return (p.X, p.Y, p.Z)


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
class Transform:
    """Rotation about Z by ``angle`` (radians), then a translation by ``origin`` (feet)."""

    def __init__(self, angle: float = 0.0, origin: Vec = (0.0, 0.0, 0.0)) -> None:
        self.angle, self.origin = angle, origin

    @property
    def IsIdentity(self) -> bool:
        return abs(self.angle) < 1e-12 and self.origin == (0.0, 0.0, 0.0)

    def _rot(self, v: Vec, angle: float) -> Vec:
        c, s = math.cos(angle), math.sin(angle)
        return (c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])

    def OfVector(self, v: XYZ) -> XYZ:
        return XYZ(*self._rot(_t(v), self.angle))

    def OfPoint(self, p: XYZ) -> XYZ:
        r = self._rot(_t(p), self.angle)
        return XYZ(r[0] + self.origin[0], r[1] + self.origin[1], r[2] + self.origin[2])

    @property
    def Origin(self) -> XYZ:
        return XYZ(*self.origin)

    @property
    def BasisX(self) -> XYZ:
        return self.OfVector(XYZ(1.0, 0.0, 0.0))

    @property
    def Determinant(self) -> float:
        return 1.0

    @property
    def Inverse(self) -> "Transform":
        back = self._rot(self.origin, -self.angle)
        return Transform(-self.angle, (-back[0], -back[1], -back[2]))


class SLine(stub.Line):
    @staticmethod
    def CreateBound(a: XYZ, b: XYZ) -> "SLine":
        return SLine(_t(a), _t(b))


class _Result:
    def __init__(self, segments: List[SLine]) -> None:
        self._segments = segments

    @property
    def SegmentCount(self) -> int:
        return len(self._segments)

    def GetCurveSegment(self, i: int) -> SLine:
        return self._segments[i]


class _Ref:
    def __init__(self, owner: Any, key: str, link: Any = None) -> None:
        self.owner, self.key, self.link = owner, key, link

    def CreateLinkReference(self, link: Any) -> "_Ref":
        return _Ref(self.owner, self.key, link)


class _Face:
    def __init__(self, solid: "BoxSolid", axis: int, sign: float) -> None:
        self.solid, self.axis, self.sign = solid, axis, sign
        n = solid.axes[axis]
        self.FaceNormal = XYZ(n[0] * sign, n[1] * sign, n[2] * sign)
        self.Reference = _Ref(solid.owner, "%s%d" % ("+" if sign > 0 else "-", axis))

    def Project(self, pt: XYZ) -> Any:
        s = self.solid
        q = list(s.local(_t(pt)))
        for i in range(3):
            if i != self.axis and abs(q[i]) > s.half[i] + 1e-9:
                return None
        dist = abs(q[self.axis] - self.sign * s.half[self.axis])
        q[self.axis] = self.sign * s.half[self.axis]
        return types.SimpleNamespace(XYZPoint=XYZ(*s.world(tuple(q))), Distance=dist)


def _clip(la: Vec, lb: Vec, lo: Vec, hi: Vec) -> Optional[Tuple[float, float]]:
    t0, t1 = 0.0, 1.0
    for i in range(3):
        d = lb[i] - la[i]
        if abs(d) < 1e-12:
            if la[i] < lo[i] or la[i] > hi[i]:
                return None
            continue
        ta, tb = (lo[i] - la[i]) / d, (hi[i] - la[i]) / d
        t0, t1 = max(t0, min(ta, tb)), min(t1, max(ta, tb))
        if t0 > t1:
            return None
    return t0, t1


class BoxSolid:
    """An oriented box (centre, three unit axes, half sizes, all in feet) with box-shaped holes in local coordinates."""

    def __init__(self, centre: Vec, axes: List[Vec], half: Vec, holes: Optional[List[Tuple[Vec, Vec]]] = None, owner: Any = None) -> None:
        self.centre, self.axes, self.half = centre, [_unit(a) for a in axes], half
        self.holes: List[Tuple[Vec, Vec]] = holes if holes is not None else []
        self.owner = owner

    @property
    def Volume(self) -> float:
        return 8.0 * self.half[0] * self.half[1] * self.half[2]

    def local(self, p: Vec) -> Vec:
        d = _sub(p, self.centre)
        return (_dot(d, self.axes[0]), _dot(d, self.axes[1]), _dot(d, self.axes[2]))

    def world(self, q: Vec) -> Vec:
        return tuple(self.centre[i] + sum(q[k] * self.axes[k][i] for k in range(3)) for i in range(3))  # type: ignore[return-value]

    def corners(self) -> List[Vec]:
        h = self.half
        return [self.world((sx * h[0], sy * h[1], sz * h[2])) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]

    @property
    def Faces(self) -> List[_Face]:
        return [_Face(self, axis, sign) for axis in range(3) for sign in (1.0, -1.0)]

    def IntersectWithCurve(self, line: SLine, options: Any) -> _Result:
        a, b = _t(line.p0), _t(line.p1)
        la, lb = self.local(a), self.local(b)
        span = _clip(la, lb, tuple(-x for x in self.half), self.half)  # type: ignore[arg-type]
        if span is None:
            return _Result([])
        pieces = [span]
        for lo, hi in self.holes:
            cut = _clip(la, lb, lo, hi)
            if cut is None:
                continue
            nxt = []
            for s0, s1 in pieces:
                if cut[1] <= s0 or cut[0] >= s1:
                    nxt.append((s0, s1))
                    continue
                if cut[0] > s0:
                    nxt.append((s0, cut[0]))
                if cut[1] < s1:
                    nxt.append((cut[1], s1))
            pieces = nxt

        def at(s: float) -> Vec:
            return (a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s, a[2] + (b[2] - a[2]) * s)

        return _Result([SLine(at(s0), at(s1)) for s0, s1 in pieces if s1 - s0 > 1e-9])

    def transformed(self, t: Transform) -> "BoxSolid":
        return BoxSolid(_t(t.OfPoint(XYZ(*self.centre))), [_t(t.OfVector(XYZ(*a))) for a in self.axes], self.half, list(self.holes), self.owner)

    def bbox(self) -> stub.BoundingBox:
        pts = self.corners()
        return stub.BoundingBox(tuple(min(p[i] for p in pts) for i in range(3)), tuple(max(p[i] for p in pts) for i in range(3)))


class SolidUtils:
    @staticmethod
    def CreateTransformed(solid: BoxSolid, t: Transform) -> BoxSolid:
        return solid.transformed(t)


class SolidCurveIntersectionOptions:
    pass


class Outline:
    def __init__(self, lo: XYZ, hi: XYZ) -> None:
        self.lo, self.hi = _t(lo), _t(hi)


class BoundingBoxIntersectsFilter:
    def __init__(self, outline: Outline) -> None:
        self.outline = outline


class BasePoint:
    @staticmethod
    def GetProjectBasePoint(document: Any) -> Any:
        return types.SimpleNamespace(Position=XYZ(*document.pbp))


class ElementTransformUtils:
    @staticmethod
    def RotateElement(document: Any, element_id: ElementId, axis: Any, angle: float) -> None:
        e = document.GetElement(element_id)
        old = (e.FacingOrientation, e.HandOrientation)
        rot = Transform(angle)
        e.FacingOrientation, e.HandOrientation = rot.OfVector(old[0]), rot.OfVector(old[1])
        rs.WORLD["w"].log(lambda: (setattr(e, "FacingOrientation", old[0]), setattr(e, "HandOrientation", old[1])))


# --------------------------------------------------------------------------- #
# Elements
# --------------------------------------------------------------------------- #
class SWall(stub.Element):
    """A straight wall from p0 to p1 (mm, at the base), height and width in mm."""

    def __init__(self, eid: int, p0: Vec, p1: Vec, height: float = 3000.0, width: float = 200.0) -> None:
        super().__init__(eid, Category(BuiltInCategory.OST_Walls, "Walls"))
        a, b = ft(p0), ft(p1)
        self.Location = types.SimpleNamespace(Curve=SLine(a, b))
        d = _unit(_sub(b, a))
        self.Orientation = XYZ(d[1], -d[0], 0.0)
        self.Width = width / MM
        centre = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, a[2] + height / MM / 2)
        length = math.sqrt(_dot(_sub(b, a), _sub(b, a)))
        self.solid = BoxSolid(centre, [d, (d[1], -d[0], 0.0), (0.0, 0.0, 1.0)], (length / 2, self.Width / 2, height / MM / 2), owner=self)
        self.solids = [self.solid]
        self.bbox = self.solid.bbox()


class SFloor(stub.Element):
    """A flat floor: rectangle lo..hi (mm, x and y), top at top_z, thickness in mm."""

    def __init__(self, eid: int, lo: Tuple[float, float], hi: Tuple[float, float], top_z: float, thickness: float = 250.0,
                 roof: bool = False) -> None:
        cat = Category(BuiltInCategory.OST_Roofs, "Roofs") if roof else Category(BuiltInCategory.OST_Floors, "Floors")
        super().__init__(eid, cat)
        t = thickness / MM
        centre = ((lo[0] + hi[0]) / 2 / MM, (lo[1] + hi[1]) / 2 / MM, top_z / MM - t / 2)
        half = ((hi[0] - lo[0]) / 2 / MM, (hi[1] - lo[1]) / 2 / MM, t / 2)
        self.solid = BoxSolid(centre, [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)], half, owner=self)
        self.solids = [self.solid]
        self.bbox = self.solid.bbox()
        self.set_param(BuiltInParameter.ROOF_ATTR_THICKNESS_PARAM if roof else BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM, t, "Double")


MEP_BIC = {"pipes": (BuiltInCategory.OST_PipeCurves, "Pipes"), "ducts": (BuiltInCategory.OST_DuctCurves, "Ducts"),
           "conduits": (BuiltInCategory.OST_Conduit, "Conduits"), "cabletrays": (BuiltInCategory.OST_CableTray, "Cable Trays")}


class SMep(stub.Element):
    """A straight pipe, duct, conduit or cable tray. Sizes in mm: diameter, or width and height."""

    def __init__(self, eid: int, cat: str, p0: Vec, p1: Vec, diameter: float = 0.0, width: float = 0.0, height: float = 0.0,
                 insulation: float = 0.0, system: str = "", level: Any = None) -> None:
        bic, name = MEP_BIC[cat]
        super().__init__(eid, Category(bic, name))
        a, b = ft(p0), ft(p1)
        self.Location = types.SimpleNamespace(Curve=SLine(a, b))
        self.ReferenceLevel = level
        bp = BuiltInParameter
        if cat == "pipes":
            self.set_param(bp.RBS_PIPE_DIAMETER_PARAM, diameter / MM, "Double")
        elif cat == "ducts" and diameter:
            self.set_param(bp.RBS_CURVE_DIAMETER_PARAM, diameter / MM, "Double")
        elif cat == "ducts":
            self.set_param(bp.RBS_CURVE_WIDTH_PARAM, width / MM, "Double").set_param(bp.RBS_CURVE_HEIGHT_PARAM, height / MM, "Double")
        elif cat == "conduits":
            self.set_param(bp.RBS_CONDUIT_DIAMETER_PARAM, diameter / MM, "Double")
        else:
            self.set_param(bp.RBS_CABLETRAY_WIDTH_PARAM, width / MM, "Double").set_param(bp.RBS_CABLETRAY_HEIGHT_PARAM, height / MM, "Double")
        if insulation:
            self.set_param(bp.RBS_REFERENCE_INSULATION_THICKNESS, insulation / MM, "Double")
        if system:
            self.set_param(bp.RBS_SYSTEM_NAME_PARAM, system, "String")
        r = max(diameter, width, height) / MM
        self.bbox = stub.BoundingBox(tuple(min(a[i], b[i]) - r for i in range(3)), tuple(max(a[i], b[i]) + r for i in range(3)))


class _Named:
    """LookupParameter / Parameters over a dict of revit_mep_stub.Param (journaled Set)."""

    named: Dict[str, Any]

    def LookupParameter(self, name: str) -> Any:
        return self.named.get(name)

    @property
    def Parameters(self) -> List[Any]:
        return [types.SimpleNamespace(Definition=types.SimpleNamespace(Name=n)) for n in self.named]


def _params(owner: Any, template: Dict[str, Tuple[Any, str, bool]]) -> Dict[str, Any]:
    return {name: rs.Param(owner, name, value, kind, ro) for name, (value, kind, ro) in template.items()}


class SOpening(_Named, rs.Taggable, stub.Element):
    """A native opening. It cuts a hole (local box) in its host's solid until it is deleted."""

    def __init__(self, eid: int, host: Any, hole: Tuple[Vec, Vec], template: Dict[str, Tuple[Any, str, bool]]) -> None:
        bic = BuiltInCategory.OST_SWallRectOpening if isinstance(host, SWall) else BuiltInCategory.OST_FloorOpening
        stub.Element.__init__(self, eid, Category(bic, "Openings"))
        self._init_taggable()
        self.Host, self.hole = host, hole
        self.named = _params(self, template)
        lo, hi = hole
        s = host.solid
        clamp = [(max(lo[i], -s.half[i]), min(hi[i], s.half[i])) for i in range(3)]
        pts = [s.world((x, y, z)) for x in clamp[0] for y in clamp[1] for z in clamp[2]]
        self.bbox = stub.BoundingBox(tuple(min(p[i] for p in pts) for i in range(3)), tuple(max(p[i] for p in pts) for i in range(3)))

    def cut(self) -> None:
        self.Host.solid.holes.append(self.hole)

    def on_delete(self) -> None:
        holes = self.Host.solid.holes
        holes.remove(self.hole)
        rs.WORLD["w"].log(lambda: holes.append(self.hole))


class SFamily(stub.Family):
    def __init__(self, eid: int, name: str, placement: str, instance_params: Dict[str, Tuple[Any, str, bool]]) -> None:
        super().__init__(eid, name, Category(BuiltInCategory.OST_GenericModel, "Generic Models"))
        self.FamilyPlacementType = placement
        self.instance_params = instance_params


class SSymbol(stub.FamilySymbol):
    def __init__(self, eid: int, name: str, family: SFamily, type_params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(eid, name, family)
        self.IsActive = False
        for k, v in (type_params or {}).items():
            self.named[k] = stub._Param(v, "Double")

    def Activate(self) -> None:
        self.IsActive = True


class SInstance(_Named, rs.Taggable, stub.FamilyInstance):
    def __init__(self, eid: int, symbol: SSymbol, point: Vec, host: Any = None, how: str = "") -> None:
        stub.FamilyInstance.__init__(self, eid, Category(BuiltInCategory.OST_GenericModel, "Generic Models"), point, host, symbol=symbol)
        self._init_taggable()
        self.named = _params(self, symbol.Family.instance_params)
        self.FacingOrientation, self.HandOrientation = XYZ(0.0, 1.0, 0.0), XYZ(1.0, 0.0, 0.0)
        self.how = how
        self.bbox = None
        self.ref: Any = None


class SLink(stub.Element):
    def __init__(self, eid: int, name: str, link_doc: Any, transform: Transform) -> None:
        super().__init__(eid, Category(BuiltInCategory.OST_RvtLinks, "RVT Links"))
        self.Name, self._doc, self._t = name, link_doc, transform

    def GetLinkDocument(self) -> Any:
        return self._doc

    def GetTotalTransform(self) -> Transform:
        return self._t


class LinkDoc(stub.Document):
    Title = "Linked.rvt"


# --------------------------------------------------------------------------- #
# Parameter bindings, shared parameter files and the Application (revit_sparing_status_setup)
# --------------------------------------------------------------------------- #
class SCategory(Category):
    def __init__(self, bic: int, name: str, allows: bool = True) -> None:
        super().__init__(bic, name)
        self.AllowsBoundParameters = allows


class SCatSet(list):
    def Insert(self, c: Any) -> bool:
        self.append(c)
        return True


class SBinding:
    def __init__(self, categories: SCatSet) -> None:
        self.Categories = categories


class SDefinition:
    def __init__(self, name: str, shared: bool = True) -> None:
        self.Name = name
        if shared:
            self.GUID = "00000000-0000-0000-0000-00000000%04d" % (abs(hash(name)) % 10000)


class _Iter:
    def __init__(self, items: List[Tuple[Any, Any]]) -> None:
        self._items, self._i = items, -1

    def MoveNext(self) -> bool:
        self._i += 1
        return self._i < len(self._items)

    @property
    def Key(self) -> Any:
        return self._items[self._i][0]

    @property
    def Current(self) -> Any:
        return self._items[self._i][1]


class SBindings:
    def __init__(self, world: "SparingWorld") -> None:
        self.w = world
        self.items: List[Tuple[Any, Any]] = []

    def ForwardIterator(self) -> _Iter:
        return _Iter(list(self.items))

    def Insert(self, definition: Any, binding: Any, group: Any = None) -> bool:
        w = self.w
        w.maybe_fail("bind_insert")
        if any(d.Name == definition.Name for d, _ in self.items):
            return False
        entry = (definition, binding)
        self.items.append(entry)
        w.log(lambda: self.items.remove(entry))
        return True

    def ReInsert(self, definition: Any, binding: Any, group: Any = None) -> bool:
        w = self.w
        w.maybe_fail("bind_reinsert")
        old = [x for x in self.items if x[0].Name == definition.Name]
        if not old:
            return False
        idx = self.items.index(old[0])
        self.items[idx] = (definition, binding)
        w.log(lambda: self.items.__setitem__(idx, old[0]))
        return True


class _Categories:
    def __init__(self, world: "SparingWorld") -> None:
        self.w = world

    def get_Item(self, bic: int) -> Any:
        return self.w.categories.get(bic)


class SDefinitions(list):
    def __init__(self, world: "SparingWorld") -> None:
        super().__init__()
        self.w = world

    def Create(self, opts: Any) -> SDefinition:
        d = SDefinition(opts.Name)
        d.spec = opts.spec
        self.append(d)
        self.w.file_writes.append(("definition", opts.Name))
        return d


class SDefGroup:
    def __init__(self, world: "SparingWorld", name: str) -> None:
        self.Name, self.Definitions = name, SDefinitions(world)


class SGroups(list):
    def __init__(self, world: "SparingWorld") -> None:
        super().__init__()
        self.w = world

    def Create(self, name: str) -> SDefGroup:
        g = SDefGroup(self.w, name)
        self.append(g)
        self.w.file_writes.append(("group", name))
        return g


class SDefFile:
    def __init__(self, world: "SparingWorld") -> None:
        self.Groups = SGroups(world)


class ExternalDefinitionCreationOptions:
    def __init__(self, name: str, spec: Any) -> None:
        self.Name, self.spec = name, spec
        self.UserModifiable = self.Visible = False


class _AppCreate:
    def NewCategorySet(self) -> SCatSet:
        return SCatSet()

    def NewInstanceBinding(self, cs: SCatSet) -> SBinding:
        return SBinding(cs)


class SApp:
    VersionNumber = "2024"

    def __init__(self, world: "SparingWorld") -> None:
        self.w = world
        self.SharedParametersFilename = ""
        self.Create = _AppCreate()

    def OpenSharedParameterFile(self) -> Any:
        return self.w.shared_files.get(self.SharedParametersFilename)


# --------------------------------------------------------------------------- #
# Collector, creation, the world
# --------------------------------------------------------------------------- #
class SCollector(rs.Collector):
    def WherePasses(self, flt: Any) -> "SCollector":
        if isinstance(flt, BoundingBoxIntersectsFilter):
            self._outline = flt.outline
            return self
        super().WherePasses(flt)
        return self

    def _matches(self, e: Any) -> bool:
        if not super()._matches(e):
            return False
        ol = getattr(self, "_outline", None)
        if ol is None:
            return True
        bb = e.get_BoundingBox(None)
        if bb is None:
            return False
        lo, hi = _t(bb.Min), _t(bb.Max)
        return all(lo[i] <= ol.hi[i] and ol.lo[i] <= hi[i] for i in range(3))


class _SCreator(rs._Creator):
    def NewFamilyInstance(self, *args: Any) -> SInstance:
        w = self.w
        w.maybe_fail("place_family")
        if isinstance(args[0], _Ref):
            ref, loc, _direction, sym = args
            how, host = "face", ref.owner
        elif len(args) == 5:
            loc, sym, host, _level, _st = args
            how = "hosted"
        else:
            loc, sym, _level, _st = args
            how, host = "unhosted", None
        if not sym.IsActive:
            raise RuntimeError("the family symbol is not active")
        inst = SInstance(w.next_id(), sym, _t(loc), host, how)
        if how == "face":
            inst.ref = args[0]
        w.add(inst)
        return inst

    def NewOpening(self, host: Any, a: Any, b: Any) -> SOpening:
        w = self.w
        w.maybe_fail("new_opening")
        s = host.solid
        if isinstance(a, stub.CurveArray):
            pts = [s.local(_t(c.p0)) for c in a.items]
            if not isinstance(host, SFloor):
                raise RuntimeError("a profile opening needs a floor or roof")
        else:
            if not isinstance(host, SWall):
                raise RuntimeError("a two-point opening needs a wall")
            pts = [s.local(_t(a)), s.local(_t(b))]
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
        thin = min(range(3), key=lambda i: s.half[i])
        lo[thin], hi[thin] = -s.half[thin] - 0.01, s.half[thin] + 0.01
        op = SOpening(w.next_id(), host, (tuple(lo), tuple(hi)), w.opening_params)  # type: ignore[arg-type]
        w.add(op)
        op.cut()
        w.log(lambda: s.holes.remove(op.hole))
        return op


class SparingWorld(rs.World):
    def __init__(self) -> None:
        super().__init__()
        self.Create = _SCreator(self)
        self.pbp: Vec = (0.0, 0.0, 0.0)
        self.opening_params: Dict[str, Tuple[Any, str, bool]] = {}
        self.ParameterBindings = SBindings(self)
        self.categories: Dict[int, SCategory] = {
            BuiltInCategory.OST_GenericModel: SCategory(BuiltInCategory.OST_GenericModel, "Generic Models"),
            BuiltInCategory.OST_SpecialityEquipment: SCategory(BuiltInCategory.OST_SpecialityEquipment, "Specialty Equipment"),
            BuiltInCategory.OST_SWallRectOpening: SCategory(BuiltInCategory.OST_SWallRectOpening, "Rectangular Straight Wall Openings", allows=False),
        }
        self.Settings = types.SimpleNamespace(Categories=_Categories(self))
        self.shared_files: Dict[str, SDefFile] = {}
        self.file_writes: List[Tuple[str, str]] = []
        self.app = SApp(self)

    def run(self, script: str) -> str:
        scope: Dict[str, Any] = {"doc": self, "app": self.app, "__output__": "", "__name__": "__ipy__"}
        exec(compile(script, "<embedded-script>", "exec"), scope)  # noqa: S102 - test-only stub execution
        return str(scope["__output__"])

    def _remove(self, e: Any) -> None:
        hook = getattr(e, "on_delete", None)
        if hook is not None:
            hook()
        super()._remove(e)

    # -- scene helpers (millimetres) ------------------------------------------ #
    def put(self, e: Any) -> Any:
        self.elements.append(e)
        return e

    def foreign_opening(self, eid: int, host: Any, centre_mm: Vec, w: float, h: float) -> SOpening:
        """An opening someone else made: a hole of w x h mm around centre_mm, through the whole host."""
        s = host.solid
        c = s.local(ft(centre_mm))
        if isinstance(host, SWall):
            lo = (c[0] - w / 2 / MM, -s.half[1] - 0.01, c[2] - h / 2 / MM)
            hi = (c[0] + w / 2 / MM, s.half[1] + 0.01, c[2] + h / 2 / MM)
        else:
            lo = (c[0] - w / 2 / MM, c[1] - h / 2 / MM, -s.half[2] - 0.01)
            hi = (c[0] + w / 2 / MM, c[1] + h / 2 / MM, s.half[2] + 0.01)
        op = SOpening(eid, host, (lo, hi), {})
        op.cut()
        return self.put(op)

    def family(self, eid: int, name: str, placement: str = "WorkPlaneBased", type_name: str = "Standaard",
               instance_params: Optional[Dict[str, Tuple[Any, str, bool]]] = None, type_params: Optional[Dict[str, Any]] = None) -> SSymbol:
        params = instance_params if instance_params is not None else {
            "b": (0.1, "Double", False), "h": (0.1, "Double", False), "d": (0.1, "Double", False), "Sparing status": ("", "String", False)}
        fam = self.put(SFamily(eid, name, placement, params))
        return self.put(SSymbol(eid + 1, type_name, fam, type_params))


@contextlib.contextmanager
def installed_sparing(monkeypatch: Any) -> Iterator[SparingWorld]:
    """Make ``import clr / System / Autodesk.Revit.DB(.Structure/.ExtensibleStorage)`` resolve to this stub."""
    world = SparingWorld()
    rs.WORLD["w"] = world
    rs.Schema.registry.clear()
    db = types.ModuleType("Autodesk.Revit.DB")
    for name in ("XYZ", "ElementId", "Options", "ViewDetailLevel", "Level", "FamilyInstance", "Family", "FamilySymbol",
                 "ElementMulticategoryFilter", "FamilyInstanceFilter", "Category", "GeometryInstance", "CurveArray", "Element"):
        setattr(db, name, getattr(stub, name))
    names = {
        "BuiltInCategory": BuiltInCategory, "BuiltInParameter": BuiltInParameter, "FilteredElementCollector": SCollector,
        "Line": SLine, "Solid": BoxSolid, "SolidUtils": SolidUtils, "SolidCurveIntersectionOptions": SolidCurveIntersectionOptions,
        "Outline": Outline, "BoundingBoxIntersectsFilter": BoundingBoxIntersectsFilter, "BasePoint": BasePoint,
        "ExternalDefinitionCreationOptions": ExternalDefinitionCreationOptions,
        "SpecTypeId": types.SimpleNamespace(String=types.SimpleNamespace(Text="spec:text")),
        "GroupTypeId": types.SimpleNamespace(IdentityData="identity_data"),
        "RevitLinkInstance": SLink, "Opening": SOpening, "Transform": Transform, "ElementTransformUtils": ElementTransformUtils,
        "Transaction": rs.Transaction, "TransactionGroup": rs.TransactionGroup, "SubTransaction": rs.SubTransaction,
        "TransactionStatus": rs.TransactionStatus, "FailureSeverity": rs.FailureSeverity,
        "FailureProcessingResult": rs.FailureProcessingResult, "IFailuresPreprocessor": rs.IFailuresPreprocessor,
    }
    for name, value in names.items():
        setattr(db, name, value)
    structure = types.ModuleType("Autodesk.Revit.DB.Structure")
    structure.StructuralType = rs._Names("NonStructural")  # type: ignore[attr-defined]
    storage = types.ModuleType("Autodesk.Revit.DB.ExtensibleStorage")
    storage.Schema, storage.SchemaBuilder, storage.AccessLevel = rs.Schema, rs.SchemaBuilder, rs.AccessLevel  # type: ignore[attr-defined]
    storage.Entity, storage.ExtensibleStorageFilter = rs.Entity, rs.ExtensibleStorageFilter  # type: ignore[attr-defined]
    system = types.ModuleType("System")
    system.Guid, system.String = rs.Guid, str  # type: ignore[attr-defined]
    diagnostics = types.ModuleType("System.Diagnostics")
    diagnostics.Stopwatch = stub.Stopwatch  # type: ignore[attr-defined]
    generic = types.ModuleType("System.Collections.Generic")
    generic.List = stub._GenericList()  # type: ignore[attr-defined]
    clr = types.ModuleType("clr")
    clr.GetClrType = lambda t: t  # type: ignore[attr-defined]
    modules = {
        "clr": clr, "System": system, "System.Collections": types.ModuleType("System.Collections"),
        "System.Collections.Generic": generic, "System.Diagnostics": diagnostics, "Autodesk": types.ModuleType("Autodesk"),
        "Autodesk.Revit": types.ModuleType("Autodesk.Revit"), "Autodesk.Revit.DB": db,
        "Autodesk.Revit.DB.Structure": structure, "Autodesk.Revit.DB.ExtensibleStorage": storage,
    }
    for name, mod in modules.items():
        monkeypatch.setitem(sys.modules, name, mod)
    stub.Stopwatch.tick = 0
    try:
        yield world
    finally:
        stub.Stopwatch.tick = 0
        rs.WORLD["w"] = None
        rs.Schema.registry.clear()
