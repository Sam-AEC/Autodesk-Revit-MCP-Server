"""Stand-in for the part of the Revit API the revit_docs sheet, template, crop and revision scripts use.

It builds on ``revit_mep_stub`` (World with an undo journal, transactions with failure injection, the Extensible Storage
tag, the collector) and adds views, sheets, viewports, view templates, crop boxes, revisions and revision clouds.
Properties that the scripts write are journaled, so a rolled-back group really restores them.

It is NOT Revit. It proves the scripts' control flow, ownership and refusal rules, rollback, dry run and the line protocol.
Where it enforces a Revit rule (sheet numbers are unique, clouds must lie in the plane of their view, an issued revision
takes no new clouds), that rule is what the script author believes Revit does; it is UNVERIFIED against a live Revit.
"""
from __future__ import annotations

import contextlib
import sys
import types
from typing import Any, Dict, Iterator, List, Optional, Tuple

import revit_api_stub as stub
import revit_mep_stub as rs
from revit_api_stub import Category, ElementId, XYZ

FT = 0.3048
TITLE_BLOCKS = -2000280


def world() -> rs.World:
    return rs.WORLD["w"]


class J:
    """Journaled attributes: a rollback puts the old value back. Switched on once ``_ready`` is set."""

    _journaled: Tuple[str, ...] = ()
    _fail_labels: Dict[str, str] = {}

    def __setattr__(self, key: str, value: Any) -> None:
        w = rs.WORLD["w"]
        if w is not None and self.__dict__.get("_ready") and key in self._journaled:
            label = self._fail_labels.get(key)
            if label:
                w.maybe_fail(label)
            old = self.__dict__.get(key)
            object.__setattr__(self, key, value)
            w.log(lambda: object.__setattr__(self, key, old))
        else:
            object.__setattr__(self, key, value)


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #
class Transform:
    def __init__(self, origin: tuple = (0.0, 0.0, 0.0), basis_x: tuple = (1.0, 0.0, 0.0), basis_y: tuple = (0.0, 1.0, 0.0)) -> None:
        self.Origin = XYZ(*origin)
        self.BasisX, self.BasisY = XYZ(*basis_x), XYZ(*basis_y)
        bx, by = basis_x, basis_y
        self.BasisZ = XYZ(bx[1] * by[2] - bx[2] * by[1], bx[2] * by[0] - bx[0] * by[2], bx[0] * by[1] - bx[1] * by[0])

    def OfPoint(self, p: XYZ) -> XYZ:
        o, x, y, z = self.Origin, self.BasisX, self.BasisY, self.BasisZ
        return XYZ(o.X + p.X * x.X + p.Y * y.X + p.Z * z.X, o.Y + p.X * x.Y + p.Y * y.Y + p.Z * z.Y, o.Z + p.X * x.Z + p.Y * y.Z + p.Z * z.Z)

    @property
    def Inverse(self) -> "Transform":
        return _Inverse(self)

    def copy(self) -> "Transform":
        return Transform((self.Origin.X, self.Origin.Y, self.Origin.Z), (self.BasisX.X, self.BasisX.Y, self.BasisX.Z), (self.BasisY.X, self.BasisY.Y, self.BasisY.Z))


class _Inverse:
    def __init__(self, t: Transform) -> None:
        self.t = t

    def OfPoint(self, p: XYZ) -> XYZ:
        t = self.t
        d = (p.X - t.Origin.X, p.Y - t.Origin.Y, p.Z - t.Origin.Z)
        dot = lambda a, b: a.X * b[0] + a.Y * b[1] + a.Z * b[2]  # noqa: E731
        return XYZ(dot(t.BasisX, d), dot(t.BasisY, d), dot(t.BasisZ, d))


class BoundingBoxXYZ:
    def __init__(self) -> None:
        self.Transform = Transform()
        self.Min, self.Max = XYZ(0.0, 0.0, 0.0), XYZ(0.0, 0.0, 0.0)

    def copy(self) -> "BoundingBoxXYZ":
        b = BoundingBoxXYZ()
        b.Transform = self.Transform.copy()
        b.Min, b.Max = XYZ(self.Min.X, self.Min.Y, self.Min.Z), XYZ(self.Max.X, self.Max.Y, self.Max.Z)
        return b


class DLine(stub.Curve):
    @staticmethod
    def CreateBound(a: XYZ, b: XYZ) -> "DLine":
        return DLine((a.X, a.Y, a.Z), (b.X, b.Y, b.Z))


class Outline:
    def __init__(self, lo: tuple, hi: tuple) -> None:
        self.MinimumPoint, self.MaximumPoint = XYZ(*lo), XYZ(*hi)


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
class _ShapeManager(J):
    _journaled = ("LeftAnnotationCropOffset", "RightAnnotationCropOffset", "TopAnnotationCropOffset", "BottomAnnotationCropOffset")

    def __init__(self) -> None:
        self.ShapeSet = False
        self.LeftAnnotationCropOffset = self.RightAnnotationCropOffset = 0.0
        self.TopAnnotationCropOffset = self.BottomAnnotationCropOffset = 0.0
        self._ready = True


class DView(J, stub.Element):
    _journaled = ("Name", "ViewTemplateId", "CropBoxActive", "_crop")
    _fail_labels = {"ViewTemplateId": "assign_template", "_crop": "crop_box"}
    view_type = "FloorPlan"

    def __init__(self, eid: int, name: str, view_type: Optional[str] = None, template: bool = False) -> None:
        stub.Element.__init__(self, eid, None)
        self.Name = name
        self.IsTemplate = template
        self.ViewType = view_type or self.view_type
        self.ViewTemplateId = ElementId(-1)
        self.CropBoxActive = False
        self._crop = BoundingBoxXYZ()
        self.Origin = XYZ(0.0, 0.0, 0.0)
        self.RightDirection, self.UpDirection = XYZ(1.0, 0.0, 0.0), XYZ(0.0, 1.0, 0.0)
        self.vp_size = (1.0, 0.8)  # feet on the sheet
        self.shape = _ShapeManager()
        self.annot = rs.NamedParam(self, "Annotation Crop", 0, "Integer", "spec:int", bip=BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
        self._ready = True

    @property
    def CropBox(self) -> BoundingBoxXYZ:
        return self._crop.copy()

    @CropBox.setter
    def CropBox(self, box: BoundingBoxXYZ) -> None:
        self._crop = box.copy()

    def set_crop(self, lo: tuple, hi: tuple, transform: Optional[Transform] = None) -> "DView":
        b = BoundingBoxXYZ()
        b.Transform = transform or Transform()
        b.Min, b.Max = XYZ(*lo), XYZ(*hi)
        object.__setattr__(self, "_crop", b)
        return self

    def get_Parameter(self, which: Any) -> Any:
        return self.annot if which == BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE else None

    def apply_param(self, key: str, value: Any) -> None:
        pass

    def GetCropRegionShapeManager(self) -> _ShapeManager:
        return self.shape

    def IsValidViewTemplate(self, tid: ElementId) -> bool:
        t = world().GetElement(tid)
        return t is not None and t.IsTemplate and t.ViewType == self.ViewType

    def CreateViewTemplate(self) -> "DView":
        world().maybe_fail("create_template")
        t = DView(world().next_id(), self.Name + " Template", self.ViewType, template=True)
        world().add(t)
        return t


class ViewPlan(DView):
    view_type = "FloorPlan"


class ViewSection(DView):
    view_type = "Section"

    def __init__(self, eid: int, name: str, **kw: Any) -> None:
        super().__init__(eid, name, **kw)
        self.RightDirection, self.UpDirection = XYZ(1.0, 0.0, 0.0), XYZ(0.0, 0.0, 1.0)  # looks along +Y
        self.Origin = XYZ(0.0, 5.0, 0.0)


class View3D(DView):
    view_type = "ThreeD"


class ViewSchedule(DView):
    view_type = "Schedule"
    IsTitleblockRevisionSchedule = False


class ViewSheet(DView):
    view_type = "DrawingSheet"
    _journaled = DView._journaled + ("SheetNumber", "_extra_revs")
    _fail_labels = {**DView._fail_labels, "SheetNumber": "sheet_number", "_extra_revs": "set_revisions"}

    def __init__(self, eid: int, number: str, name: str, placeholder: bool = False) -> None:
        super().__init__(eid, name)
        self._ready = False
        self.SheetNumber = number
        self.IsPlaceholder = placeholder
        self._extra_revs: List[int] = []
        self._ready = True

    def __setattr__(self, key: str, value: Any) -> None:
        if key == "SheetNumber" and self.__dict__.get("_ready"):
            for e in world().elements:
                if isinstance(e, ViewSheet) and e is not self and e.SheetNumber == value:
                    raise RuntimeError("The sheet number '%s' is already in use." % value)
        super().__setattr__(key, value)

    def GetAdditionalRevisionIds(self) -> List[ElementId]:
        return [ElementId(i) for i in self._extra_revs]

    def SetAdditionalRevisionIds(self, ids: Any) -> None:
        self._extra_revs = [i.Value for i in ids]

    def GetAllRevisionIds(self) -> List[ElementId]:
        out = set(self._extra_revs)
        on_sheet = {vp.ViewId.Value for vp in world().elements if isinstance(vp, Viewport) and vp.SheetId.Value == self.Id.Value}
        for c in world().elements:
            if isinstance(c, RevisionCloud) and c.OwnerViewId.Value in on_sheet:
                out.add(c.RevisionId.Value)
        return [ElementId(i) for i in sorted(out)]

    def get_Parameter(self, which: Any) -> Any:
        revs = [r for r in world().elements if isinstance(r, Revision) and r.Id.Value in {i.Value for i in self.GetAllRevisionIds()} and r.Issued]
        if which == BuiltInParameter.SHEET_CURRENT_REVISION:
            return _TextParam(revs[-1].RevisionNumber if revs else "")
        if which == BuiltInParameter.SHEET_CURRENT_REVISION_DESCRIPTION:
            return _TextParam(revs[-1].Description if revs else "")
        return None


class _TextParam:
    def __init__(self, text: str) -> None:
        self.text = text

    def AsString(self) -> str:
        return self.text


class ScheduleSheetInstance(stub.Element):
    IsTitleblockRevisionSchedule = False

    def __init__(self, eid: int, sheet: ViewSheet, schedule: ViewSchedule) -> None:
        super().__init__(eid, None)
        self.OwnerViewId, self.ScheduleId = sheet.Id, schedule.Id


class TitleBlockSymbol(stub.Element):
    def __init__(self, eid: int, family: str, name: str) -> None:
        super().__init__(eid, Category(TITLE_BLOCKS, "Title Blocks"), "")
        self.FamilyName, self.Name, self.is_type = family, name, True


class TitleBlock(stub.Element):
    def __init__(self, eid: int, sheet: ViewSheet, symbol: TitleBlockSymbol, lo: tuple, hi: tuple) -> None:
        super().__init__(eid, Category(TITLE_BLOCKS, "Title Blocks"), "")
        self.OwnerViewId, self.Symbol = sheet.Id, symbol
        self.bbox = stub.BoundingBox(lo, hi)


class Viewport(J, stub.Element):
    _journaled = ("_center",)

    def __init__(self, eid: int, sheet: ViewSheet, view: DView, centre: XYZ) -> None:
        stub.Element.__init__(self, eid, None)
        self.SheetId, self.ViewId = sheet.Id, view.Id
        self.size = view.vp_size
        self._center = (centre.X, centre.Y)
        self._ready = True

    def GetBoxCenter(self) -> XYZ:
        return XYZ(self._center[0], self._center[1], 0.0)

    def SetBoxCenter(self, p: XYZ) -> None:
        self._center = (p.X, p.Y)

    def GetBoxOutline(self) -> Outline:
        (cx, cy), (w, h) = self._center, self.size
        return Outline((cx - w / 2.0, cy - h / 2.0, 0.0), (cx + w / 2.0, cy + h / 2.0, 0.0))

    @staticmethod
    def CanAddViewToSheet(document: Any, sheet_id: ElementId, view_id: ElementId) -> bool:
        w = world()
        v = w.GetElement(view_id)
        if w.GetElement(sheet_id) is None or v is None or isinstance(v, ViewSheet) or isinstance(v, DView) and v.IsTemplate:
            return False
        if v.ViewType == "Legend":
            return True
        return not any(isinstance(e, Viewport) and e.ViewId.Value == view_id.Value for e in w.elements)

    @staticmethod
    def Create(document: Any, sheet_id: ElementId, view_id: ElementId, centre: XYZ) -> "Viewport":
        w = world()
        w.maybe_fail("viewport")
        vp = Viewport(w.next_id(), w.GetElement(sheet_id), w.GetElement(view_id), centre)
        w.add(vp)
        return vp


# --------------------------------------------------------------------------- #
# Revisions
# --------------------------------------------------------------------------- #
class RevisionVisibility:
    Hidden, CloudAndTagVisible, TagVisible = "Hidden", "CloudAndTagVisible", "TagVisible"


class Revision(J, stub.Element):
    _journaled = ("Description", "RevisionDate", "IssuedBy", "IssuedTo", "Issued", "Visibility")

    def __init__(self, eid: int, sequence: int) -> None:
        stub.Element.__init__(self, eid, None)
        self.SequenceNumber, self.RevisionNumber = sequence, str(sequence)
        self.Description, self.RevisionDate, self.IssuedBy, self.IssuedTo = "", "", "", ""
        self.Issued, self.Visibility = False, RevisionVisibility.CloudAndTagVisible
        self._ready = True

    @staticmethod
    def Create(document: Any) -> "Revision":
        w = world()
        w.maybe_fail("revision")
        r = Revision(w.next_id(), 1 + sum(1 for e in w.elements if isinstance(e, Revision)))
        w.add(r)
        return r


class RevisionCloud(stub.Element):
    def __init__(self, eid: int, view: DView, revision: Revision, curves: List[DLine]) -> None:
        super().__init__(eid, None)
        self.OwnerViewId, self.RevisionId, self.curves = view.Id, revision.Id, curves

    @staticmethod
    def Create(document: Any, view: DView, revision_id: Any, curves: Any) -> "RevisionCloud":
        w = world()
        w.maybe_fail("cloud")
        # The real signature takes an ElementId; passing the Revision itself fails in Revit 2024.
        revision = w.GetElement(revision_id)
        if not isinstance(revision, Revision):
            raise TypeError("expected ElementId, got %s" % type(revision_id).__name__)
        if revision.Issued:
            raise RuntimeError("Revision clouds cannot be added to an issued revision.")
        curves = list(curves)
        if len(curves) < 3:
            raise RuntimeError("The cloud needs a closed loop of curves.")
        o, r, u = view.Origin, view.RightDirection, view.UpDirection
        n = (r.Y * u.Z - r.Z * u.Y, r.Z * u.X - r.X * u.Z, r.X * u.Y - r.Y * u.X)
        for c in curves:
            for p in (c.p0, c.p1):
                if abs((p.X - o.X) * n[0] + (p.Y - o.Y) * n[1] + (p.Z - o.Z) * n[2]) > 1e-6:
                    raise RuntimeError("The curves do not lie in the plane of the view.")
        c = RevisionCloud(w.next_id(), view, revision, curves)
        w.add(c)
        return c


# --------------------------------------------------------------------------- #
# Installing the stub
# --------------------------------------------------------------------------- #
BuiltInParameter = types.SimpleNamespace(
    **rs.BuiltInParameter.__dict__, VIEWER_ANNOTATION_CROP_ACTIVE="viewer_annotation_crop", SHEET_CURRENT_REVISION="sheet_rev",
    SHEET_CURRENT_REVISION_DESCRIPTION="sheet_rev_desc",
)
BuiltInCategory = types.SimpleNamespace(**rs.BuiltInCategory.__dict__, OST_TitleBlocks=TITLE_BLOCKS)


@contextlib.contextmanager
def installed_docs(monkeypatch: Any) -> Iterator["Scene"]:
    with rs.installed_mep(monkeypatch) as w:
        w.Regenerate = lambda: None  # type: ignore[method-assign]
        db = sys.modules["Autodesk.Revit.DB"]
        for name, obj in {
            "View": DView, "ViewPlan": ViewPlan, "ViewSection": ViewSection, "View3D": View3D, "ViewSchedule": ViewSchedule,
            "ViewSheet": ViewSheet, "ScheduleSheetInstance": ScheduleSheetInstance, "Viewport": Viewport, "Revision": Revision,
            "RevisionCloud": RevisionCloud, "RevisionVisibility": RevisionVisibility, "Curve": stub.Curve, "Line": DLine,
            "BoundingBoxXYZ": BoundingBoxXYZ, "Transform": Transform, "BuiltInParameter": BuiltInParameter,
            "BuiltInCategory": BuiltInCategory,
        }.items():
            monkeypatch.setattr(db, name, obj, raising=False)
        yield Scene(w)


class Scene:
    """A small project: two levels, plan views, a section, a legend, templates, sheets with title blocks, two revisions."""

    def __init__(self, w: rs.World) -> None:
        self.w = w
        self.tb_symbol = TitleBlockSymbol(w.next_id(), "A1 metric", "A1")
        w.elements.append(self.tb_symbol)
        self.plans: Dict[str, ViewPlan] = {}
        for i, name in enumerate(("L0 Plan", "L1 Plan", "L2 Plan", "L3 Plan")):
            p = ViewPlan(w.next_id(), name)
            p.set_crop((0.0, 0.0, -1.0), (30.0, 20.0, 1.0), Transform((0.0, 0.0, 10.0 * i)))
            p.CropBoxActive = True
            self.plans[name] = p
            w.elements.append(p)
        self.section = ViewSection(w.next_id(), "Section A")
        self.view3d = View3D(w.next_id(), "3D Overview")
        self.legend = DView(w.next_id(), "Legend 1", "Legend")
        self.schedule = ViewSchedule(w.next_id(), "Door schedule")
        self.tpl_plan = DView(w.next_id(), "Plan Template", "FloorPlan", template=True)
        self.tpl_section = DView(w.next_id(), "Section Template", "Section", template=True)
        w.elements.extend([self.section, self.view3d, self.legend, self.schedule, self.tpl_plan, self.tpl_section])
        self.sheets: Dict[str, ViewSheet] = {}
        for number, name, tb in (("A101", "Plans", True), ("A102", "Sections", True), ("A103", "Details", True), ("A104", "No title block", False)):
            self.add_sheet(number, name, tb)
        self.rev1 = self.add_revision("Issue for permit", issued=True)
        self.rev2 = self.add_revision("Client comments")
        w.journal.clear()
        w.txn_log.clear()

    def add_sheet(self, number: str, name: str, title_block: bool = True, placeholder: bool = False) -> ViewSheet:
        w = self.w
        s = ViewSheet(w.next_id(), number, name, placeholder)
        w.elements.append(s)
        self.sheets[number] = s
        if title_block:
            w.elements.append(TitleBlock(w.next_id(), s, self.tb_symbol, (0.0, 0.0, 0.0), (2.76, 1.95, 0.0)))
        return s

    def add_revision(self, description: str, issued: bool = False) -> Revision:
        r = Revision(self.w.next_id(), 1 + sum(1 for e in self.w.elements if isinstance(e, Revision)))
        object.__setattr__(r, "Description", description)
        object.__setattr__(r, "Issued", issued)
        self.w.elements.append(r)
        return r

    def place(self, view: DView, sheet: str, x: float = 1.0, y: float = 1.0) -> Viewport:
        vp = Viewport(self.w.next_id(), self.sheets[sheet], view, XYZ(x, y, 0.0))
        self.w.elements.append(vp)
        return vp

    def viewports(self, sheet: Optional[str] = None) -> List[Viewport]:
        sid = self.sheets[sheet].Id.Value if sheet else None
        return [e for e in self.w.elements if isinstance(e, Viewport) and (sid is None or e.SheetId.Value == sid)]

    def clouds(self) -> List[RevisionCloud]:
        return [e for e in self.w.elements if isinstance(e, RevisionCloud)]

    def snapshot(self) -> tuple:
        """Everything the tests compare before and after a rolled-back call."""
        out = []
        for e in self.w.elements:
            row = [type(e).__name__, e.Id.Value]
            for k in ("Name", "SheetNumber", "ViewTemplateId", "CropBoxActive", "Description", "Issued", "IssuedBy", "RevisionDate", "_extra_revs", "_center"):
                if hasattr(e, k):
                    v = getattr(e, k)
                    row.append((k, v.Value if isinstance(v, ElementId) else (list(v) if isinstance(v, list) else v)))
            if isinstance(e, DView):
                c = e._crop
                row.append(("crop", c.Min.X, c.Min.Y, c.Max.X, c.Max.Y, e.annot.value, e.shape.LeftAnnotationCropOffset))
            out.append(tuple(row))
        return tuple(out)


def box_in_model(view: DView) -> Tuple[float, float, float, float]:
    cb = view.CropBox
    pts = [cb.Transform.OfPoint(XYZ(x, y, cb.Min.Z)) for x in (cb.Min.X, cb.Max.X) for y in (cb.Min.Y, cb.Max.Y)]
    return (min(p.X for p in pts), min(p.Y for p in pts), max(p.X for p in pts), max(p.Y for p in pts))
