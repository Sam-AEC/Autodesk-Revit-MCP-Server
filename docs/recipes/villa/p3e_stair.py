# Phase 3e: straight concrete stair from level 00 to AMB_01 through the slab opening.
PH = "p3e"
say("purged %d earlier p3e elements" % purge(PH))
L0, L1 = level_named("00 begane grond"), level_named("AMB_01 First Floor")
st_type = find_type(StairsType, "300_27_beton trap")
say("stairs type found: %s" % (st_type is not None))
X = 2.3; Y0, Y1 = -3.4, 0.5           # run centreline (villa-local metres): 3.9 m = 17 treads of 230 mm -> 18 risers of ~178 mm = 3.2 m
sid = None
scope = StairsEditScope(doc, "AMB: stair")
try:
    sid = scope.Start(L0.Id, L1.Id)
    t = Transaction(doc, "AMB: stair run"); t.Start()
    try:
        line = Line.CreateBound(XYZ(CX + ft(X), CY + ft(Y0), L0.Elevation), XYZ(CX + ft(X), CY + ft(Y1), L0.Elevation))
        srun = StairsRun.CreateStraightRun(doc, sid, line, StairsRunJustification.Center)
        srun.ActualRunWidth = ft(1.0)
        if st_type is not None:
            doc.GetElement(sid).ChangeTypeId(st_type.Id)
        t.Commit()
    except Exception as e:
        say("run failed: " + str(e)); t.RollBack(); raise
    scope.Commit(Swallow())
except Exception as e:
    say("STAIR FAILED: " + str(e))
    try: scope.Cancel()
    except: pass
    sid = None
if sid is not None:
    # the slab opening is 4.7 m long; close everything north of the stair's top riser with a matching floor patch
    fl = find_type(FloorType, "AMB_Floor_Upper_280")
    def patch():
        for (y0, y1) in ((-4.1, -3.4), (0.5, 0.6)):          # the slab opening is y -4.1 .. 0.6; the stair covers -3.4 .. 0.5
            loops = List[CurveLoop](); loops.Add(loop([(1.8, y0), (2.8, y0), (2.8, y1), (1.8, y1)], L1.Elevation))
            f = Floor.Create(doc, loops, fl.Id, L1.Id); tag(f, PH)
    run("AMB: close slab opening above the stair", patch)
    s = doc.GetElement(sid)
    def tg(): tag(s, PH)
    run("AMB: tag stair", tg)
    lo, hi = zrange_m(s)
    p_r = s.get_Parameter(BuiltInParameter.STAIRS_ACTUAL_NUM_RISERS)
    p_rh = s.get_Parameter(BuiltInParameter.STAIRS_ACTUAL_RISER_HEIGHT)
    p_t = s.get_Parameter(BuiltInParameter.STAIRS_ACTUAL_TREAD_DEPTH)
    say("stair id %d  z %.2f .. %.2f m ; risers %s ; riser %.0f mm ; tread %.0f mm" % (
        sid.Value, lo, hi, p_r.AsInteger() if p_r else "?", (p_rh.AsDouble() * 304.8) if p_rh else -1, (p_t.AsDouble() * 304.8) if p_t else -1))
__output__ = "\n".join(LOG)
