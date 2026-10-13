# Villa 2 MEP routing helpers. Native pipes / ducts joined to equipment connectors, with elbow, union and takeoff fittings.
# Nothing here draws loose lines: every segment is created from a connector or joined to the previous one by a fitting.
#   find(mark)                          placed family instance by Mark
#   pick(mark, sys, dia=(lo,hi), sort)  first free connector of that instance and system class
#   route(kind, c1, c2, ...)            polyline c1 -> c2 : stub, vertical, horizontal (x then y) via points, vertical, stub
#   branch(kind, c, trunk, ...)         pipe/duct from connector c to a point on a straight trunk piece + takeoff fitting
#   riser(kind, trunk, x, y, z_to, ...) vertical pipe from a trunk to another elevation (open top end returned as a connector)
#   report()                            counts and open (unconnected) ends of everything created by these helpers
# via points are (x, y) or (x, y, z) in model feet (z absolute); a z in a via point makes a vertical move there.
import math
from Autodesk.Revit.DB.Plumbing import Pipe, PipeType, PipingSystemType
from Autodesk.Revit.DB.Mechanical import Duct, DuctType, MechanicalSystemType
from Autodesk.Revit.DB import Domain

MIN_SEG = 0.03            # m, shorter legs are dropped
PHASE = "m3_route"

def find(mark):
    for e in FilteredElementCollector(doc).OfClass(FamilyInstance):
        c = cmt(e)
        if c and c.startswith(TAG) and e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).AsString() == mark: return e
    raise Exception("no instance with mark " + mark)

def _sysname(c):
    if c.Domain == Domain.DomainPiping: return str(c.PipeSystemType)
    if c.Domain == Domain.DomainHvac: return str(c.DuctSystemType)
    return "Power"

def conns(fi): return [c for c in fi.MEPModel.ConnectorManager.Connectors]

def pick(mark, sysname, dia=None, sort=None, free=True):
    fi = find(mark)
    cs = [c for c in conns(fi) if _sysname(c) == sysname and (not free or not c.IsConnected)]
    if dia is not None: cs = [c for c in cs if dia[0] <= (c.Radius * 2 * 304.8) <= dia[1]]
    if sort:
        k = {"x": lambda c: c.Origin.X, "y": lambda c: c.Origin.Y, "z": lambda c: c.Origin.Z}[sort]
        cs.sort(key=k)
    if not cs: raise Exception("no free %s connector (dia %s) on %s" % (sysname, dia, mark))
    return cs[0]

def _normal(c): return c.CoordinateSystem.BasisZ

def _clean(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if out[-1].DistanceTo(p) > MIN_SEG / FT: out.append(p)
    res = [out[0]]
    for i in range(1, len(out) - 1):
        a, b, c = res[-1], out[i], out[i + 1]
        u = (b - a).Normalize(); v = (c - b).Normalize()
        if u.CrossProduct(v).GetLength() > 1e-6: res.append(b)
    res.append(out[-1])
    return res

def way(c1, c2, zr_abs, stub_m=0.2, via=None):
    o1, o2 = c1.Origin, c2.Origin
    s1 = o1 + _normal(c1) * (stub_m / FT); s2 = o2 + _normal(c2) * (stub_m / FT)
    pts = [o1, s1, XYZ(s1.X, s1.Y, zr_abs)]
    for v in (via or []):
        cur = pts[-1]
        pts.append(XYZ(v[0], cur.Y, cur.Z)); pts.append(XYZ(v[0], v[1], cur.Z))
        if len(v) > 2: pts.append(XYZ(v[0], v[1], v[2]))
    cur = pts[-1]
    pts.append(XYZ(s2.X, cur.Y, cur.Z)); pts.append(XYZ(s2.X, s2.Y, cur.Z))
    pts.append(XYZ(s2.X, s2.Y, s2.Z)); pts.append(s2); pts.append(o2)
    return _clean(pts)

def _create(kind, sysid, typeid, lvlid, a, b):
    isc = hasattr(a, "Origin")
    if kind == "pipe":
        return Pipe.Create(doc, typeid, lvlid, a, b) if isc else Pipe.Create(doc, sysid, typeid, lvlid, a, b)
    return Duct.Create(doc, typeid, lvlid, a, b) if isc else Duct.Create(doc, sysid, typeid, lvlid, a, b)

def _sysid(kind, curve):
    bip = BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM if kind == "pipe" else BuiltInParameter.RBS_DUCT_SYSTEM_TYPE_PARAM
    return curve.get_Parameter(bip).AsElementId()

def _near(curve, p):
    best = None
    for c in curve.ConnectorManager.Connectors:
        d = c.Origin.DistanceTo(p)
        if best is None or d < best[0]: best = (d, c)
    return best[1]

def _set_size(kind, curve, dia_mm):
    bip = BuiltInParameter.RBS_PIPE_DIAMETER_PARAM if kind == "pipe" else BuiltInParameter.RBS_CURVE_DIAMETER_PARAM
    try: curve.get_Parameter(bip).Set(dia_mm / 1000.0 / FT)
    except Exception as e: say("size %s: %s" % (dia_mm, e))

def _mark(e, label):
    try:
        tag(e, PHASE); e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).Set(label)
    except: pass

def _join(kind, a, b, p, label):
    ca, cb = _near(a, p), _near(b, p)
    if ca.IsConnected or cb.IsConnected: return None
    da = (a.Location.Curve.GetEndPoint(1) - a.Location.Curve.GetEndPoint(0)).Normalize()
    db = (b.Location.Curve.GetEndPoint(1) - b.Location.Curve.GetEndPoint(0)).Normalize()
    f = doc.Create.NewUnionFitting(ca, cb) if da.CrossProduct(db).GetLength() < 1e-6 else doc.Create.NewElbowFitting(ca, cb)
    _mark(f, label + "_fit")
    return f

def _chain(kind, pts, first, last, typeid, lvlid, dia_mm, label):
    """pts = cleaned waypoints; first/last = Connector or None (then a free end at pts[0] / pts[-1])."""
    curves = []
    n = len(pts)
    for i in range(n - 1):
        a = first if (i == 0 and first is not None) else pts[i]
        b = pts[i + 1]
        if i == n - 2 and last is not None:
            cu = _create(kind, None, typeid, lvlid, last, pts[i])          # created from the far connector, reversed
        elif i == 0 and first is not None:
            cu = _create(kind, None, typeid, lvlid, first, b)
        else:
            sid = _sysid(kind, curves[0]) if curves else None
            cu = _create(kind, sid, typeid, lvlid, a, b)
        _set_size(kind, cu, dia_mm); _mark(cu, "%s_%d" % (label, i)); curves.append(cu)
    for i in range(len(curves) - 1):
        _join(kind, curves[i], curves[i + 1], pts[i + 1], label)
    return curves

def route(kind, c1, c2, typeid, lvlid, zr_abs, dia_mm, via=None, stub_m=0.2, label="r"):
    pts = way(c1, c2, zr_abs, stub_m, via)
    if len(pts) == 2:
        cu = _create(kind, None, typeid, lvlid, c1, c2); _set_size(kind, cu, dia_mm); _mark(cu, label); return [cu]
    return _chain(kind, pts, c1, c2, typeid, lvlid, dia_mm, label)

def _trunk_attach(trunk_curves, xy, z):
    best = None
    for cu in trunk_curves:
        a, b = cu.Location.Curve.GetEndPoint(0), cu.Location.Curve.GetEndPoint(1)
        if abs(a.Z - b.Z) > 1e-4 or abs(a.Z - z) > 0.05 / FT * 4: continue
        d = b - a; L = d.GetLength()
        if L < 0.6 / FT: continue
        u = d.Normalize()
        t = ((xy[0] - a.X) * u.X + (xy[1] - a.Y) * u.Y)
        if t < 0.15 / FT or t > L - 0.15 / FT: continue
        px, py = a.X + u.X * t, a.Y + u.Y * t
        dist = math.hypot(xy[0] - px, xy[1] - py)
        if best is None or dist < best[0]: best = (dist, cu, XYZ(px, py, a.Z), u)
    return best

def branch(kind, c, trunk_curves, typeid, lvlid, dia_mm, stub_m=0.2, label="b"):
    """Branch from connector c to the nearest straight horizontal piece of the trunk, ending with a takeoff fitting."""
    o = c.Origin; s = o + _normal(c) * (stub_m / FT)
    z = trunk_curves[0].Location.Curve.GetEndPoint(0).Z
    best = _trunk_attach(trunk_curves, (s.X, s.Y), z) or _trunk_attach(trunk_curves, (o.X, o.Y), z)
    if best is None: raise Exception("no trunk piece to attach %s" % label)
    dist, cu, p, u = best
    # leg 1: stub, leg 2: vertical to trunk z, leg 3: horizontal perpendicular to the trunk to the attach point
    pts = _clean([o, s, XYZ(s.X, s.Y, z), p])
    curves = _chain(kind, pts, c, None, typeid, lvlid, dia_mm, label)
    end = _near(curves[-1], p)
    doc.Create.NewTakeoffFitting(end, cu)
    return curves

def riser(kind, trunk_curves, x, y, z_from, z_to, typeid, lvlid, dia_mm, label="riser"):
    """Vertical pipe at (x, y) from a trunk piece up/down to z_to; returns (curve, top_connector)."""
    best = _trunk_attach(trunk_curves, (x, y), z_from)
    if best is None: raise Exception("no trunk piece for riser " + label)
    dist, cu, p, u = best
    cur = _create(kind, _sysid(kind, cu), typeid, lvlid, XYZ(p.X, p.Y, z_from), XYZ(p.X, p.Y, z_to))
    _set_size(kind, cur, dia_mm); _mark(cur, label)
    cb = _near(cur, XYZ(p.X, p.Y, z_from))
    doc.Create.NewTakeoffFitting(cb, cu)
    return cur, _near(cur, XYZ(p.X, p.Y, z_to))

def report():
    out = {}
    for cls, nm in ((Pipe, "pipe"), (Duct, "duct")):
        n = 0; open_ends = []
        for e in FilteredElementCollector(doc).OfClass(cls):
            c = cmt(e)
            if not (c and c.startswith(TAG)): continue
            n += 1
            for cn in e.ConnectorManager.Connectors:
                if not cn.IsConnected: open_ends.append((e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).AsString(), round(cn.Origin.X, 1), round(cn.Origin.Y, 1), round(cn.Origin.Z, 1)))
        out[nm] = (n, open_ends)
    fit = len([e for e in FilteredElementCollector(doc).OfClass(FamilyInstance) if (cmt(e) or "").startswith(TAG + PHASE)])
    return out, fit
