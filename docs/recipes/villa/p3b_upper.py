# Phase 3b: first-floor walls, first-floor slab (with stair opening), parapet (roof comes from the add-in command) (tagged AMB_VILLA:p3b)
PH = "p3b"
say("purged %d earlier p3b elements" % purge(PH))
L1 = level_named("AMB_01 First Floor"); L2 = level_named("AMB_02 Roof")
ext, intw, parapet = [find_type(WallType, n) for n in ("AMB_Wall_Ext_425", "AMB_Wall_Int_100", "AMB_Wall_Parapet_250")]
fl_upper, roof_t = find_type(FloorType, "AMB_Floor_Upper_280"), find_type(RoofType, "AMB_Roof_Flat_440")
UPPER = [(-9, -5), (10, -5), (10, 3), (-1, 3), (-1, 8), (-9, 8)]
STAIR_HOLE = [(1.8, -4.1), (2.8, -4.1), (2.8, 0.6), (1.8, 0.6)]
INTERIOR = {"p1 bed2|bed3": ((-4.5, -5), (-4.5, 1.5)), "p2 bed3|gallery": ((0, -5), (0, 1.5)), "c1 bedrooms|corridor": ((-9, 1.5), (0, 1.5)),
            "p3 gallery|master": ((3.5, -5), (3.5, 3)), "p5 master|dressing": ((3.5, 0.5), (10, 0.5)), "p6 dressing|ensuite": ((6.5, 0.5), (6.5, 3)),
            "p7 bed4|bath": ((-5, 3), (-5, 8)), "p8 A|C": ((-9, 3), (-1, 3))}

for nm, obj in (("L1", L1), ("L2", L2), ("ext", ext), ("intw", intw), ("parapet", parapet), ("fl_upper", fl_upper), ("roof_t", roof_t)):
    if obj is None: say("MISSING: " + nm)

def build():
    made = {}
    say("stage walls")
    made["upper ext"] = poly_walls(UPPER, ext, L1, 3.2, 0.0, PH)
    made["upper int"] = [seg_wall(a, b, intw, L1, 3.2, 0.0, PH) for (a, b) in INTERIOR.values()]
    say("stage slab")
    zl = L1.Elevation
    loops = List[CurveLoop](); loops.Add(loop(UPPER, zl)); loops.Add(loop(STAIR_HOLE, zl))
    slab = Floor.Create(doc, loops, fl_upper.Id, L1.Id); tag(slab, PH); made["slab upper"] = [slab]
    say("stage parapet")
    made["parapet"] = poly_walls(UPPER, parapet, L2, 0.94, 0.0, PH)
    return made

made = run("AMB: first floor, roof, parapet", build)
if made:
    for k in sorted(made):
        zs = [zrange_m(e) for e in made[k]]
        say("%-10s %2d elements  z %.2f .. %.2f m" % (k, len(made[k]), min([a for a, b in zs]), max([b for a, b in zs])))
    say("created %d elements" % sum([len(v) for v in made.values()]))
__output__ = "\n".join(LOG)
