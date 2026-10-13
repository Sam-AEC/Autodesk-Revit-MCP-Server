# the hall/garage door must swing into the garage, not across the stair
L0 = level_named("00 begane grond")
doors = [e for e in tagged("p3c") if isinstance(e, FamilyInstance) and e.Category.Id.IntegerValue == int(BuiltInCategory.OST_Doors)]
def near(e, x, y):
    p = e.Location.Point; return abs((p.X - CX) * FT - x) < 0.3 and abs((p.Y - CY) * FT - y) < 0.3
tgt = [d for d in doors if near(d, 3.0, -2.0)]
say("hall/garage door found: %d ; facing flipped before: %s" % (len(tgt), [d.FacingFlipped for d in tgt]))
run("AMB: flip hall/garage door", lambda: [d.flipFacing() for d in tgt])
say("after: %s" % [d.FacingFlipped for d in tgt])
__output__ = "\n".join(LOG)
