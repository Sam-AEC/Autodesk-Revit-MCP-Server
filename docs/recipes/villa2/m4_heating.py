# Villa 2 MEP: heating. Heat pump -> manifolds (ground, first floor) and cylinder coil; manifolds -> radiators (two-pipe, one loop each).
# Pipes run in the floor build-up (concept, ~35 mm above the structural floor), joined to the equipment connectors with fittings.
# DATA = dict(only=[route ids] optional). Needs prelude2 + m3_route.py.
from Autodesk.Revit.DB.Plumbing import PipeType
from Autodesk.Revit.DB.Plumbing import PipeSegment
def ensure_pipe_type(name, base_name):
    """Pressure pipe type: duplicate of the project's PVC type, segment replaced by the project's Rautitan (PE-X) segment.
    Fittings stay the project's variable-size ones (smallest size 32 mm), so every pressure pipe here is 32 mm (concept, not sized)."""
    for t in FilteredElementCollector(doc).OfClass(PipeType):
        if type_name(t) == name: return t
    for t in FilteredElementCollector(doc).OfClass(PipeType):
        if type_name(t) == base_name:
            n = t.Duplicate(name)
            seg = [s for s in FilteredElementCollector(doc).OfClass(PipeSegment) if "Rautitan" in (s.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString() or s.Name if True else "")]
            if seg:
                rpm = n.RoutingPreferenceManager
                rpm.AddRule(RoutingPreferenceRuleGroupType.Segments, RoutingPreferenceRule(seg[0].Id, "Rautitan"), 0)
                try: rpm.RemoveRule(RoutingPreferenceRuleGroupType.Segments, 1)
                except: pass
            return n
    raise Exception("no base pipe type " + base_name)
PEX = None
def _t():
    global PEX
    PEX = ensure_pipe_type("AMB2_PE-X_pressure", "NLRS_52_PI_PVC U3 Grijs OD_Dyka")
run("AMB2: pipe type", _t)
PEX = [t for t in FilteredElementCollector(doc).OfClass(PipeType) if type_name(t) == "AMB2_PE-X_pressure"][0]
L0, L1 = level_named("00 begane grond"), level_named("AMB2_01 First Floor")
ZS, ZR = 0.035, 0.080          # supply / return height above the finished level (m)

def plan():
    r = []
    # ground manifold and cylinder coil from the heat pump; first-floor manifold through a riser at (1636, 3746)
    r.append(dict(id="H_HP_MG_S", a=("HP", "SupplyHydronic", None, "y"), b=("MANG", "SupplyHydronic", (38, 42), None), lvl="L0", z=ZS, dia=40))
    r.append(dict(id="H_HP_MG_R", a=("HP", "ReturnHydronic", None, "y"), b=("MANG", "ReturnHydronic", (38, 42), None), lvl="L0", z=ZR, dia=40))
    r.append(dict(id="H_HP_MF_S", a=("HP", "SupplyHydronic", None, "y"), b=("MANF", "SupplyHydronic", (30, 34), None), lvl="L0", z=ZS, dia=28, via=[(1636.0, 3746.0, "L1", ZS)]))
    r.append(dict(id="H_HP_MF_R", a=("HP", "ReturnHydronic", None, "y"), b=("MANF", "ReturnHydronic", (30, 34), None), lvl="L0", z=ZR, dia=28, via=[(1636.6, 3746.0, "L1", ZR)]))
    r.append(dict(id="H_HP_CY_S", a=("HP", "SupplyHydronic", None, "y"), b=("CYL", "SupplyHydronic", None, None), lvl="L0", z=ZS, dia=40))
    r.append(dict(id="H_HP_CY_R", a=("HP", "ReturnHydronic", None, "y"), b=("CYL", "ReturnHydronic", None, None), lvl="L0", z=ZR, dia=40))
    for i, (m, lv) in enumerate([("MANG", "L0")] * 5 + [("MANF", "L1")] * 5, 1):
        rad = "RAD%d" % i
        r.append(dict(id="H_%s_S" % rad, a=(m, "SupplyHydronic", (30, 34), "y"), b=(rad, "SupplyHydronic", None, None), lvl=lv, z=ZS, dia=32))
        r.append(dict(id="H_%s_R" % rad, a=(m, "ReturnHydronic", (30, 34), "y"), b=(rad, "ReturnHydronic", None, None), lvl=lv, z=ZR, dia=32))
    return r

def do(rt):
    lvl = L0 if rt["lvl"] == "L0" else L1
    c1 = pick(*rt["a"][:2], dia=rt["a"][2], sort=rt["a"][3]); c2 = pick(*rt["b"][:2], dia=rt["b"][2], sort=rt["b"][3])
    via = None
    if rt.get("via"):
        via = []
        for v in rt["via"]:
            x, y = v[0] / 1.0, v[1]
            pt = P(x, y, 0); zl = (L1 if v[2] == "L1" else L0).Elevation + v[3] / FT
            via.append((pt.X, pt.Y, zl))
    zr = lvl.Elevation + rt["z"] / FT
    route("pipe", c1, c2, PEX.Id, lvl.Id, zr, rt["dia"], via=via, label=rt["id"])

only = DATA.get("only")
for rt in plan():
    if only and rt["id"] not in only: continue
    run("AMB2: heating " + rt["id"], lambda rt=rt: do(rt))
rep, fit = report()
say("pipes %d (open ends %d) ; fittings %d" % (rep["pipe"][0], len(rep["pipe"][1]), fit))
__output__ = chr(10).join(LOG)
