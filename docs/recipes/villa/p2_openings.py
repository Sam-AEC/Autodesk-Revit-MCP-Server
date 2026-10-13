# Phase 2: Autodesk standard door/window families (from DefaultMetric.rte) + sized AMB types. Idempotent.
TEMPLATE = r"C:\ProgramData\Autodesk\RVT 2024\Templates\English\DefaultMetric.rte"
BASE = [("M_Single-Flush", "0915 x 2134mm"), ("M_Fixed", "0915 x 1220mm"), ("M_Window-Double-Hung", "700 x 1200mm")]

def symbols_in(d):
    return list(FilteredElementCollector(d).OfClass(FamilySymbol))

def sym_key(s):
    return (s.FamilyName, s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString())

class UseExisting(IDuplicateTypeNamesHandler):
    """Answer Revit's 'Duplicate Types' dialog ourselves: keep the model's existing types."""
    def OnDuplicateTypeNamesFound(self, args):
        return DuplicateTypeAction.UseDestinationTypes

def import_base():
    have = set([sym_key(s) for s in symbols_in(doc)])
    missing = [b for b in BASE if b not in have]
    if not missing:
        say("base families already in the model")
        return
    src = app.OpenDocumentFile(ModelPathUtils.ConvertUserVisiblePathToModelPath(TEMPLATE), OpenOptions())
    try:
        ids = List[ElementId]()
        for s in symbols_in(src):
            if sym_key(s) in missing:
                ids.Add(s.Id)
        say("copying %d symbols from the Autodesk template" % ids.Count)
        def cp():
            o = CopyPasteOptions()
            o.SetDuplicateTypeNamesHandler(UseExisting())
            ElementTransformUtils.CopyElements(src, ids, doc, Transform.Identity, o)
        run("AMB: import standard families", cp)
    finally:
        src.Close(False)

def find_sym(family, name):
    for s in symbols_in(doc):
        if sym_key(s) == (family, name): return s
    return None

def setd(sym, pname, metres):
    p = sym.LookupParameter(pname)
    if p is None or p.IsReadOnly:
        say("  parameter %s missing/readonly on %s" % (pname, sym_key(sym)[1])); return False
    p.Set(ft(metres)); return True

DOORS = [   # name, base family, base type, width m, height m
    ("AMB_Door_Entrance_1000x2300", "M_Single-Flush", "0915 x 2134mm", 1.00, 2.30),
    ("AMB_Door_Interior_900x2100",  "M_Single-Flush", "0915 x 2134mm", 0.90, 2.10),
    ("AMB_Door_Garage_4800x2300",   "M_Single-Flush", "0915 x 2134mm", 4.80, 2.30),
]
WINDOWS = [
    ("AMB_Window_Fixed_2400x1500", "M_Fixed", "0915 x 1220mm", 2.40, 1.50),
    ("AMB_Window_Fixed_1200x1500", "M_Fixed", "0915 x 1220mm", 1.20, 1.50),
    ("AMB_Window_Fixed_1800x1500", "M_Fixed", "0915 x 1220mm", 1.80, 1.50),
    ("AMB_Window_FullHeight_2400x2600", "M_Fixed", "0915 x 1220mm", 2.40, 2.60),
    ("AMB_Window_Hung_900x1400", "M_Window-Double-Hung", "700 x 1200mm", 0.90, 1.40),
]

def make_types():
    out = []
    for (name, fam, base, w, h) in DOORS + WINDOWS:
        if find_sym(fam, name) is not None:
            out.append("exists " + name); continue
        b = find_sym(fam, base)
        if b is None:
            out.append("MISSING base %s / %s" % (fam, base)); continue
        n = b.Duplicate(name)
        ok = setd(n, "Width", w) and setd(n, "Height", h)
        out.append("%s %s" % ("created" if ok else "created (size not set!)", name))
    return out

import_base()
res = run("AMB: door and window types", make_types)
for line in (res or []): say(line)
# activate every AMB symbol (required before placing) and read the sizes back
def activate():
    for (name, fam, base, w, h) in DOORS + WINDOWS:
        s = find_sym(fam, name)
        if s is not None and not s.IsActive: s.Activate()
run("AMB: activate symbols", activate)
for (name, fam, base, w, h) in DOORS + WINDOWS:
    s = find_sym(fam, name)
    if s is None: say("CHECK %s NOT FOUND" % name); continue
    gw = s.LookupParameter("Width").AsDouble() * 304.8
    gh = s.LookupParameter("Height").AsDouble() * 304.8
    say("CHECK %-34s %5.0f x %5.0f mm (expected %4.0f x %4.0f) %s active=%s" % (name, gw, gh, w * 1000, h * 1000, "OK" if abs(gw - w * 1000) < 1 and abs(gh - h * 1000) < 1 else "MISMATCH", s.IsActive))
__output__ = "\n".join(LOG)
