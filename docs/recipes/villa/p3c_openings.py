# Phase 3c: doors and windows from the Autodesk base families, hosted in the right wall, verified to cut it.
PH = "p3c"
say("purged %d earlier p3c elements" % purge(PH))
L0, L1 = level_named("00 begane grond"), level_named("AMB_01 First Floor")
def sym(name):
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString() == name: return s
ENT, INT, GAR = "AMB_Door_Entrance_1000x2300", "AMB_Door_Interior_900x2100", "AMB_Door_Garage_4800x2300"
FX24, FX12, FX18, FULL, HUNG = "AMB_Window_Fixed_2400x1500", "AMB_Window_Fixed_1200x1500", "AMB_Window_Fixed_1800x1500", "AMB_Window_FullHeight_2400x2600", "AMB_Window_Hung_900x1400"
# (type, x, y, sill_m)   sill is ignored for doors
GROUND = [(ENT, 2, -5, 0), (GAR, 6.5, -5, 0), (INT, 3, -2, 0), (INT, 1, -1, 0), (INT, -3, 0, 0), (INT, -7, 3, 0), (INT, -2, 3, 0),
          (FULL, -6, -5, 0), (FULL, -9, -1, 0), (FX24, -1, -5, 0.9), (FX12, -9, 5.5, 0.9), (FX12, -7, 8, 0.9), (FX18, -3, 8, 0.9), (FX12, -1, 5.5, 0.9)]
UPPER = [(INT, -6.75, 1.5, 0), (INT, -2.25, 1.5, 0), (INT, 3.5, -1, 0), (INT, 5, 0.5, 0), (INT, 6.5, 2, 0), (INT, -7, 3, 0), (INT, -3, 3, 0),
         (FX18, -6.75, -5, 0.9), (FX18, -2.25, -5, 0.9), (FULL, 1.75, -5, 0), (FULL, 6.75, -5, 0), (FX18, -9, -1.75, 0.9), (FX12, -9, 5.5, 0.9),
         (FX12, -7, 8, 0.9), (HUNG, -3, 8, 1.2), (FULL, 10, -1.5, 0), (HUNG, 10, 1.75, 1.2), (HUNG, 8.25, 3, 1.2)]
walls = [w for w in tagged() if isinstance(w, Wall)]
say("candidate host walls: %d" % len(walls))

def host_at(x, y, level):
    p = XYZ(CX + ft(x), CY + ft(y), level.Elevation)
    best, bd = None, 1e9
    for w in walls:
        if w.LevelId != level.Id: continue
        lo, hi = zrange_m(w)
        # a host must stand on this level and reach well above the floor (excludes the underground foundation walls)
        if lo > level.Elevation * FT + 0.2 or hi < level.Elevation * FT + 2.0: continue
        lc = w.Location
        if lc is None or lc.Curve is None: continue
        c = lc.Curve
        q = XYZ(p.X, p.Y, c.GetEndPoint(0).Z)
        d = c.Distance(q)
        if d < bd: best, bd = w, d
    return (best, bd)

def vol(w):
    p = w.get_Parameter(BuiltInParameter.HOST_VOLUME_COMPUTED)
    return p.AsDouble() if p is not None else None

def place(items, level):
    out = []
    for (tname, x, y, sill) in items:
        s = sym(tname)
        host, dist = host_at(x, y, level)
        if s is None or host is None or dist > 0.2:
            out.append((tname, x, y, None, "no host/type (dist %.2f ft)" % dist)); continue
        v0 = vol(host)
        loc = XYZ(CX + ft(x), CY + ft(y), level.Elevation)
        fi = doc.Create.NewFamilyInstance(loc, s, host, level, Structure.StructuralType.NonStructural)
        tag(fi, PH)
        if fi.Category.Id.IntegerValue == int(BuiltInCategory.OST_Windows):
            p = fi.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)
            if p is not None and not p.IsReadOnly: p.Set(ft(sill))
        out.append((tname, x, y, (fi, host, v0), ""))
    return out

def build():
    return place(GROUND, L0) + place(UPPER, L1)

import Autodesk.Revit.DB.Structure as Structure
res = run("AMB: doors and windows", build)
doc.Regenerate() if False else None
placed = bad = 0
if res:
    for (tname, x, y, data, why) in res:
        if data is None:
            bad += 1; say("NOT PLACED %-34s at (%.2f, %.2f): %s" % (tname, x, y, why)); continue
        fi, host, v0 = data
        v1 = vol(host)
        cut = (v0 - v1) if (v0 is not None and v1 is not None) else None
        placed += 1
        if cut is None or cut <= 1e-6:
            bad += 1; say("DOES NOT CUT %-34s at (%.2f, %.2f) host wall %d" % (tname, x, y, host.Id.Value))
    say("placed %d, problems %d" % (placed, bad))
__output__ = "\n".join(LOG)
