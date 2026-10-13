# Exterior walls: the exterior face must NOT point into a room (probe 0.6 m out along the exterior normal).
def probe_inside(w):
    c = w.Location.Curve; m = c.Evaluate(0.5, True); o = w.Orientation
    lvl = doc.GetElement(w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT).AsElementId())
    p = XYZ(m.X + o.X * ft(0.6), m.Y + o.Y * ft(0.6), lvl.Elevation + 3.0)
    return doc.GetRoomAtPoint(p) is not None
ext = [w for w in tagged() if isinstance(w, Wall) and type_name(doc.GetElement(w.GetTypeId())) == "AMB_Wall_Ext_425"]
bad = [w for w in ext if probe_inside(w)]
say("exterior walls facing a room before: %d %s" % (len(bad), [w.Id.Value for w in bad]))
run("AMB: orient exterior walls (room probe)", lambda: [w.Flip() for w in bad])
bad2 = [w for w in ext if probe_inside(w)]
say("after: %d %s" % (len(bad2), [w.Id.Value for w in bad2]))
__output__ = "\n".join(LOG)
