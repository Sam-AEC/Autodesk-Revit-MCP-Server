# BIM quality review: READ-ONLY IronPython for revit_execute_python (run after prelude.py).
# Reviews every element tagged AMB_VILLA:* plus AMB_ floors, stairs and lawn. Prints one line per check:
#   PASS|FAIL|INFO <check id> <measured evidence>
# It never opens a transaction and never changes the model.
VILLA = [e for e in tagged()]
for f in FilteredElementCollector(doc).OfClass(Floor):
    if type_name(doc.GetElement(f.GetTypeId())).startswith("AMB_") and f.Id not in [x.Id for x in VILLA]:
        VILLA.append(f)
walls = [e for e in VILLA if isinstance(e, Wall)]
floors = [e for e in VILLA if isinstance(e, Floor)]
roofs = [e for e in VILLA if e.Category is not None and e.Category.Id.IntegerValue == int(BuiltInCategory.OST_Roofs)]
inst = [e for e in VILLA if isinstance(e, FamilyInstance)]
rooms = [e for e in VILLA if e.Category is not None and e.Category.Id.IntegerValue == int(BuiltInCategory.OST_Rooms)]
stairs = [e for e in VILLA if e.Category is not None and e.Category.Id.IntegerValue == int(BuiltInCategory.OST_Stairs)]
def tn(e): return type_name(doc.GetElement(e.GetTypeId()))
def cat(e): return e.Category.Id.IntegerValue if e.Category is not None else 0
doors = [e for e in inst if cat(e) == int(BuiltInCategory.OST_Doors)]
windows = [e for e in inst if cat(e) == int(BuiltInCategory.OST_Windows)]
RESULTS = []
def check(status, cid, text):
    RESULTS.append(status); say("%-4s %-14s %s" % (status, cid, text))

check("INFO", "SCOPE", "reviewing %d elements: %d walls, %d floors, %d roofs, %d doors, %d windows, %d rooms, %d stairs" % (len(VILLA), len(walls), len(floors), len(roofs), len(doors), len(windows), len(rooms), len(stairs)))

# 1 ground level
ground = [f for f in floors if tn(f) == "AMB_Floor_Ground_370"]
tops = [zrange_m(f)[1] for f in ground]
lo = min([zrange_m(e)[0] for e in VILLA if zrange_m(e)[0] is not None] or [0])
ok = bool(tops) and abs(max(tops)) < 0.01 and lo > -3.0
check("PASS" if ok else "FAIL", "GROUND", "ground slab top %.2f m (must be 0.00 = level 00); lowest element %.2f m" % (max(tops) if tops else float("nan"), lo))

# 2 wall tops constrained
free = [w for w in walls if w.get_Parameter(BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId() == ElementId.InvalidElementId]
check("PASS" if not free else "FAIL", "WALL_TOPS", "%d of %d walls have an unconstrained top (heights must follow levels)" % (len(free), len(walls)))

# 3 exterior walls face outward: probe 0.6 m out along the wall's exterior normal; that point must NOT be inside a room
def probe_inside(w):
    c = w.Location.Curve; m = c.Evaluate(0.5, True); o = w.Orientation
    z = w.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)
    lvl = doc.GetElement(z.AsElementId()); zz = (lvl.Elevation if lvl is not None else m.Z) + 3.0
    p = XYZ(m.X + o.X * ft(0.6), m.Y + o.Y * ft(0.6), zz)
    try: return doc.GetRoomAtPoint(p) is not None
    except Exception: return False
ext = [w for w in walls if tn(w) == "AMB_Wall_Ext_425"]
inward = [w for w in ext if probe_inside(w)]
check("PASS" if not inward else "FAIL", "WALL_ORIENT", "%d of %d exterior walls have their exterior face toward a room %s" % (len(inward), len(ext), [w.Id.Value for w in inward][:6]))

# 4 joins
loose = []
for w in walls:
    n = 0
    for end in (0, 1):
        try: n += 1 if w.Location.get_ElementsAtJoin(end).Size > 0 else 0
        except Exception: pass
    if n < 2 and tn(w) in ("AMB_Wall_Ext_425", "AMB_Wall_Found_300"): loose.append(w)
check("PASS" if not loose else "FAIL", "WALL_JOINS", "%d exterior/foundation walls with an unjoined end %s" % (len(loose), [w.Id.Value for w in loose][:6]))

# 5 assemblies are real
def stack(t):
    cs = t.GetCompoundStructure()
    if cs is None: return None
    return [cs.GetLayerFunction(i) for i in range(cs.LayerCount)], cs.GetWidth() * 304.8
problems = []
for e in walls + floors + roofs:
    t = doc.GetElement(e.GetTypeId()); s = stack(t)
    n = type_name(t)
    if s is None: continue
    funcs, width = s
    need_ins = n in ("AMB_Wall_Ext_425", "AMB_Floor_Ground_370", "AMB_Roof_Flat_440")
    if need_ins and MaterialFunctionAssignment.Insulation not in funcs: problems.append("%s has no insulation layer" % n)
    if MaterialFunctionAssignment.Structure not in funcs: problems.append("%s has no structural layer" % n)
check("PASS" if not problems else "FAIL", "ASSEMBLIES", "%d problems %s" % (len(set(problems)), sorted(set(problems))[:4]))

# 6 openings: hosted, no warnings, plausible width for a hinged door
warn_by_id = {}
for w in doc.GetWarnings():
    for i in list(w.GetFailingElements()) + list(w.GetAdditionalElements()):
        warn_by_id.setdefault(i.Value, []).append(w.GetDescriptionText())
bad_open = []
for o in doors + windows:
    if o.Host is None: bad_open.append("%d no host" % o.Id.Value)
    if o.Id.Value in warn_by_id: bad_open.append("%d warning: %s" % (o.Id.Value, warn_by_id[o.Id.Value][0][:40]))
for d in doors:
    wd = d.Symbol.LookupParameter("Width")
    if wd is not None and wd.AsDouble() * 304.8 > 1300 and d.Symbol.FamilyName == "M_Single-Flush": bad_open.append("%d hinged door %.0f mm wide (swing arc)" % (d.Id.Value, wd.AsDouble() * 304.8))
check("PASS" if not bad_open else "FAIL", "OPENINGS", "%d doors + %d windows ; %d problems %s" % (len(doors), len(windows), len(bad_open), bad_open[:4]))

# 7 rooms enclosed, and every room reachable through doors
bad_rooms = [r for r in rooms if r.Area * 0.0929 < 1.0 or r.Location is None]
check("PASS" if not bad_rooms else "FAIL", "ROOMS", "%d rooms, total %.1f m2 ; %d not enclosed/placed" % (len(rooms), sum([r.Area for r in rooms]) * 0.0929, len(bad_rooms)))
adj = {}
for d in doors:
    try:
        ph = doc.GetElement(d.CreatedPhaseId)
        a, b = d.get_FromRoom(ph), d.get_ToRoom(ph)
    except Exception:
        a = b = None
    if a is not None and b is not None:
        adj.setdefault(a.Id.Value, set()).add(b.Id.Value); adj.setdefault(b.Id.Value, set()).add(a.Id.Value)
# the stair joins the entrance hall to the gallery
hall_ids = [r.Id.Value for r in rooms if "Hall" in (r.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() or "")]
gal_ids = [r.Id.Value for r in rooms if "Gallery" in (r.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() or "")]
if stairs and hall_ids and gal_ids:
    adj.setdefault(hall_ids[0], set()).add(gal_ids[0]); adj.setdefault(gal_ids[0], set()).add(hall_ids[0])
entrance = [r for r in rooms if "Hall" in (r.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() or "")]
if entrance and rooms:
    seen = set([entrance[0].Id.Value]); todo = [entrance[0].Id.Value]
    while todo:
        c = todo.pop()
        for n in adj.get(c, []):
            if n not in seen: seen.add(n); todo.append(n)
    unreachable = [r.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() for r in rooms if r.Id.Value not in seen]
    check("PASS" if not unreachable else "FAIL", "CIRCULATION", "%d of %d rooms reachable from the entrance through doors; unreachable: %s" % (len(rooms) - len(unreachable), len(rooms), unreachable[:8]))

# 8 stairs
for s in stairs:
    nr = s.get_Parameter(BuiltInParameter.STAIRS_ACTUAL_NUM_RISERS); rh = s.get_Parameter(BuiltInParameter.STAIRS_ACTUAL_RISER_HEIGHT)
    if nr is not None and rh is not None:
        total = nr.AsInteger() * rh.AsDouble() * 304.8
        check("PASS" if abs(total - 3200) < 5 else "FAIL", "STAIR", "%d risers x %.1f mm = %.0f mm (storey height 3200 mm)" % (nr.AsInteger(), rh.AsDouble() * 304.8, total))
if not stairs: check("FAIL", "STAIR", "no stair between the storeys")

# 9 warnings touching the villa
mine = set([e.Id.Value for e in VILLA])
touch = [d for i, ds in warn_by_id.items() if i in mine for d in ds]
check("PASS" if not touch else "FAIL", "WARNINGS", "%d warnings touch villa elements %s ; model total %d" % (len(touch), sorted(set([t[:38] for t in touch]))[:3], len(doc.GetWarnings())))

# 10 structure
flagged = [w for w in walls if w.get_Parameter(BuiltInParameter.WALL_STRUCTURAL_SIGNIFICANT).AsInteger() == 1]
members = [e for e in VILLA if cat(e) in (int(BuiltInCategory.OST_StructuralColumns), int(BuiltInCategory.OST_StructuralFraming))]
check("PASS" if flagged else "FAIL", "STRUCT_FLAGS", "%d load-bearing walls flagged structural" % len(flagged))
check("PASS" if members else "FAIL", "STRUCT_MEMBERS", "%d columns/beams modelled (a cantilever and wide openings need them)" % len(members))

# 11 content: furnished rooms
furn_cats = (int(BuiltInCategory.OST_Furniture), int(BuiltInCategory.OST_PlumbingFixtures), int(BuiltInCategory.OST_Casework), int(BuiltInCategory.OST_Planting), int(BuiltInCategory.OST_ElectricalFixtures), int(BuiltInCategory.OST_LightingFixtures))
furn = [e for e in VILLA if cat(e) in furn_cats]
inroom = {}
for f in furn:
    r = None
    try:
        if isinstance(f, FamilyInstance): r = f.get_Room(doc.GetElement(f.CreatedPhaseId))
    except Exception:
        r = None
    if r is None:
        try:
            lp = f.Location.Point; lvl = doc.GetElement(f.LevelId)
            r = doc.GetRoomAtPoint(XYZ(lp.X, lp.Y, (lvl.Elevation if lvl is not None else lp.Z) + 1.0))
        except Exception:
            r = None
    if r is not None: inroom[r.Id.Value] = inroom.get(r.Id.Value, 0) + 1
unfurnished = [r.get_Parameter(BuiltInParameter.ROOM_NAME).AsString() for r in rooms if r.Id.Value not in inroom]
check("PASS" if rooms and len(unfurnished) <= 1 else "FAIL", "FURNISHING", "%d furniture/fixture/planting elements ; %d of %d rooms empty %s" % (len(furn), len(unfurnished), len(rooms), unfurnished[:6]))

# 12 documentation
vviews = [v for v in FilteredElementCollector(doc).OfClass(View) if not v.IsTemplate and (v.get_Parameter(BuiltInParameter.VIEW_NAME).AsString() or "").startswith("AMB_")]
vids = set([v.Id.Value for v in vviews])
plans = [v for v in vviews if v.ViewType == ViewType.FloorPlan]
rtags = [t for t in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_RoomTags).WhereElementIsNotElementType() if t.OwnerViewId.Value in vids]
dims = [d for d in FilteredElementCollector(doc).OfClass(Dimension) if d.OwnerViewId.Value in vids]
sheets_with = 0
for s in FilteredElementCollector(doc).OfClass(ViewSheet):
    for vid in s.GetAllPlacedViews():
        if vid.Value in vids: sheets_with += 1; break
check("PASS" if rtags else "FAIL", "ROOM_TAGS", "%d room tags in villa views (rooms: %d)" % (len(rtags), len(rooms)))
check("PASS" if dims else "FAIL", "DIMENSIONS", "%d dimensions in villa views" % len(dims))
check("PASS" if sheets_with else "FAIL", "SHEETS", "%d sheets carry villa views" % sheets_with)
sched = [s for s in FilteredElementCollector(doc).OfClass(ViewSchedule) if (s.Name or "").startswith("AMB_")]
check("PASS" if len(sched) >= 3 else "FAIL", "SCHEDULES", "%d AMB_ schedules (expect rooms, doors, windows)" % len(sched))
fine = [v for v in plans if v.DetailLevel == ViewDetailLevel.Fine]
check("PASS" if plans and len(fine) == len(plans) else "FAIL", "DETAIL", "%d of %d villa plans at Fine detail" % (len(fine), len(plans)))

# 13 section actually shows the building
secs = [v for v in vviews if v.ViewType == ViewType.Section]
for sv in secs:
    inview = FilteredElementCollector(doc, sv.Id).WhereElementIsNotElementType().ToElements()
    n_mine = len([e for e in inview if e.Id.Value in mine])
    has_stair = len([e for e in inview if e.Id.Value in [s.Id.Value for s in stairs]]) > 0
    check("PASS" if n_mine >= 15 and has_stair else "FAIL", "SECTION", "'%s' shows %d villa elements, stair visible: %s" % (sv.get_Parameter(BuiltInParameter.VIEW_NAME).AsString(), n_mine, has_stair))
if not secs: check("FAIL", "SECTION", "no section view")

# 14 fixtures against walls, the right way round (measured from geometry, because FacingOrientation means different
#    things in different families: for the WC it points to the BACK, for beds it points sideways)
_opts = Options(); _opts.ComputeReferences = False; _opts.DetailLevel = ViewDetailLevel.Fine
def _verts(e):
    out = []
    for g in e.get_Geometry(_opts):
        geoms = g.GetInstanceGeometry() if isinstance(g, GeometryInstance) else [g]
        for s_ in geoms:
            if isinstance(s_, Mesh):
                for v_ in s_.Vertices: out.append((v_.X, v_.Y, v_.Z))
            elif isinstance(s_, Solid) and s_.Volume > 1e-9:
                for ed in s_.Edges:
                    c_ = ed.AsCurve()
                    for t_ in (0.0, 1.0):
                        p_ = c_.Evaluate(t_, True); out.append((p_.X, p_.Y, p_.Z))
    return out
def _back(e, kind):
    """(unit back direction (dx, dy), back-edge midpoint (x, y) in feet) or None"""
    v = _verts(e)
    if not v: return None
    xs = [p[0] for p in v]; ys = [p[1] for p in v]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    ax = (x1 - x0) >= (y1 - y0)
    lo = x0 if ax else y0; hi = x1 if ax else y1; span = hi - lo
    low = [p for p in v if (p[0] if ax else p[1]) < lo + 0.15 * span]; high = [p for p in v if (p[0] if ax else p[1]) > hi - 0.15 * span]
    if kind == "bed":
        a = max([p[2] for p in low] or [0]); b = max([p[2] for p in high] or [0]); head_low = a > b
    else:
        wl = (max([(p[1] if ax else p[0]) for p in low] or [0]) - min([(p[1] if ax else p[0]) for p in low] or [0]))
        wh = (max([(p[1] if ax else p[0]) for p in high] or [0]) - min([(p[1] if ax else p[0]) for p in high] or [0]))
        head_low = wl > wh
    if ax: d = (-1.0, 0.0) if head_low else (1.0, 0.0); mid = ((x0 if head_low else x1), (y0 + y1) / 2)
    else:  d = (0.0, -1.0) if head_low else (0.0, 1.0); mid = ((x0 + x1) / 2, (y0 if head_low else y1))
    return d, mid
def _wall_behind(e, d, mid):
    best = None
    for w_ in walls:
        lo_, hi_ = zrange_m(w_)
        lv = doc.GetElement(e.LevelId); z0 = (lv.Elevation if lv is not None else 0) * FT
        if not (lo_ <= z0 + 0.5 and hi_ >= z0 + 0.5): continue
        c_ = w_.Location.Curve; pr = c_.Project(XYZ(mid[0], mid[1], c_.GetEndPoint(0).Z))
        if pr is None: continue
        vx, vy = pr.XYZPoint.X - mid[0], pr.XYZPoint.Y - mid[1]; dist = pr.Distance
        if dist < 1e-6: gap = -w_.Width / 2; behind = True
        else: behind = (vx * d[0] + vy * d[1]) / dist > 0.7; gap = dist - w_.Width / 2
        if behind and (best is None or gap < best[0]): best = (gap, w_)
    return best
fix_bad = []; checked = 0; wrong_level = []
for e in furn:
    if not isinstance(e, FamilyInstance): continue
    fam = e.Symbol.FamilyName
    kind = "bed" if (fam.startswith("Bed") or fam == "AMB_Bed_King") else ("wc" if fam == "74_HB_Wandcloset" else None)
    lv = doc.GetElement(e.LevelId)
    if lv is not None:
        lo_, hi_ = zrange_m(e)
        if lo_ is not None and abs(lo_ - lv.Elevation * FT) > 0.35: wrong_level.append("%s id %d z %.2f vs level %.2f" % (fam[:18], e.Id.Value, lo_, lv.Elevation * FT))
    if kind is None: continue
    r_ = _back(e, kind)
    if r_ is None: continue
    checked += 1
    nb = _wall_behind(e, r_[0], r_[1])
    if nb is None: fix_bad.append("%s id %d: no wall behind its %s" % (fam[:16], e.Id.Value, "head" if kind == "bed" else "back"))
    elif nb[0] * FT > 0.08 or nb[0] * FT < -0.05: fix_bad.append("%s id %d: %s is %.2f m from the wall behind it" % (fam[:16], e.Id.Value, "head" if kind == "bed" else "back", nb[0] * FT))
check("PASS" if not wrong_level else "FAIL", "FIXTURE_LEVEL", "%d furniture/fixtures not standing on their level (z offset applied twice?) %s" % (len(wrong_level), wrong_level[:3]))
check("PASS" if not fix_bad else "FAIL", "FIXTURE_BACK", "%d of %d beds/WCs checked: %d with the head/back not against a wall behind them %s" % (checked, checked, len(fix_bad), fix_bad[:4]))

nf = len([r for r in RESULTS if r == "FAIL"]); npass = len([r for r in RESULTS if r == "PASS"])
say("RESULT %d FAIL / %d PASS" % (nf, npass))
__output__ = "\n".join(LOG)
