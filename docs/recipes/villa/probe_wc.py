# READ-ONLY: where is the back of each WC, and is it against a wall? (flat back = wider at its end; rounded bowl = narrower)
opts = Options(); opts.ComputeReferences = False; opts.DetailLevel = ViewDetailLevel.Fine
def verts(e):
    out = []
    for g in e.get_Geometry(opts):
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
walls = [w for w in tagged() if isinstance(w, Wall)]
def nearest_wall(x, y, lvl_z):
    best = (9e9, None, None)
    for w in walls:
        lo, hi = zrange_m(w)
        if not (lo <= lvl_z * FT + 0.5 and hi >= lvl_z * FT + 0.5): continue
        c = w.Location.Curve; p = c.Project(XYZ(x, y, c.GetEndPoint(0).Z))
        if p is None: continue
        d = p.Distance - w.Width / 2
        if d < best[0]: best = (d, w, p.XYZPoint)
    return best
for e in tagged("p7"):
    if not isinstance(e, FamilyInstance) or e.Symbol.FamilyName != "74_HB_Wandcloset": continue
    v = verts(e); xs = [p[0] for p in v]; ys = [p[1] for p in v]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    along_x = (x1 - x0) >= (y1 - y0)
    lo_n = [p for p in v if (p[0] if along_x else p[1]) < (x0 if along_x else y0) + 0.15 * ((x1 - x0) if along_x else (y1 - y0))]
    hi_n = [p for p in v if (p[0] if along_x else p[1]) > (x1 if along_x else y1) - 0.15 * ((x1 - x0) if along_x else (y1 - y0))]
    def width(pts): 
        q = [(p[1] if along_x else p[0]) for p in pts] or [0]; return (max(q) - min(q)) * FT
    wl, wh = width(lo_n), width(hi_n)
    back = ("west" if along_x else "south") if wl > wh else ("east" if along_x else "north")
    cx_, cy_ = (x0 + x1) / 2, (y0 + y1) / 2
    lvl = doc.GetElement(e.LevelId)
    d, w, pp = nearest_wall(cx_, cy_, lvl.Elevation)
    say("WC id %d : footprint %.2f x %.2f m ; long axis %s ; width at low end %.2f vs high end %.2f -> FLAT BACK faces %s ; centre (%.2f, %.2f) ; FacingOrientation (%.1f, %.1f) ; nearest wall face %.3f m away, wall %d (%s)" % (
        e.Id.Value, (x1 - x0) * FT, (y1 - y0) * FT, "X" if along_x else "Y", wl, wh, back, (cx_ - CX) * FT, (cy_ - CY) * FT, e.FacingOrientation.X, e.FacingOrientation.Y, d * FT, w.Id.Value if w else 0, type_name(doc.GetElement(w.GetTypeId())) if w else "-"))
    if w is not None:
        nx, ny = pp.X - cx_, pp.Y - cy_
        say("      direction from WC centre to nearest wall: (%.2f, %.2f)  -> wall is to the %s" % (nx, ny, ("east" if nx > 0 else "west") if abs(nx) > abs(ny) else ("north" if ny > 0 else "south")))
__output__ = "\n".join(LOG)
