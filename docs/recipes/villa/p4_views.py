# Phase 4: plans, 3D view, section; then export PNGs so the result can be inspected by eye.
IMG = r"C:\Users\samo3\AppData\Local\Temp\claude\c--Users-samo3-OneDrive---Heijmans-N-V-Documenten-GitHub-aec-model-bridge\0ba13d00-c907-48cb-84f8-fb5a8038d60c\scratchpad\img\amb"
L0, L1, L2 = level_named("00 begane grond"), level_named("AMB_01 First Floor"), level_named("AMB_02 Roof")
def vft(family):
    for t in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        if t.ViewFamily == family: return t
VIEW_NAMES = ["AMB_Plan_00 Ground", "AMB_Plan_01 First Floor", "AMB_Plan_02 Roof", "AMB_3D Villa", "AMB_Section A-A stair"]
def vname(v): return v.get_Parameter(BuiltInParameter.VIEW_NAME).AsString()
def purge_views():
    ids = List[ElementId]([v.Id for v in FilteredElementCollector(doc).OfClass(View) if not v.IsTemplate and vname(v) in VIEW_NAMES])
    if ids.Count: run("AMB: remove old views", lambda: doc.Delete(ids))
    return ids.Count
say("removed %d old AMB views" % purge_views())
HALF = 14.0
def crop_box(z0=-100.0, z1=100.0):
    bb = BoundingBoxXYZ()
    bb.Min = XYZ(CX - ft(HALF), CY - ft(HALF - 3), z0); bb.Max = XYZ(CX + ft(HALF), CY + ft(HALF + 2), z1)
    return bb
created = {}
def build():
    pt_ = vft(ViewFamily.FloorPlan)
    for lvl, nm in ((L0, VIEW_NAMES[0]), (L1, VIEW_NAMES[1]), (L2, VIEW_NAMES[2])):
        v = ViewPlan.Create(doc, pt_.Id, lvl.Id)
        v.get_Parameter(BuiltInParameter.VIEW_NAME).Set(nm)
        v.Scale = 100
        v.CropBox = crop_box(); v.CropBoxActive = True; v.CropBoxVisible = False
        created[nm] = v
    # isometric view looking at the villa from the south-east
    v3 = View3D.CreateIsometric(doc, vft(ViewFamily.ThreeDimensional).Id)
    v3.get_Parameter(BuiltInParameter.VIEW_NAME).Set(VIEW_NAMES[3])
    eye = XYZ(CX + ft(34), CY + ft(-38), ft(26)); target = XYZ(CX + ft(0.5), CY + ft(1.5), ft(3.0))
    fwd = (target - eye).Normalize(); right = fwd.CrossProduct(XYZ.BasisZ).Normalize(); up = right.CrossProduct(fwd).Normalize()
    v3.SetOrientation(ViewOrientation3D(eye, up, fwd))
    sb = BoundingBoxXYZ(); sb.Min = XYZ(CX - ft(HALF), CY - ft(HALF), ft(-1.5)); sb.Max = XYZ(CX + ft(HALF + 2), CY + ft(HALF), ft(9))
    v3.SetSectionBox(sb); v3.IsSectionBoxActive = True
    v3.DisplayStyle = DisplayStyle.Shading
    created[VIEW_NAMES[3]] = v3
    # section A-A through the stair, looking east
    tr = Transform.Identity
    tr.Origin = XYZ(CX + ft(2.3), CY + ft(1.5), ft(2.5))
    tr.BasisX = XYZ(0, -1, 0); tr.BasisY = XYZ(0, 0, 1); tr.BasisZ = XYZ(-1, 0, 0)
    sbx = BoundingBoxXYZ(); sbx.Transform = tr
    sbx.Min = XYZ(-ft(9.5), -ft(3.7), -ft(8.0)); sbx.Max = XYZ(ft(9.5), ft(5.6), ft(0.3))
    sv = ViewSection.CreateSection(doc, vft(ViewFamily.Section).Id, sbx)
    sv.get_Parameter(BuiltInParameter.VIEW_NAME).Set(VIEW_NAMES[4]); sv.Scale = 100
    created[VIEW_NAMES[4]] = sv
run("AMB: views", build)
say("views created: " + ", ".join(sorted(created.keys())))
# export
ids = List[ElementId]([created[n].Id for n in VIEW_NAMES if n in created])
o = ImageExportOptions()
o.ZoomType = ZoomFitType.FitToPage; o.PixelSize = 1700; o.ImageResolution = ImageResolution.DPI_150
o.FitDirection = FitDirectionType.Horizontal; o.ExportRange = ExportRange.SetOfViews
o.SetViewsAndSheets(ids); o.FilePath = IMG
o.HLRandWFViewsFileType = ImageFileType.PNG; o.ShadowViewsFileType = ImageFileType.PNG
try:
    doc.ExportImage(o); say("images exported")
except Exception as e:
    say("EXPORT FAILED: " + str(e))
__output__ = "\n".join(LOG)
