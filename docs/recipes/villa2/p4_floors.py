# Villa 2 floor/slab builder. DATA = dict(phase, slabs=[{name, type, level, offset_m, loops=[[(x,y)...], ...]}])
# Loops are DWG ground-frame polygons (first loop outer, others holes). Genuine Floors only: asserts IsFoundationSlab is False.
PH = DATA["phase"]
say("purged %d earlier %s elements" % (purge(PH), PH))
made = []
def build():
    for s in DATA["slabs"]:
        ft_ = find_type(FloorType, s["type"])
        assert ft_ is not None and not ft_.IsFoundationSlab, "bad floor type " + s["type"]
        lvl = level_named(s["level"])
        loops = List[CurveLoop]()
        for poly in s["loops"]:
            cl = CurveLoop(); n = len(poly)
            for i in range(n):
                a, b = poly[i], poly[(i + 1) % n]
                pa, pb = P(a[0], a[1], 0), P(b[0], b[1], 0)
                cl.Append(Line.CreateBound(XYZ(pa.X, pa.Y, lvl.Elevation), XYZ(pb.X, pb.Y, lvl.Elevation)))
            loops.Add(cl)
        f = Floor.Create(doc, loops, ft_.Id, lvl.Id)
        f.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM).Set(s.get("offset_m", 0) / FT)
        f.get_Parameter(BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL).Set(1 if s.get("structural", True) else 0)
        tag(f, PH)
        made.append((s["name"], f))
run("AMB2: floors " + PH, build)
try:
    for (nm, f) in made:
        t = doc.GetElement(f.GetTypeId()); bb = f.get_BoundingBox(None)
        say("%-16s id %d %-22s cat=%s foundation=%s z %.2f..%.2f  area %.1f m2" % (nm, f.Id.IntegerValue, type_name(t), f.Category.Name, t.IsFoundationSlab, bb.Min.Z * FT, bb.Max.Z * FT, f.get_Parameter(BuiltInParameter.HOST_AREA_COMPUTED).AsDouble() * FT * FT))
except Exception as e:
    say("verification failed: %s" % e)
__output__ = chr(10).join(LOG)
