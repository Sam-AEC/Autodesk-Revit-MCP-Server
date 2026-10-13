# Villa 2 stair: ground -> first floor, U-shape in the stair hall (two straight runs and a half landing at the south end).
# Run 1 starts at the hall's north-east, runs south; run 2 returns north on the west side and tops out at the first floor.
PH = DATA.get("phase", "p6_stair")
say("purged %d earlier %s elements" % (purge(PH), PH))
L0, L1 = level_named(DATA.get("from_level", "00 begane grond")), level_named(DATA.get("to_level", "AMB2_01 First Floor"))
st_type = find_type(StairsType, "300_27_beton trap")
say("stairs type %s ; tread depth %.0f mm ; max riser %.0f mm" % (type_name(st_type), st_type.MinTreadDepth * 304.8, st_type.MaxRiserHeight * 304.8))
RUN_W = 1.10                                    # m
TREAD = 0.28; NRISE = DATA.get("risers", 20)
RISER = (L1.Elevation - L0.Elevation) / NRISE   # feet
X1, X2 = 1638.4, 1623.2                         # DWG x of the run centre lines (east flight, west flight)
Y_TOP = DATA["y_top"]
Y_LAND = Y_TOP - (NRISE // 2 - 1) * TREAD / SC                 # run 1 has 9 treads (10 risers); the landing is the 10th tread
LAND = [[DATA["landing"][0][0], DATA["landing"][0][1]], [DATA["landing"][1][0], DATA["landing"][1][1]], [DATA["landing"][2][0], Y_LAND], [DATA["landing"][3][0], Y_LAND]]
sid = None
scope = StairsEditScope(doc, "AMB2: stair")
try:
    sid = scope.Start(L0.Id, L1.Id)
    t = Transaction(doc, "AMB2: stair runs"); t.Start()
    try:
        st = doc.GetElement(sid)
        st.ChangeTypeId(st_type.Id)
        try: st.DesiredRisersNumber = NRISE
        except Exception as e: say("desired risers: %s" % e)
        try: st.ActualTreadDepth = TREAD / FT
        except Exception as e: say("tread depth: %s" % e)
        a, b = P(X1, Y_TOP, 0), P(X1, Y_LAND, 0)
        r1 = StairsRun.CreateStraightRun(doc, sid, Line.CreateBound(XYZ(a.X, a.Y, L0.Elevation), XYZ(b.X, b.Y, L0.Elevation)), StairsRunJustification.Center)
        r1.ActualRunWidth = RUN_W / FT
        say("run1 base %.3f top %.3f len %.2f m" % (r1.BaseElevation * FT, r1.TopElevation * FT, a.DistanceTo(b) * FT))
        c, d = P(X2, Y_LAND, 0), P(X2, Y_TOP, 0)
        r2 = StairsRun.CreateStraightRun(doc, sid, Line.CreateBound(XYZ(c.X, c.Y, L0.Elevation), XYZ(d.X, d.Y, L0.Elevation)), StairsRunJustification.Center)
        r2.ActualRunWidth = RUN_W / FT
        total = L1.Elevation - L0.Elevation
        ok2 = False
        for attempt in range(3):
            try:
                try: r2.ExtensionBelowRiserBase = 0.0
                except: pass
                if attempt == 0:   r2.TopElevation = total; r2.BaseElevation = r1.TopElevation       # raise the top first, then lift the base onto the landing
                elif attempt == 1: r2.BaseElevation = r1.TopElevation; r2.TopElevation = total
                else:
                    r2.BaseElevation = r1.TopElevation + 0.01; r2.TopElevation = total
                ok2 = True; break
            except Exception as e: say("run2 elevations (try %d): %s" % (attempt + 1, e))
        say("run2 base %.3f top %.3f" % (r2.BaseElevation * FT, r2.TopElevation * FT))
        cl = CurveLoop()
        pts = [P(x, y, 0) for (x, y) in LAND]
        pts = [P(LAND[0][0], LAND[0][1], 0), P(LAND[1][0], LAND[1][1], 0), P(LAND[2][0], Y_LAND, 0), P(LAND[3][0], Y_LAND, 0)]
        z = r1.TopElevation + L0.Elevation
        for i in range(4):
            cl.Append(Line.CreateBound(XYZ(pts[i].X, pts[i].Y, z), XYZ(pts[(i + 1) % 4].X, pts[(i + 1) % 4].Y, z)))
        StairsLanding.CreateSketchedLanding(doc, sid, cl, r1.TopElevation)
        t.Commit()
    except Exception as e:
        say("runs failed: " + str(e)); t.RollBack(); raise
    scope.Commit(Swallow())
except Exception as e:
    say("STAIR FAILED: " + str(e))
    try: scope.Cancel()
    except: pass
    sid = None
if sid is not None:
    s = doc.GetElement(sid)
    run("AMB2: tag stair", lambda: tag(s, PH))
    p = lambda b: s.get_Parameter(b)
    say("stair id %d ; risers %s ; riser %.0f mm ; tread %.0f mm" % (sid.IntegerValue, p(BuiltInParameter.STAIRS_ACTUAL_NUM_RISERS).AsInteger(), p(BuiltInParameter.STAIRS_ACTUAL_RISER_HEIGHT).AsDouble() * 304.8, p(BuiltInParameter.STAIRS_ACTUAL_TREAD_DEPTH).AsDouble() * 304.8))
    lo, hi = None, None
    bb = s.get_BoundingBox(None)
    say("stair z %.3f .. %.3f ; plan x %.2f..%.2f y %.2f..%.2f (local m)" % (bb.Min.Z * FT, bb.Max.Z * FT, (bb.Min.X - OX) * FT, (bb.Max.X - OX) * FT, (bb.Min.Y - OY) * FT, (bb.Max.Y - OY) * FT))
__output__ = chr(10).join(LOG)
