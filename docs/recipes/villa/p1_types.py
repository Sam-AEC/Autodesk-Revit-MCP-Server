# Phase 1: levels, materials, real layered wall / floor / roof / ceiling types. Idempotent.
MAT_COLORS = {
    "AMB_Brick": (156, 84, 62), "AMB_CavityAir": (225, 235, 240), "AMB_Insulation": (240, 214, 90),
    "AMB_SandLimeBlock": (214, 208, 196), "AMB_Plaster": (245, 243, 238), "AMB_Concrete": (150, 150, 150),
    "AMB_Screed": (190, 186, 178), "AMB_Gypsum": (236, 236, 232), "AMB_RoofMembrane": (60, 62, 66),
    "AMB_Gravel": (170, 165, 158), "AMB_StudCore": (205, 190, 150), "AMB_Paving": (128, 124, 118),
}
def mat_id(name):
    for m in FilteredElementCollector(doc).OfClass(Material):
        if m.Name == name: return m.Id
    mid = Material.Create(doc, name)
    m = doc.GetElement(mid)
    r, g, b = MAT_COLORS.get(name, (180, 180, 180))
    m.Color = Color(r, g, b)
    return mid

F = MaterialFunctionAssignment

def layers(spec):
    L = List[CompoundStructureLayer]()
    for (width_mm, func, mat) in spec:
        L.Add(CompoundStructureLayer(mmf(width_mm), func, mat_id(mat)))
    return L

def structure_index(spec):
    for i, (w, f, m) in enumerate(spec):
        if f == F.Structure: return i
    return 0

def make_type(cls, src, name, spec):
    t = find_type(cls, name)
    created = t is None
    if created:
        t = src.Duplicate(name)
    cs = t.GetCompoundStructure()          # keep the end-cap condition that is right for this element kind
    cs.SetLayers(layers(spec))
    core = structure_index(spec)
    # mark the core explicitly: everything before it is the exterior shell, everything after the interior shell
    try:
        cs.SetNumberOfShellLayers(ShellLayerType.Exterior, core)
        cs.SetNumberOfShellLayers(ShellLayerType.Interior, len(spec) - 1 - core)
    except Exception as e:
        say("shell layers not set for %s: %s" % (name, e))
    try: cs.StructuralMaterialIndex = core
    except Exception as e: say("structural index not set for %s: %s" % (name, e))
    ok, why = False, ""
    try:
        D = System.Collections.Generic.IDictionary
        errs = clr.Reference[D[System.Int32, CompoundStructureError]]()
        two = clr.Reference[D[System.Int32, System.Int32]]()
        ok = cs.IsValid(doc, errs, two)
        if not ok:
            why = "; ".join(["layer %s: %s" % (k, errs.Value[k]) for k in errs.Value.Keys])
            if not why: why = "no layer-level error reported (layers=%d, core=%d, width=%.1f mm)" % (cs.LayerCount, core, cs.GetWidth() * 304.8)
    except Exception as e:
        why = "validity check unavailable: " + str(e)
    if not ok:
        say("INVALID %s -> %s" % (name, why))
    t.SetCompoundStructure(cs)
    return t, created

WALLS = {   # exterior -> interior
    "AMB_Wall_Ext_425": [(100, F.Finish1, "AMB_Brick"), (40, F.Insulation, "AMB_CavityAir"), (120, F.Insulation, "AMB_Insulation"),
                         (150, F.Structure, "AMB_SandLimeBlock"), (15, F.Finish2, "AMB_Plaster")],
    "AMB_Wall_Int_100":  [(12.5, F.Finish2, "AMB_Gypsum"), (75, F.Structure, "AMB_StudCore"), (12.5, F.Finish2, "AMB_Gypsum")],
    "AMB_Wall_Core_200": [(200, F.Structure, "AMB_SandLimeBlock")],
    "AMB_Wall_Found_300": [(300, F.Structure, "AMB_Concrete")],
    "AMB_Wall_Parapet_250": [(100, F.Finish1, "AMB_Brick"), (150, F.Structure, "AMB_Concrete")],
}
FLOORS = {
    "AMB_Floor_Ground_370": [(70, F.Finish1, "AMB_Screed"), (100, F.Insulation, "AMB_Insulation"), (200, F.Structure, "AMB_Concrete")],
    "AMB_Floor_Upper_280":  [(60, F.Finish1, "AMB_Screed"), (20, F.Insulation, "AMB_Insulation"), (200, F.Structure, "AMB_Concrete")],
    "AMB_Floor_Terrace_150": [(40, F.Finish1, "AMB_Paving"), (110, F.Structure, "AMB_Concrete")],
}
ROOFS = {"AMB_Roof_Flat_440": [(20, F.Finish1, "AMB_Gravel"), (0, F.Membrane, "AMB_RoofMembrane"), (220, F.Insulation, "AMB_Insulation"), (200, F.Structure, "AMB_Concrete")]}
CEILINGS = {"AMB_Ceiling_Gypsum_15": [(15, F.Finish1, "AMB_Gypsum")]}

def phase():
    out = []
    ground = level_named("00 begane grond")
    out.append("ground level: %s at %.3f m" % (ground.Name, ground.Elevation * FT))
    for nm, z in (("AMB_01 First Floor", 3.2), ("AMB_02 Roof", 6.4)):
        if level_named(nm) is None:
            l = Level.Create(doc, ft(z)); l.Name = nm
            out.append("level created: %s at %.2f m" % (nm, z))
        else:
            out.append("level exists: " + nm)
    def first_with_structure(cls, only_basic_walls=False):
        for x in FilteredElementCollector(doc).OfClass(cls):
            if only_basic_walls and x.Kind != WallKind.Basic: continue
            if x.GetCompoundStructure() is not None and not type_name(x).startswith("AMB_"):
                return x
        return None
    src = {WallType: first_with_structure(WallType, True), FloorType: first_with_structure(FloorType),
           RoofType: first_with_structure(RoofType), CeilingType: first_with_structure(CeilingType)}
    for k, v in src.items():
        out.append("source for %s: %s" % (k.__name__, type_name(v) if v is not None else "NONE"))
    for cls, table in ((WallType, WALLS), (FloorType, FLOORS), (RoofType, ROOFS), (CeilingType, CEILINGS)):
        for name in sorted(table):
            t, created = make_type(cls, src[cls], name, table[name])
            out.append("%s %s" % ("created" if created else "updated", name))
    return out

res = run("AMB: villa types and levels", phase)
for line in (res or []): say(line)
for cls, table in ((WallType, WALLS), (FloorType, FLOORS), (RoofType, ROOFS), (CeilingType, CEILINGS)):
    for name in sorted(table):
        t = find_type(cls, name)
        want = sum([w for (w, f, m) in table[name]])
        got = t.GetCompoundStructure().GetWidth() * 304.8 if t is not None else -1
        n = t.GetCompoundStructure().LayerCount if t is not None else 0
        say("CHECK %-22s layers=%d  thickness=%.1f mm (expected %.1f) %s" % (name, n, got, want, "OK" if abs(got - want) < 0.5 else "MISMATCH"))
__output__ = "\n".join(LOG)
