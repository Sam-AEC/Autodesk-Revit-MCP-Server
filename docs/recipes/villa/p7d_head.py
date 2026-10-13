# 1) delete the old stair patch (the 1.00 x 0.90 m floor that overlaps the moved stair)
def rm():
    d = doc.GetElement(ElementId(23840387))
    if d is not None and isinstance(d, Floor): doc.Delete(d.Id); say("deleted old slab patch 23840387")
run("AMB: remove old stair patch", rm)
# 2) which end is the headboard? slice the geometry of each placed bed by its local X/Y and compare heights
opts = Options(); opts.ComputeReferences = False; opts.DetailLevel = ViewDetailLevel.Fine
def heights(e):
    pts = []
    for g in e.get_Geometry(opts):
        gi = g if isinstance(g, GeometryInstance) else None
        geoms = gi.GetInstanceGeometry() if gi is not None else [g]
        for s in geoms:
            if isinstance(s, Mesh):
                for v in s.Vertices: pts.append((v.X, v.Y, v.Z))
            elif isinstance(s, Solid) and s.Volume > 1e-6:
                for edge in s.Edges:
                    c = edge.AsCurve()
                    for t in (0.0, 1.0):
                        p = c.Evaluate(t, True); pts.append((p.X, p.Y, p.Z))
    return pts
for fam in ("Bed01", "Bed04"):
    for e in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Furniture).WhereElementIsNotElementType():
        if isinstance(e, FamilyInstance) and e.Symbol.FamilyName == fam:
            pts = heights(e)
            if not pts: say(fam + ": no solids or meshes"); break
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]; zs = [p[2] for p in pts]
            mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
            hx = (max([p[2] for p in pts if p[0] < mx - 0.3] or [0]) - max([p[2] for p in pts if p[0] > mx + 0.3] or [0])) * FT
            hy = (max([p[2] for p in pts if p[1] < my - 0.3] or [0]) - max([p[2] for p in pts if p[1] > my + 0.3] or [0])) * FT
            say("%s: x-extent %.2f m, y-extent %.2f m ; height(west half) - height(east half) = %+.2f m ; height(south half) - height(north half) = %+.2f m" % (fam, (max(xs)-min(xs))*FT, (max(ys)-min(ys))*FT, hx, hy))
            break
__output__ = "\n".join(LOG)
