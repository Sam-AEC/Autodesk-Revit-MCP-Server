# Phase 3d: rooms (named, numbered, area-checked) and ceilings built from each room's real boundary.
PH = "p3d"
say("purged %d earlier p3d elements" % purge(PH))
L0, L1 = level_named("00 begane grond"), level_named("AMB_01 First Floor")
ROOMS = [   # level, number, name, x, y, ceiling?
    (L0, "G.01", "Lounge", -6, -1, True), (L0, "G.02", "Kitchen & Dining", -1, -1, True), (L0, "G.03", "Entrance Hall", 2, -2, False),
    (L0, "G.04", "Study", -7, 5.5, True), (L0, "G.05", "Guest Suite", -3, 5.5, True), (L0, "G.06", "Double Garage", 6.5, -2, True),
    (L1, "1.01", "Bedroom 2", -6.75, -1.75, True), (L1, "1.02", "Bedroom 3", -2.25, -1.75, True), (L1, "1.03", "Gallery & Corridor", 1.75, -1, True),
    (L1, "1.04", "Master Bedroom", 7, -2, True), (L1, "1.05", "Dressing Room", 5, 1.75, True), (L1, "1.06", "Master Ensuite", 8.25, 1.75, True),
    (L1, "1.07", "Bedroom 4", -7, 5.5, True), (L1, "1.08", "Family Bathroom", -3, 5.5, True)]
made = []
def build_rooms():
    for (lvl, num, name, x, y, ceil) in ROOMS:
        r = doc.Create.NewRoom(lvl, uv(x, y))
        r.get_Parameter(BuiltInParameter.ROOM_NUMBER).Set(num); r.get_Parameter(BuiltInParameter.ROOM_NAME).Set(name); tag(r, PH)
        made.append((r, ceil))
run("AMB: rooms", build_rooms)
okc = 0
for (r, ceil) in made:
    area = r.Area * 0.09290304
    good = r.Location is not None and area > 1.0
    okc += 1 if good else 0
    say("room %-5s %-20s area %6.2f m2 %s" % (r.get_Parameter(BuiltInParameter.ROOM_NUMBER).AsString(), r.get_Parameter(BuiltInParameter.ROOM_NAME).AsString(), area, "OK" if good else "NOT ENCLOSED/NOT PLACED"))
say("rooms OK: %d of %d ; total area %.1f m2" % (okc, len(made), sum([r.Area for (r, c) in made]) * 0.09290304))

ctype = find_type(CeilingType, "AMB_Ceiling_Gypsum_15")
def build_ceilings():
    n = 0
    for (r, ceil) in made:
        if not ceil or r.Area <= 0: continue
        segs = r.GetBoundarySegments(SpatialElementBoundaryOptions())
        if segs is None or segs.Count == 0: continue
        prof = List[CurveLoop]()
        cl = CurveLoop()
        for s in segs[0]: cl.Append(s.GetCurve())
        prof.Add(cl)
        c = Ceiling.Create(doc, prof, ctype.Id, r.LevelId)
        p = c.get_Parameter(BuiltInParameter.CEILING_HEIGHTABOVELEVEL_PARAM)
        if p is not None and not p.IsReadOnly: p.Set(ft(2.7))
        tag(c, PH); n += 1
    return n
n = run("AMB: ceilings", build_ceilings)
say("ceilings created: %s" % n)
__output__ = "\n".join(LOG)
