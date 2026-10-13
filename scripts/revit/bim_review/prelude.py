import clr, System
from System.Collections.Generic import List
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Architecture import *

FT = 0.3048           # metres per foot
def ft(m): return m / FT
def mmf(v): return v / 304.8      # millimetres -> feet

# villa-local metres -> model feet. Origin = centre of the anchor element 23832472, ground = level "00 begane grond".
CX, CY = 12981.79708478394, 2673.3989865352243
def pt(x, y, z=0.0): return XYZ(CX + ft(x), CY + ft(y), ft(z))
def uv(x, y): return UV(CX + ft(x), CY + ft(y))

LOG = []
def say(s): LOG.append(str(s))

class Swallow(IFailuresPreprocessor):
    """Never show a dialog. Warnings are collected and dismissed. Errors are reported with the element ids; a failing
    door or window is removed so the rest of the transaction survives, anything else rolls the transaction back."""
    def PreprocessFailures(self, fa):
        verdict = FailureProcessingResult.Continue
        for m in fa.GetFailureMessages():
            if m.GetSeverity() == FailureSeverity.Warning:
                say("warning (swallowed): " + m.GetDescriptionText())
                fa.DeleteWarning(m)
                continue
            ids = list(m.GetFailingElementIds())
            say("ERROR: %s  [failing ids: %s]" % (m.GetDescriptionText(), ", ".join([str(i.Value) for i in ids])))
            removable = List[ElementId]()
            for i in ids:
                e = doc.GetElement(i)
                if e is not None and e.Category is not None and e.Category.Id.IntegerValue in (int(BuiltInCategory.OST_Doors), int(BuiltInCategory.OST_Windows)):
                    removable.Add(i)
            if removable.Count > 0 and removable.Count == len(ids):
                fa.DeleteElements(removable)
                say("   -> removed %d failing door/window instance(s); the rest is kept" % removable.Count)
                verdict = FailureProcessingResult.ProceedWithCommit
            else:
                say("   -> not a door/window error: rolling this transaction back")
                return FailureProcessingResult.ProceedWithRollBack
        return verdict

def run(name, fn):
    t = Transaction(doc, name)
    t.Start()
    opts = t.GetFailureHandlingOptions()
    opts.SetFailuresPreprocessor(Swallow())
    opts.SetClearAfterRollback(True)
    t.SetFailureHandlingOptions(opts)
    try:
        r = fn()
        st = t.Commit()
        if st != TransactionStatus.Committed:
            say("commit status for %s: %s" % (name, st))
        return r
    except Exception as e:
        say("EXCEPTION in %s: %s" % (name, e))
        if t.GetStatus() == TransactionStatus.Started:
            t.RollBack()
        return None

def type_name(t):
    try: return t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or t.Name
    except: return t.Name

def find_type(cls, name):
    for t in FilteredElementCollector(doc).OfClass(cls):
        if type_name(t) == name: return t
    return None

def level_named(name):
    for l in FilteredElementCollector(doc).OfClass(Level):
        if l.Name == name: return l
    return None

# ---- tagging so every phase can be re-run without duplicating anything ----
TAG = "AMB_VILLA:"
_CATS = (BuiltInCategory.OST_Walls, BuiltInCategory.OST_Floors, BuiltInCategory.OST_Roofs, BuiltInCategory.OST_Doors,
         BuiltInCategory.OST_Windows, BuiltInCategory.OST_Rooms, BuiltInCategory.OST_Ceilings, BuiltInCategory.OST_Stairs,
         BuiltInCategory.OST_Columns, BuiltInCategory.OST_StructuralColumns)

def _comments_param(e):
    p = e.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p is None: p = e.LookupParameter("Comments")
    return p

def tag(e, phase):
    p = _comments_param(e)
    if p is not None and not p.IsReadOnly: p.Set(TAG + phase)
    else: say("could not tag element %d (%s)" % (e.Id.Value, e.Category.Name if e.Category else "?"))

def tagged(phase=None):
    out = []
    for c in _CATS:
        for e in FilteredElementCollector(doc).OfCategory(c).WhereElementIsNotElementType():
            p = _comments_param(e)
            v = p.AsString() if p is not None else None
            if v and v.startswith(TAG + (phase or "")): out.append(e)
    return out

def purge(phase):
    items = tagged(phase)
    if not items: return 0
    ids = List[ElementId]([e.Id for e in items])
    def d():
        doc.Delete(ids)
    run("AMB: purge " + phase, d)
    return len(items)

def loop(pts, z):
    cl = CurveLoop()
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        cl.Append(Line.CreateBound(XYZ(CX + ft(a[0]), CY + ft(a[1]), z), XYZ(CX + ft(b[0]), CY + ft(b[1]), z)))
    return cl

def seg_wall(a, b, wt, level, h, off=0.0, phase=""):
    z = level.Elevation
    line = Line.CreateBound(XYZ(CX + ft(a[0]), CY + ft(a[1]), z), XYZ(CX + ft(b[0]), CY + ft(b[1]), z))
    w = Wall.Create(doc, line, wt.Id, level.Id, ft(h), ft(off), False, False)
    tag(w, phase)
    return w

def poly_walls(pts, wt, level, h, off=0.0, phase="", closed=True):
    n = len(pts)
    return [seg_wall(pts[i], pts[(i + 1) % n], wt, level, h, off, phase) for i in range(n if closed else n - 1)]

def zrange_m(e):
    bb = e.get_BoundingBox(None)
    return (bb.Min.Z * FT, bb.Max.Z * FT) if bb is not None else (None, None)
