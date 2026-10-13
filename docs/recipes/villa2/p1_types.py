# Villa 2, phase 1: levels, materials and layered wall / floor / roof types. Idempotent.
# Run as prelude.py + this file. Levels are shared with villa 1 only for the ground level ("00 begane grond").
MAT = {
    "AMB2_Render":   (236, 224, 200),   # sand-coloured lime render
    "AMB2_Block":    (205, 198, 186),
    "AMB2_Plaster":  (246, 243, 236),
    "AMB2_Concrete": (150, 150, 150),
    "AMB2_Screed":   (190, 186, 178),
    "AMB2_Tile":     (150, 92, 62),     # terracotta roof tile
    "AMB2_Insul":    (240, 214, 90),
    "AMB2_Gypsum":   (236, 236, 232),
    "AMB2_Membrane": (60, 62, 66),
    "AMB2_Gravel":   (170, 165, 158),
    "AMB2_Stone":    (214, 200, 170),   # limestone trim, coping, plinth
    "AMB2_Zellige":  (40, 96, 110),     # glazed tile accent
    "AMB2_Timber":   (110, 72, 44),
    "AMB2_Frame":    (70, 58, 50),
    "AMB2_Glass":    (190, 215, 225),
    "AMB2_Floor":    (212, 196, 170),
}
def mat_id(name):
    for m in FilteredElementCollector(doc).OfClass(Material):
        if m.Name == name: return m.Id
    mid = Material.Create(doc, name)
    m = doc.GetElement(mid)
    r, g, b = MAT.get(name, (180, 180, 180))
    m.Color = Color(r, g, b)
    if name == "AMB2_Glass": m.Transparency = 60
    return mid

F = MaterialFunctionAssignment
def layers(spec):
    L = List[CompoundStructureLayer]()
    for (width_mm, func, mat) in spec:
        L.Add(CompoundStructureLayer(mmf(width_mm), func, mat_id(mat)))
    return L

def make_type(cls, src, name, spec):
    t = find_type(cls, name)
    created = t is None
    if created: t = src.Duplicate(name)
    cs = t.GetCompoundStructure()
    cs.SetLayers(layers(spec))
    core = [i for i, (w, f, m) in enumerate(spec) if f == F.Structure][0]
    try:
        cs.SetNumberOfShellLayers(ShellLayerType.Exterior, core)
        cs.SetNumberOfShellLayers(ShellLayerType.Interior, len(spec) - 1 - core)
    except Exception as e: say("shell layers %s: %s" % (name, e))
    try: cs.StructuralMaterialIndex = core
    except Exception as e: say("structural index %s: %s" % (name, e))
    t.SetCompoundStructure(cs)
    return t, created

WALLS = {   # exterior -> interior
    "AMB2_Wall_Ext_240": [(25, F.Finish1, "AMB2_Render"), (200, F.Structure, "AMB2_Block"), (15, F.Finish2, "AMB2_Plaster")],
    "AMB2_Wall_Core_240": [(15, F.Finish2, "AMB2_Plaster"), (210, F.Structure, "AMB2_Block"), (15, F.Finish2, "AMB2_Plaster")],
    "AMB2_Wall_Int_125": [(12.5, F.Finish2, "AMB2_Plaster"), (100, F.Structure, "AMB2_Block"), (12.5, F.Finish2, "AMB2_Plaster")],
    "AMB2_Wall_Parapet_240": [(25, F.Finish1, "AMB2_Render"), (200, F.Structure, "AMB2_Concrete"), (15, F.Finish2, "AMB2_Render")],
    "AMB2_Wall_Plinth_300": [(300, F.Structure, "AMB2_Stone")],
    "AMB2_Wall_Glazed_100": [(100, F.Structure, "AMB2_Glass")],
    "AMB2_Wall_Pier_300": [(300, F.Structure, "AMB2_Render")],
}
FLOORS = {
    "AMB2_Floor_Ground_300": [(20, F.Finish1, "AMB2_Floor"), (60, F.Finish1, "AMB2_Screed"), (220, F.Structure, "AMB2_Concrete")],
    "AMB2_Floor_Upper_280":  [(20, F.Finish1, "AMB2_Floor"), (60, F.Finish1, "AMB2_Screed"), (200, F.Structure, "AMB2_Concrete")],
    "AMB2_Floor_Terrace_280": [(30, F.Finish1, "AMB2_Stone"), (250, F.Structure, "AMB2_Concrete")],
}
ROOFS = {
    "AMB2_Roof_Flat_400": [(20, F.Finish1, "AMB2_Gravel"), (0, F.Membrane, "AMB2_Membrane"), (180, F.Insulation, "AMB2_Insul"), (200, F.Structure, "AMB2_Concrete")],
    "AMB2_Roof_Tile_250": [(30, F.Finish1, "AMB2_Tile"), (0, F.Membrane, "AMB2_Membrane"), (220, F.Structure, "AMB2_Concrete")],
}

def phase(levels):
    out = []
    ground = level_named("00 begane grond")
    out.append("ground level %s at %.3f m" % (lname(ground), ground.Elevation * FT))
    for nm, z in levels:
        l = level_named(nm)
        if l is None:
            l = Level.Create(doc, ft(z)); l.Name = nm
            out.append("level created: %s at %.3f m" % (nm, z))
        else:
            if abs(l.Elevation * FT - z) > 0.001:
                l.Elevation = ft(z)
            out.append("level exists: %s at %.3f m" % (nm, l.Elevation * FT))
    def pick(cls, wall=False):
        for x in FilteredElementCollector(doc).OfClass(cls):
            if wall and x.Kind != WallKind.Basic: continue
            if x.GetCompoundStructure() is not None and not type_name(x).startswith("AMB") and not (cls == FloorType and x.IsFoundationSlab):
                return x
    src = {WallType: pick(WallType, True), FloorType: pick(FloorType), RoofType: pick(RoofType)}
    for cls, table in ((WallType, WALLS), (FloorType, FLOORS), (RoofType, ROOFS)):
        for name in sorted(table):
            t, created = make_type(cls, src[cls], name, table[name])
            out.append("%s %s" % ("created" if created else "updated", name))
    return out
