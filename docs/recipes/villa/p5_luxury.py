# Phase 5: garage door fix, infinity pool, deck, driveway, garden walls, lawn (tagged AMB_VILLA:p5)
PH = "p5"
say("purged %d earlier p5 elements" % purge(PH))
L0 = level_named("00 begane grond")
FT_FLOOR_SRC = find_type(FloorType, "AMB_Floor_Terrace_150")
def mat(name, rgb, transp=0):
    for m in FilteredElementCollector(doc).OfClass(Material):
        if m.Name == name: return m.Id
    mid = Material.Create(doc, name); m = doc.GetElement(mid); m.Color = Color(*rgb)
    if transp: m.Transparency = transp
    return mid
def floor_type(name, mm_, matname, rgb, transp=0):
    t = find_type(FloorType, name)
    if t is None:
        t = FT_FLOOR_SRC.Duplicate(name)
        cs = t.GetCompoundStructure()
        L = List[CompoundStructureLayer](); L.Add(CompoundStructureLayer(mmf(mm_), MaterialFunctionAssignment.Structure, mat(matname, rgb, transp)))
        cs.SetLayers(L); t.SetCompoundStructure(cs)
    return t
def put_floor(outer, hole, ftype, offset_m, name):
    loops = List[CurveLoop](); loops.Add(loop(outer, L0.Elevation))
    if hole: loops.Add(loop(hole, L0.Elevation))
    f = Floor.Create(doc, loops, ftype.Id, L0.Id)
    p = f.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
    if p is not None and not p.IsReadOnly: p.Set(ft(offset_m))
    tag(f, PH); return f

def build():
    out = []
    for old in list(FilteredElementCollector(doc).OfClass(TopographySurface)):
        mp = old.get_Parameter(BuiltInParameter.MATERIAL_ID_PARAM)
        if mp is not None and mp.AsElementId() != ElementId.InvalidElementId and doc.GetElement(mp.AsElementId()).Name == "AMB_Lawn":
            doc.Delete(old.Id); out.append("removed previous lawn")
    found, parapet = find_type(WallType, "AMB_Wall_Found_300"), find_type(WallType, "AMB_Wall_Parapet_250")
    t_conc = find_type(FloorType, "AMB_Floor_Ground_370")
    t_water = floor_type("AMB_Floor_Water_50", 50, "AMB_Water", (70, 150, 200), 45)
    t_lawn_mat = mat("AMB_Lawn", (96, 142, 74))
    POOL = [(-8, -14), (2, -14), (2, -10), (-8, -10)]
    DECK = [(-10.5, -17), (4.5, -17), (4.5, -9), (-10.5, -9)]
    put_floor(DECK, POOL, find_type(FloorType, "AMB_Floor_Terrace_150"), 0.0, "pool deck"); out.append("pool deck")
    put_floor(POOL, None, t_conc, -1.6, "pool floor"); out.append("pool basin floor (-1.60 m)")
    put_floor(POOL, None, t_water, -0.2, "water"); out.append("pool water surface (-0.20 m)")
    for i in range(4):
        a, b = POOL[i], POOL[(i + 1) % 4]
        w = seg_wall(a, b, found, L0, 1.6, -1.6, PH); out.append("pool wall")
    put_floor([(4.5, -18), (9.2, -18), (9.2, -5), (4.5, -5)], None, find_type(FloorType, "AMB_Floor_Terrace_150"), 0.0, "driveway"); out.append("driveway")
    # garden wall with a gate gap for the drive
    for (a, b) in (((-12, -18), (4.5, -18)), ((9.2, -18), (13, -18)), ((13, -18), (13, 11)), ((13, 11), (-12, 11)), ((-12, 11), (-12, -18))):
        seg_wall(a, b, parapet, L0, 2.2, 0.0, PH); out.append("garden wall")
    # lawn
    pts = List[XYZ]()
    for (x, y) in ((-12, -18), (13, -18), (13, 11), (-12, 11)): pts.Add(XYZ(CX + ft(x), CY + ft(y), ft(-0.25)))
    topo = TopographySurface.Create(doc, pts)
    topo.get_Parameter(BuiltInParameter.MATERIAL_ID_PARAM).Set(t_lawn_mat); tag_ok = True
    try: tag(topo, PH)
    except Exception: pass
    out.append("lawn (topography surface, 25 x 29 m)")
    return out
res = run("AMB: luxury exterior", build)
for line in (res or []): say(line)
__output__ = "\n".join(LOG)
