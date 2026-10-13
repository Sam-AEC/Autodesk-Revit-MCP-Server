# Villa 2 roofs: footprint roofs from DWG polygons. DATA = dict(phase, roofs=[{name,type,level,offset_m,pts,slope_deg,sloped_edges|None}]).
# sloped_edges: list of edge indices that define slope (None = all); slope_deg 0 = flat.
import math
PH = DATA["phase"]
say("purged %d earlier %s elements" % (purge(PH), PH))
made = []
def build():
    for r in DATA["roofs"]:
        rt = find_type(RoofType, r["type"]); lvl = level_named(r["level"])
        ca = CurveArray(); pts = r["pts"]; n = len(pts)
        for i in range(n):
            a, b = P(pts[i][0], pts[i][1], 0), P(pts[(i + 1) % n][0], pts[(i + 1) % n][1], 0)
            ca.Append(Line.CreateBound(XYZ(a.X, a.Y, lvl.Elevation), XYZ(b.X, b.Y, lvl.Elevation)))
        mca = clr.Reference[ModelCurveArray]()
        roof = doc.Create.NewFootPrintRoof(ca, lvl, rt, mca)
        mcs = mca.Value
        deg = r.get("slope_deg", 0)
        for i in range(mcs.Size):
            mc = mcs.get_Item(i)
            on = deg > 0 and (r.get("sloped_edges") is None or i in r["sloped_edges"])
            roof.set_DefinesSlope(mc, on)
            if on: roof.set_SlopeAngle(mc, math.tan(math.radians(deg)))
        roof.get_Parameter(BuiltInParameter.ROOF_LEVEL_OFFSET_PARAM).Set(r.get("offset_m", 0) / FT)
        tag(roof, PH); roof.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).Set(r["name"])
        made.append((r["name"], roof))
run("AMB2: roofs " + PH, build)
try:
    for (nm, rf) in made:
        bb = rf.get_BoundingBox(None)
        say("%-12s id %d type %s z %.2f..%.2f  area %.1f m2" % (nm, rf.Id.IntegerValue, type_name(doc.GetElement(rf.GetTypeId())), bb.Min.Z * FT, bb.Max.Z * FT, rf.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED).AsDouble() * FT * FT))
except Exception as e:
    say("verification failed: %s" % e)
__output__ = chr(10).join(LOG)
