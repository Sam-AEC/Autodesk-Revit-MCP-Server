# Phase 3x: make every exterior-type wall face outwards (exterior layers outside). Measured, then flipped where needed.
EXT_NAMES = ("AMB_Wall_Ext_425", "AMB_Wall_Parapet_250")
GROUND_C = (0.0, 1.5)      # footprint centroid (villa-local metres), good enough to tell inside from outside for this plan
def outward_dot(w):
    lc = w.Location.Curve
    mid = lc.Evaluate(0.5, True)
    mx, my = (mid.X - CX) * FT, (mid.Y - CY) * FT
    vx, vy = mx - GROUND_C[0], my - GROUND_C[1]
    o = w.Orientation
    return o.X * vx + o.Y * vy

ext_walls = [w for w in tagged() if isinstance(w, Wall) and type_name(doc.GetElement(w.GetTypeId())) in EXT_NAMES]
bad = [w for w in ext_walls if outward_dot(w) < 0]
say("exterior-type walls: %d ; facing inwards before: %d" % (len(ext_walls), len(bad)))
def fix():
    for w in bad: w.Flip()
if bad: run("AMB: orient exterior walls", fix)
still = [w for w in ext_walls if outward_dot(w) < 0]
say("facing inwards after: %d" % len(still))
if still: say("   still inward: " + ", ".join([str(w.Id.Value) for w in still]))
__output__ = "\n".join(LOG)
