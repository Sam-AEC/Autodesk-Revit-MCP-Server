# Toolkit: measured audit of openings and roofs against their data. A mandatory stage of the villa workflow: run after the
# openings and roofs phases; every FAIL must be fixed (or explicitly waived in DATA["waive"]) before the model is called done.
# Needs: DATA = dict(doors=[...], windows=[...], roofs=[{name, top_m|ridge_m:[lo,hi], poly:[(x,y)...], open_edges_near:[(x0,y0,x1,y1)]}]).
# Output lines start with PASS / FAIL / INFO. It reads the model only.
import math
SC_MM = SC * 1000.0
fails = []
def check(ok, cid, text):
    line = "%s %-14s %s" % ("PASS" if ok else "FAIL", cid, text)
    say(line)
    if not ok: fails.append(cid)

def by_mark(phase_prefix, cls):
    out = {}
    for e in FilteredElementCollector(doc).OfClass(cls):
        c = cmt(e)
        if c and c.startswith(TAG + phase_prefix):
            m = e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).AsString()
            if m: out[m] = e
    return out

def solids_world(e):
    opt = Options(); opt.DetailLevel = ViewDetailLevel.Fine
    out = []
    ge = e.get_Geometry(opt)
    for g in ge:
        if isinstance(g, GeometryInstance):
            for h in g.GetInstanceGeometry():
                if isinstance(h, Solid) and h.Volume > 1e-7: out.append(h)
        elif isinstance(g, Solid) and g.Volume > 1e-7: out.append(g)
    return out

def extents(e, ax):
    """z range and extent along the unit vector ax (plan) over all solids of the instance, in metres."""
    zs = []; ds = []
    for s in solids_world(e):
        for f in s.Faces:
            for v in f.Triangulate().Vertices:
                zs.append(v.Z * FT); ds.append((v.X * ax.X + v.Y * ax.Y) * FT)
    return (min(zs), max(zs), min(ds), max(ds)) if zs else None

def area_factor(shape):
    return {None: 1.0, "rect": 1.0, "segmental": 0.93, "round": 0.88, "horseshoe": 0.85}.get(shape, 0.85)

def audit_openings():
    inst = by_mark("p5_openings", FamilyInstance)
    walls = by_mark("p3_walls", Wall)
    waive = set(DATA.get("waive", []))
    for (o, is_door) in [(d, True) for d in DATA["doors"]] + [(w, False) for w in DATA["windows"]]:
        oid = o["id"]
        if oid in waive: continue
        fi = inst.get(oid)
        if fi is None:
            check(False, "OPEN_MISSING", "%s was not placed" % oid); continue
        host = fi.Host
        hm = host.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).AsString() if host is not None else None
        check(hm == o["wall"], "OPEN_HOST", "%s hosted in %s (data says %s)" % (oid, hm, o["wall"]))
        pt = P(o["x"], o["y"], 0); loc = fi.Location.Point
        dist = math.hypot(pt.X - loc.X, pt.Y - loc.Y) * FT
        check(dist < 0.08, "OPEN_POS", "%s is %.3f m from its DWG position" % (oid, dist))
        # size and sill from the real geometry
        crv = host.Location.Curve
        d = (crv.GetEndPoint(1) - crv.GetEndPoint(0)).Normalize()
        ex = extents(fi, d)
        w_mm = o.get("w_mm") or int(round(o["width"] * SC_MM / 50.0) * 50)
        h_mm = o.get("h_mm") or (2100 if is_door else 1250)
        lvl = doc.GetElement(host.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT).AsElementId())
        sill = 0.0 if is_door else o.get("sill_mm", 1050) / 1000.0
        if ex is None:
            check(False, "OPEN_GEOM", "%s has no geometry" % oid); continue
        z0 = lvl.Elevation * FT + sill; z1 = z0 + h_mm / 1000.0
        # frames add ~0.12 m to the width; a leaf-only door shows its leaf width
        wid = ex[3] - ex[2]
        check(abs(ex[0] - z0) <= 0.06 and (ex[1] <= z1 + (0.14 if is_door else 0.06)), "OPEN_Z", "%s z %.2f..%.2f expected %.2f..%.2f" % (oid, ex[0], ex[1], z0, z1))
        check(wid <= w_mm / 1000.0 + 0.2 and wid >= 0.6 * w_mm / 1000.0, "OPEN_WIDTH", "%s width %.2f m (spec %.2f)" % (oid, wid, w_mm / 1000.0))
    # per wall: cut volume must match the opening areas
    per = {}
    for (o, is_door) in [(d, True) for d in DATA["doors"]] + [(w, False) for w in DATA["windows"]]:
        if o["id"] in waive: continue
        per.setdefault(o["wall"], []).append((o, is_door))
    for wm, items in per.items():
        w = walls.get(wm)
        if w is None: continue
        exp = 0.0
        for (o, is_door) in items:
            w_mm = o.get("w_mm") or int(round(o["width"] * SC_MM / 50.0) * 50); h_mm = o.get("h_mm") or (2100 if is_door else 1250)
            exp += w_mm / 1000.0 * h_mm / 1000.0 * area_factor(o.get("shape")) * w.Width * FT
        have = DATA.get("_vol0", {}).get(wm)
        # volume of the wall now vs the volume of the same wall without openings: computed from length x height x width
        L = w.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH).AsDouble() * FT
        bb = w.get_BoundingBox(None)
        H = (bb.Max.Z - bb.Min.Z) * FT
        vol_now = w.get_Parameter(BuiltInParameter.HOST_VOLUME_COMPUTED).AsDouble() * 0.0283168
        full = L * H * w.Width * FT
        cut = full - vol_now
        check(cut >= 0.6 * exp, "OPEN_CUT", "wall %s: %d openings cut %.2f m3 of ~%.2f m3 expected (full prism %.2f, now %.2f)" % (wm, len(items), cut, exp, full, vol_now))

def audit_roofs():
    roofs = by_mark("p7_roofs", RoofBase)
    for r in DATA.get("roofs", []):
        rf = roofs.get(r["name"])
        if rf is None:
            check(False, "ROOF_MISSING", r["name"]); continue
        bb = rf.get_BoundingBox(None)
        top = bb.Max.Z * FT; bot = bb.Min.Z * FT
        lo, hi = r["top_m"]
        check(lo <= top <= hi, "ROOF_TOP", "%s top %.2f m (allowed %.2f..%.2f)" % (r["name"], top, lo, hi))
        # edge parapets for flat roofs
        if r.get("poly") and r.get("need_parapet"):
            walls = [w for w in FilteredElementCollector(doc).OfClass(Wall) if (cmt(w) or "").startswith(TAG + "p3_walls")]
            n = len(r["poly"]); missing = []
            for i in range(n):
                a, b = r["poly"][i], r["poly"][(i + 1) % n]
                mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                if any(x0 <= mx <= x1 and y0 <= my <= y1 for (x0, y0, x1, y1) in r.get("open_edges_near", [])): continue
                mid = P(mx, my, top)
                ok = False
                for w in walls:
                    wb = w.get_BoundingBox(None)
                    if wb.Max.Z * FT < top + 0.6: continue          # a parapet must stand well above the roof surface
                    c = w.Location.Curve
                    q = c.Project(XYZ(mid.X, mid.Y, c.GetEndPoint(0).Z))
                    if q is not None and q.Distance * FT < 0.35: ok = True; break
                if not ok: missing.append("edge %d (%.0f,%.0f)-(%.0f,%.0f)" % (i, a[0], a[1], b[0], b[1]))
            check(not missing, "ROOF_PARAPET", "%s: %d edge(s) without a parapet %s" % (r["name"], len(missing), missing[:6]))
    check(True, "ROOF_DONE", "roof checks finished")

audit_openings()
audit_roofs()
say("AUDIT RESULT: %d FAIL" % len(fails))
__output__ = chr(10).join(LOG)
