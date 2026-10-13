# Phase 3a: foundation walls, ground-floor walls, ground slab and terraces (all tagged AMB_VILLA:p3a)
PH = "p3a"
n_old = purge(PH)
say("purged %d earlier p3a elements" % n_old)
L0 = level_named("00 begane grond"); L1 = level_named("AMB_01 First Floor")
ext, intw, core, found = [find_type(WallType, n) for n in ("AMB_Wall_Ext_425", "AMB_Wall_Int_100", "AMB_Wall_Core_200", "AMB_Wall_Found_300")]
fl_ground, fl_terrace = find_type(FloorType, "AMB_Floor_Ground_370"), find_type(FloorType, "AMB_Floor_Terrace_150")
GROUND = [(-9, -5), (10, -5), (10, 0.5), (3, 0.5), (3, 3), (-1, 3), (-1, 8), (-9, 8)]
WALL_H = 3.2 - 0.28          # ground walls stop under the first-floor slab (280 mm)

def build():
    made = {}
    made["foundation"] = poly_walls(GROUND, found, L0, 0.9, -0.9, PH)
    made["ext"] = poly_walls(GROUND, ext, L0, WALL_H, 0.0, PH)
    made["i1 garage|hall"] = [seg_wall((3, -5), (3, 0.5), core, L0, WALL_H, 0.0, PH)]
    made["i2 A|C"] = [seg_wall((-9, 3), (-1, 3), intw, L0, WALL_H, 0.0, PH)]
    made["i3 lounge|kitchen"] = [seg_wall((-3, -5), (-3, 3), intw, L0, WALL_H, 0.0, PH)]
    made["i4 kitchen|hall"] = [seg_wall((1, -5), (1, 3), intw, L0, WALL_H, 0.0, PH)]
    made["i5 study|guest"] = [seg_wall((-5, 3), (-5, 8), intw, L0, WALL_H, 0.0, PH)]
    z0 = L0.Elevation
    slabs = [("slab ground", GROUND, fl_ground), ("terrace south", [(-9, -9), (3, -9), (3, -5), (-9, -5)], fl_terrace),
             ("terrace covered", [(3, 0.5), (10, 0.5), (10, 3), (3, 3)], fl_terrace)]
    for name, pts, ft_ in slabs:
        loops = List[CurveLoop](); loops.Add(loop(pts, z0))
        f = Floor.Create(doc, loops, ft_.Id, L0.Id)
        tag(f, PH); made[name] = [f]
    return made

made = run("AMB: ground structure", build)
if made:
    for k in sorted(made):
        for e in made[k]:
            lo, hi = zrange_m(e)
            say("%-18s id %d  z %.2f .. %.2f m" % (k, e.Id.Value, lo, hi))
    say("created %d elements" % sum([len(v) for v in made.values()]))
__output__ = "\n".join(LOG)
