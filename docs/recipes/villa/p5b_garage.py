# Garage opening: replace the hinged-door family (swing arc) with a plain fixed panel type 4.8 x 2.3 m.
L0 = level_named("00 begane grond")
def symk(s): return (s.FamilyName, s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString())
base = [s for s in FilteredElementCollector(doc).OfClass(FamilySymbol) if symk(s) == ("M_Fixed", "AMB_Window_Fixed_2400x1500")][0]
def fix():
    gd = [e for e in tagged("p3c") if isinstance(e, FamilyInstance) and e.Symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString() == "AMB_Door_Garage_4800x2300"]
    host = gd[0].Host if gd else None
    for g in gd: doc.Delete(g.Id)
    t = [s for s in FilteredElementCollector(doc).OfClass(FamilySymbol) if symk(s) == ("M_Fixed", "AMB_Window_GarageDoor_4800x2300")]
    if t: sym = t[0]
    else:
        sym = base.Duplicate("AMB_Window_GarageDoor_4800x2300")
        sym.LookupParameter("Width").Set(ft(4.8)); sym.LookupParameter("Height").Set(ft(2.3))
    if not sym.IsActive: sym.Activate()
    return sym, host
r = run("AMB: garage door -> sectional panel", fix)
if r:
    sym, host = r
    def place():
        v0 = host.get_Parameter(BuiltInParameter.HOST_VOLUME_COMPUTED).AsDouble()
        fi = doc.Create.NewFamilyInstance(XYZ(CX + ft(6.5), CY + ft(-5), L0.Elevation), sym, host, L0, Structure.StructuralType.NonStructural)
        p = fi.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)
        if p is not None and not p.IsReadOnly: p.Set(0.0)
        tag(fi, "p3c"); return fi, v0
    import Autodesk.Revit.DB.Structure as Structure
    pr = run("AMB: place garage panel", place)
    if pr:
        fi, v0 = pr
        v1 = host.get_Parameter(BuiltInParameter.HOST_VOLUME_COMPUTED).AsDouble()
        say("garage panel placed (id %d): wall volume %.2f -> %.2f m3 %s" % (fi.Id.Value, v0 * 0.0283168, v1 * 0.0283168, "CUTS" if v1 < v0 else "DOES NOT CUT"))
__output__ = "\n".join(LOG)
