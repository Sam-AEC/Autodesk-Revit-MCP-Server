# Build a king-size bed family (1.80 x 2.00 m mattress) in a family document from Autodesk's Metric Furniture template, load it.
TEMPLATE = r"C:\ProgramData\Autodesk\RVT 2024\Family Templates\English\Metric Furniture.rft"
OUT = r"C:\Users\samo3\AppData\Local\Temp\AMB_Bed_King.rfa"
have = [s for s in FilteredElementCollector(doc).OfClass(FamilySymbol) if s.FamilyName == "AMB_Bed_King"]
if have:
    say("AMB_Bed_King already in the model")
else:
    fd = app.NewFamilyDocument(TEMPLATE)
    try:
        t = Transaction(fd, "AMB king bed"); t.Start()
        def box(x0, y0, x1, y1, z0, z1):
            P = [XYZ(ft(x0), ft(y0), ft(z0)), XYZ(ft(x1), ft(y0), ft(z0)), XYZ(ft(x1), ft(y1), ft(z0)), XYZ(ft(x0), ft(y1), ft(z0))]
            ca = CurveArray()
            for i in range(4): ca.Append(Line.CreateBound(P[i], P[(i + 1) % 4]))
            caa = CurveArrArray(); caa.Append(ca)
            sp = SketchPlane.Create(fd, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ(0, 0, ft(z0))))
            return fd.FamilyCreate.NewExtrusion(True, caa, sp, ft(z1 - z0))
        # origin = centre of the bed; head (high end) at the WEST (-x) end, like the project's Bed01 and Bed04
        box(-1.075, -0.95, 1.075, 0.95, 0.12, 0.38)      # frame / base 1.90 x 2.15 m
        box(-1.00, -0.90, 1.00, 0.90, 0.38, 0.62)        # mattress 1.80 x 2.00 m
        box(-1.075, -0.95, -0.975, 0.95, 0.12, 1.15)     # headboard 100 mm thick, 1.15 m high
        box(-0.95, -0.80, -0.55, -0.05, 0.62, 0.72)      # pillow
        box(-0.95, 0.05, -0.55, 0.80, 0.62, 0.72)        # pillow
        box(-0.30, -0.90, 1.00, 0.90, 0.62, 0.68)        # duvet
        t.Commit()
        so = SaveAsOptions(); so.OverwriteExistingFile = True
        fd.SaveAs(OUT, so)
        say("family saved: " + OUT)
    finally:
        fd.Close(False)
    def load():
        return doc.LoadFamily(OUT)
    say("LoadFamily returned: %s" % run("AMB: load king bed family", load))
s = [s for s in FilteredElementCollector(doc).OfClass(FamilySymbol) if s.FamilyName == "AMB_Bed_King"]
say("king bed symbols in the model: %d" % len(s))
if s:
    def act():
        if not s[0].IsActive: s[0].Activate()
    run("AMB: activate king bed", act)
__output__ = "\n".join(LOG)
