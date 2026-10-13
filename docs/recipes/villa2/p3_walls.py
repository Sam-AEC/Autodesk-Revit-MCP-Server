# Villa 2 wall builder. Needs DATA = dict(phase, base_level, top_level, top_offset_m, outline=[(x,y)...], walls=[...])
# Walls are created on their centre line from DWG coordinates; exterior faces are verified against the footprint outline.
import math
PH = DATA["phase"]
TYPES = {"ext": "AMB2_Wall_Ext_240", "core": "AMB2_Wall_Core_240", "int": "AMB2_Wall_Int_125",
         "parapet": "AMB2_Wall_Parapet_240", "pier": "AMB2_Wall_Pier_300", "glazed": "AMB2_Wall_Glazed_100"}
LB = level_named(DATA["base_level"]); LT = level_named(DATA["top_level"]) if DATA.get("top_level") else None

def inside(pt, poly):
    x, y = pt; c = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c

def seg_dist(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

def in_any(pt):
    for poly in DATA["outlines"]:
        if inside(pt, poly): return True
    return False

say("purged %d earlier %s elements" % (purge(PH), PH))
made = {}

def preorient(w):
    """Revit puts the exterior face on the LEFT of the drawing direction. Reverse the segment so that left is outside;
    flipping afterwards would break the corner joins."""
    if w["kind"] not in ("ext", "parapet", "glazed"): return w
    (x1, y1), (x2, y2) = w["p1"], w["p2"]
    L = math.hypot(x2 - x1, y2 - y1); d = 0.6 / SC
    nx, ny = -(y2 - y1) / L, (x2 - x1) / L
    mid = ((x1 + x2) / 2, (y1 + y2) / 2)
    left = in_any((mid[0] + nx * d, mid[1] + ny * d)); right = in_any((mid[0] - nx * d, mid[1] - ny * d))
    if left and not right:
        w = dict(w); w["p1"], w["p2"] = w["p2"], w["p1"]
    elif left == right:
        say("%s: both sides %s the footprint" % (w["id"], "inside" if left else "outside"))
    return w

def build():
    DATA["walls"] = [preorient(w) for w in DATA["walls"]]
    for w in DATA["walls"]:
        wt = find_type(WallType, TYPES[w["kind"]])
        a, b = P(w["p1"][0], w["p1"][1], 0), P(w["p2"][0], w["p2"][1], 0)
        lb = level_named(w["base_level"]) if w.get("base_level") else LB
        z = lb.Elevation
        line = Line.CreateBound(XYZ(a.X, a.Y, z), XYZ(b.X, b.Y, z))
        boff = w.get("base_offset_m", 0) / FT
        if w.get("height_m"):
            lt = None; h = w["height_m"] / FT
        else:
            lt = level_named(w["top_level"]) if w.get("top_level") else LT
            off = w.get("top_offset_m", DATA.get("top_offset_m", 0)) / FT
            h = (lt.Elevation - lb.Elevation + off - boff) if lt is not None else DATA["height_m"] / FT
        wall = Wall.Create(doc, line, wt.Id, lb.Id, h, boff, False, kind_structural(w))
        if lt is not None:
            wall.get_Parameter(BuiltInParameter.WALL_HEIGHT_TYPE).Set(lt.Id)
            wall.get_Parameter(BuiltInParameter.WALL_TOP_OFFSET).Set(off)
        tag(wall, PH)
        wall.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).Set(w["id"])
        made[w["id"]] = wall
    doc.Regenerate()
    for w in DATA["walls"]:
        o = made[w["id"]].Orientation
        mid = ((w["p1"][0] + w["p2"][0]) / 2, (w["p1"][1] + w["p2"][1]) / 2)
        if w["kind"] in ("ext", "parapet", "glazed") and in_any((mid[0] + o.X * 0.6 / SC, mid[1] + o.Y * 0.6 / SC)) and not in_any((mid[0] - o.X * 0.6 / SC, mid[1] - o.Y * 0.6 / SC)):
            say("WRONG ORIENTATION %s" % w["id"])
    # allow joins at ends
    for w in DATA["walls"]:
        wall = made[w["id"]]
        try:
            WallUtils.AllowWallJoinAtEnd(wall, 0); WallUtils.AllowWallJoinAtEnd(wall, 1)
        except Exception as e: say("join %s: %s" % (w["id"], e))

def kind_structural(w):
    return w["kind"] in ("ext", "core")

run("AMB2: walls " + PH, build)
say("created %d walls" % len(made))
try:
    for w in DATA["walls"]:
        wl = made.get(w["id"])
        if wl is None: say("MISSING " + w["id"]); continue
        bb = wl.get_BoundingBox(None)
        say("%-5s id %d %-4s len %.2f m  z %.2f..%.2f" % (w["id"], wl.Id.IntegerValue, w["kind"], wl.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH).AsDouble() * FT, bb.Min.Z * FT, bb.Max.Z * FT))
except Exception as e:
    say("verification failed (transaction probably rolled back): %s" % e)
__output__ = chr(10).join(LOG)
