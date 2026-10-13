import clr, System
from System.Collections.Generic import List
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Architecture import *

FT = 0.3048           # metres per foot
def ft(m): return m / FT
def mmf(v): return v / 304.8      # millimetres -> feet

# ---- Villa 2: built from the DWG drawing "630ef8009fd4b.dwg" (see README). ----
# DWG units are 0.125 m. Villa 2 stands 30 m to the left (-X) and 30 m above (+Y) of villa 1.
SC = 0.125                              # metres per DWG unit
DWG_CX, DWG_CY = 1624.5, 3735.0         # DWG point that maps to the villa-2 origin
OX = 12981.79708478394 - 30000.0 / 304.8
OY = 2673.3989865352243 + 30000.0 / 304.8
def dx(v): return (v - DWG_CX) * SC / FT       # DWG x -> feet relative to origin
def dy(v): return (v - DWG_CY) * SC / FT
def P(x, y, z=0.0):                            # DWG (x, y) + z in metres -> model XYZ in feet
    return XYZ(OX + dx(x), OY + dy(y), z / FT)
def M(x, y, z=0.0):                            # villa-2 local metres -> model XYZ
    return XYZ(OX + x / FT, OY + y / FT, z / FT)
def metres(v): return v * SC                   # DWG length -> metres

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
TAG = "AMB_V2:"
def _comments_param(e):
    p = e.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p is None: p = e.LookupParameter("Comments")
    return p

def tag(e, phase):
    p = _comments_param(e)
    if p is not None and not p.IsReadOnly: p.Set(TAG + phase)
    else: say("could not tag element %d (%s)" % (e.Id.IntegerValue, e.Category.Name if e.Category else "?"))

def cmt(e):
    p = _comments_param(e)
    return p.AsString() if p is not None else None

def tagged(phase=None):
    """Every element of villa 2 (any category), optionally limited to one phase."""
    out = []
    for e in FilteredElementCollector(doc).WhereElementIsNotElementType():
        try: v = cmt(e)
        except: v = None
        if v and v.startswith(TAG + (phase or "")): out.append(e)
    return out

def purge(phase):
    items = tagged(phase)
    if not items: return 0
    ids = List[ElementId]([e.Id for e in items if e.IsValidObject])
    def d():
        for i in ids:
            try: doc.Delete(i)
            except: pass
    run("AMB2: purge " + phase, d)
    return len(items)

def level_elev_m(l): return l.Elevation * FT
def lname(l): return l.get_Parameter(BuiltInParameter.DATUM_TEXT).AsString()
