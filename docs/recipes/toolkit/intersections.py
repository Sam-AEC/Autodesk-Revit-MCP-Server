# Toolkit: scoped solid/solid (and mesh-aware) intersection check. Prototype of the proposed `revit_check_intersections` tool.
# Needs SCOPE = list of Elements (the elements to test against each other) and optional OTHERS = elements to test the scope against.
# Returns pair records: (id_a, id_b, kind, volume_m3, status). status: 'verified' (both solids) | 'candidate' (mesh / no solid).
# Broad phase: bounding-box overlap (with tolerance). Narrow phase: BooleanOperationsUtils.ExecuteBooleanOperation(Intersect).
import System
FT3_TO_M3 = 0.0283168466

def _solids(e):
    out = []; meshes = 0
    opt = Options(); opt.DetailLevel = ViewDetailLevel.Fine; opt.ComputeReferences = False
    ge = e.get_Geometry(opt)
    if ge is None: return out, 0
    def walk(g):
        n = 0
        for o in g:
            if isinstance(o, Solid):
                if o.Volume > 1e-9: out.append(o)
            elif isinstance(o, GeometryInstance):
                n += walk(o.GetInstanceGeometry())
            elif isinstance(o, Mesh):
                n += 1
        return n
    meshes = walk(ge)
    return out, meshes

def _bb(e):
    b = e.get_BoundingBox(None)
    return b

def _overlap(a, b, tol=0.001):
    return not (a.Max.X < b.Min.X - tol or b.Max.X < a.Min.X - tol or a.Max.Y < b.Min.Y - tol or b.Max.Y < a.Min.Y - tol or a.Max.Z < b.Min.Z - tol or b.Max.Z < a.Min.Z - tol)

def check_intersections(scope, others=None, min_volume_m3=0.0005):
    items = {}
    def info(e):
        k = e.Id.IntegerValue
        if k not in items:
            s, m = _solids(e); items[k] = (e, _bb(e), s, m)
        return items[k]
    pairs = []
    A = list(scope); B = list(others) if others is not None else None
    for i, ea in enumerate(A):
        ia = info(ea)
        if ia[1] is None: continue
        rng = B if B is not None else A[i + 1:]
        for eb in rng:
            if eb.Id == ea.Id: continue
            ib = info(eb)
            if ib[1] is None or not _overlap(ia[1], ib[1]): continue
            if not ia[2] or not ib[2]:
                pairs.append((ea.Id.IntegerValue, eb.Id.IntegerValue, "bbox", None, "candidate: no solid (mesh=%d/%d)" % (ia[3], ib[3])))
                continue
            vol = 0.0
            for sa in ia[2]:
                for sb in ib[2]:
                    try:
                        r = BooleanOperationsUtils.ExecuteBooleanOperation(sa, sb, BooleanOperationsType.Intersect)
                        if r is not None: vol += r.Volume
                    except Exception as ex:
                        pairs.append((ea.Id.IntegerValue, eb.Id.IntegerValue, "error", None, "failed: %s" % ex))
            if vol * FT3_TO_M3 >= min_volume_m3:
                pairs.append((ea.Id.IntegerValue, eb.Id.IntegerValue, "solid", round(vol * FT3_TO_M3, 4), "verified"))
    return pairs
