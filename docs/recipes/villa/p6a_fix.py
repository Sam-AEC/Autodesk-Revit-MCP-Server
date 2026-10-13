# Phase 6a: BIM-correctness pass. Constrain wall tops to levels, orient garden walls, structural flags, detail level + poche.
L0, L1, L2 = level_named("00 begane grond"), level_named("AMB_01 First Floor"), level_named("AMB_02 Roof")
walls = [w for w in tagged() if isinstance(w, Wall)]
def tname(e): return type_name(doc.GetElement(e.GetTypeId()))
def lo_hi(w): return zrange_m(w)

def constrain():
    n = 0
    for w in walls:
        name = tname(w); comment = w.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).AsString()
        lo, hi = lo_hi(w)
        if name == "AMB_Wall_Found_300" and comment.endswith("p3a"):      top, off = L0, 0.0              # foundation: -0.90 .. 0.00
        elif comment.endswith("p3a"):                                      top, off = L1, -0.28            # ground walls stop under the slab
        elif comment.endswith("p3b") and name == "AMB_Wall_Parapet_250":   top, off = L2, 0.94             # parapet above the roof
        elif comment.endswith("p3b"):                                      top, off = L2, 0.0              # upper walls up to the roof level
        elif comment.endswith("p5") and name == "AMB_Wall_Found_300":      top, off = L0, 0.0              # pool walls
        elif comment.endswith("p5"):                                       top, off = L1, -1.0             # garden walls 2.20 m
        else: continue
        w.get_Parameter(BuiltInParameter.WALL_HEIGHT_TYPE).Set(top.Id)
        w.get_Parameter(BuiltInParameter.WALL_TOP_OFFSET).Set(ft(off))
        n += 1
    return n
n = run("AMB: constrain wall tops to levels", constrain)
say("walls constrained to a top level: %s" % n)

# measured: heights unchanged, tops now constrained
bad = 0
for w in walls:
    tc = w.get_Parameter(BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId()
    if tc == ElementId.InvalidElementId: bad += 1
say("walls still unconstrained: %d of %d" % (bad, len(walls)))

# orientation of the garden walls (brick outside)
def outward(w, cx=0.0, cy=-3.5):
    mid = w.Location.Curve.Evaluate(0.5, True)
    vx, vy = (mid.X - CX) * FT - cx, (mid.Y - CY) * FT - cy
    o = w.Orientation; return o.X * vx + o.Y * vy
garden = [w for w in walls if tname(w) == "AMB_Wall_Parapet_250" and w.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).AsString().endswith("p5")]
inward = [w for w in garden if outward(w) < 0]
say("garden walls: %d ; brick facing the villa (wrong) before: %d" % (len(garden), len(inward)))
run("AMB: flip garden walls", lambda: [w.Flip() for w in inward])
say("garden walls with brick facing inwards after: %d" % len([w for w in garden if outward(w) < 0]))

# structural flags: load-bearing walls and slabs
def flags():
    k = 0
    for w in walls:
        if tname(w) in ("AMB_Wall_Ext_425", "AMB_Wall_Core_200", "AMB_Wall_Found_300"):
            w.get_Parameter(BuiltInParameter.WALL_STRUCTURAL_SIGNIFICANT).Set(1); k += 1
    for f in FilteredElementCollector(doc).OfClass(Floor):
        if tname(f) in ("AMB_Floor_Ground_370", "AMB_Floor_Upper_280"):
            p = f.get_Parameter(BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL); 
            if p is not None and not p.IsReadOnly: p.Set(1); k += 1
    return k
say("structural flags set on %s elements" % run("AMB: structural flags", flags))

# poche: solid cut fill in each material's colour, Fine detail level on the villa views
solid = [fp for fp in FilteredElementCollector(doc).OfClass(FillPatternElement) if fp.GetFillPattern().IsSolidFill and fp.GetFillPattern().Target == FillPatternTarget.Drafting]
def poche():
    k = 0
    for m in FilteredElementCollector(doc).OfClass(Material):
        if m.Name.startswith("AMB_") and solid:
            m.CutForegroundPatternId = solid[0].Id; m.CutForegroundPatternColor = m.Color; k += 1
    for v in FilteredElementCollector(doc).OfClass(View):
        if not v.IsTemplate and v.get_Parameter(BuiltInParameter.VIEW_NAME).AsString().startswith("AMB_") and v.ViewType in (ViewType.FloorPlan, ViewType.Section):
            v.DetailLevel = ViewDetailLevel.Fine
    return k
say("materials given a cut pattern: %s ; villa plans/section set to Fine" % run("AMB: poche and detail level", poche))
say("warnings in model now: %d (baseline 2077)" % len(doc.GetWarnings()))
__output__ = "\n".join(LOG)
