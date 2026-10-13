# Spatial primitive v0: place a fixture with its BACK/HEAD touching a wall face, measured from real geometry (mesh/solid vertices),
# never from the bounding box (which includes hidden extent) and never from an assumed origin.
import math
import Autodesk.Revit.DB.Structure as Structure
PH = "p7"
L0, L1 = level_named("00 begane grond"), level_named("AMB_01 First Floor")
KINDS = {"Bed04": "bed", "Bed01": "bed", "AMB_Bed_King": "bed", "74_HB_Wandcloset": "wc"}
NS_FAM = "Mesa de noche - 3D - Genérico - Con cajón y estante"
_opts = Options(); _opts.ComputeReferences = False; _opts.DetailLevel = ViewDetailLevel.Fine
def verts(e):
    out = []
    for g in e.get_Geometry(_opts):
        geoms = g.GetInstanceGeometry() if isinstance(g, GeometryInstance) else [g]
        for s in geoms:
            if isinstance(s, Mesh):
                for v in s.Vertices: out.append((v.X, v.Y, v.Z))
            elif isinstance(s, Solid) and s.Volume > 1e-9:
                for ed in s.Edges:
                    c = ed.AsCurve()
                    for t in (0.0, 1.0):
                        p = c.Evaluate(t, True); out.append((p.X, p.Y, p.Z))
    return out
def extent(e):                       # real visible extent, villa-local metres: (xmin, ymin, xmax, ymax)
    doc.Regenerate(); v = verts(e)
    xs = [(p[0] - CX) * FT for p in v]; ys = [(p[1] - CY) * FT for p in v]
    return min(xs), min(ys), max(xs), max(ys)
def back_dir(e, kind):               # unit vector (dx, dy) from the fixture's centre towards its back/head
    doc.Regenerate(); v = verts(e)
    xs = [p[0] for p in v]; ys = [p[1] for p in v]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys); ax = (x1 - x0) >= (y1 - y0)
    lo, hi = (x0, x1) if ax else (y0, y1); span = hi - lo
    low = [p for p in v if (p[0] if ax else p[1]) < lo + 0.15 * span]; high = [p for p in v if (p[0] if ax else p[1]) > hi - 0.15 * span]
    if kind == "bed":
        head_low = max([p[2] for p in low] or [0]) > max([p[2] for p in high] or [0])
    else:
        w = lambda pts: (max([(p[1] if ax else p[0]) for p in pts] or [0]) - min([(p[1] if ax else p[0]) for p in pts] or [0]))
        head_low = w(low) > w(high)
    return ((-1.0 if head_low else 1.0), 0.0) if ax else (0.0, (-1.0 if head_low else 1.0))
def rotate_to(e, kind, want):        # turn the fixture so its back points along `want` (a cardinal unit vector)
    d = back_dir(e, kind)
    ang = math.atan2(want[1], want[0]) - math.atan2(d[1], d[0])
    if abs(ang) > 1e-6:
        p = e.Location.Point
        ElementTransformUtils.RotateElement(doc, e.Id, Line.CreateBound(p, p + XYZ.BasisZ), ang)
SIDE = {"W": (-1, 0), "E": (1, 0), "N": (0, 1), "S": (0, -1)}      # side of the ROOM the wall is on
def place_back_to_wall(fam, lvl, wall_side, face, along, kind=None, gap=0.01):
    kind = kind or KINDS.get(fam, "plain")
    s = [x for x in FilteredElementCollector(doc).OfClass(FamilySymbol) if x.FamilyName == fam][0]
    if not s.IsActive: s.Activate()
    ax_, ay_ = (face, along) if wall_side in "WE" else (along, face)
    fi = doc.Create.NewFamilyInstance(XYZ(CX + ft(ax_), CY + ft(ay_), 0.0), s, lvl, Structure.StructuralType.NonStructural)
    if kind != "plain": rotate_to(fi, kind, SIDE[wall_side])
    x0, y0, x1, y1 = extent(fi)
    if wall_side == "W": dx, dy = face + gap - x0, along - (y0 + y1) / 2
    elif wall_side == "E": dx, dy = face - gap - x1, along - (y0 + y1) / 2
    elif wall_side == "N": dx, dy = along - (x0 + x1) / 2, face - gap - y1
    else: dx, dy = along - (x0 + x1) / 2, face + gap - y0
    ElementTransformUtils.MoveElement(doc, fi.Id, XYZ(ft(dx), ft(dy), 0)); tag(fi, PH)
    return fi
def old():
    return [e for e in tagged(PH) if isinstance(e, FamilyInstance) and (e.Symbol.FamilyName in KINDS or e.Symbol.FamilyName == NS_FAM)]
def rm():
    ids = List[ElementId]([e.Id for e in old()])
    if ids.Count: doc.Delete(ids)
    return ids.Count
say("removed %s earlier beds/nightstands/WCs" % run("AMB: remove beds and WCs", rm))
INT, EXT = 0.05, 0.2125                                      # half wall thickness (m)
# (family, level, side of the room the wall is on, wall face coordinate, position along the wall, room)
JOBS = [("Bed04", L0, "W", -5 + INT, 5.5, "Guest Suite"), ("AMB_Bed_King", L1, "N", 0.5 - INT, 7.0, "Master Bedroom"),
        ("Bed04", L1, "E", -4.5 - INT, -1.75, "Bedroom 2"), ("Bed04", L1, "W", -4.5 + INT, -1.75, "Bedroom 3"), ("Bed04", L1, "E", -5 - INT, 5.5, "Bedroom 4"),
        ("74_HB_Wandcloset", L1, "E", 10 - EXT, 1.0, "Master Ensuite"), ("74_HB_Wandcloset", L1, "E", -1 - EXT, 4.2, "Family Bathroom")]
placed = []
def build():
    for (fam, lvl, side, face, along, room) in JOBS:
        b = place_back_to_wall(fam, lvl, side, face, along); placed.append((room, fam, b))
        if KINDS[fam] == "bed":
            x0, y0, x1, y1 = extent(b); wd = (y1 - y0) if side in "WE" else (x1 - x0)
            for k in (-1, 1):
                a = ((y0 + y1) / 2 + k * (wd / 2 + 0.28)) if side in "WE" else ((x0 + x1) / 2 + k * (wd / 2 + 0.28))
                n = place_back_to_wall(NS_FAM, lvl, side, face, a, kind="plain"); placed.append((room, "nightstand", n))
run("AMB: beds and WCs back-to-wall (geometry-measured)", build)
for (room, fam, e) in placed:
    if fam == "nightstand": continue
    x0, y0, x1, y1 = extent(e); say("%-15s %-17s footprint x %.2f..%.2f  y %.2f..%.2f m" % (room, fam, x0, x1, y0, y1))
__output__ = "\n".join(LOG)
