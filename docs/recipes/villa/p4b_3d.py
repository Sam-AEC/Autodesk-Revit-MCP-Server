IMG = r"C:\Users\samo3\AppData\Local\Temp\claude\c--Users-samo3-OneDrive---Heijmans-N-V-Documenten-GitHub-aec-model-bridge\0ba13d00-c907-48cb-84f8-fb5a8038d60c\scratchpad\img\v2"
def vname(v): return v.get_Parameter(BuiltInParameter.VIEW_NAME).AsString()
v3 = [v for v in FilteredElementCollector(doc).OfClass(View3D) if not v.IsTemplate and vname(v) == "AMB_3D Villa"][0]
def fit():
    bb = v3.CropBox; inv = bb.Transform.Inverse
    xs, ys, zs = [], [], []
    for x in (-13, 14):
        for y in (-18.5, 11.5):
            for z in (-2.0, 8.0):
                q = inv.OfPoint(XYZ(CX + ft(x), CY + ft(y), ft(z))); xs.append(q.X); ys.append(q.Y); zs.append(q.Z)
    m = ft(1.5)
    nb = BoundingBoxXYZ(); nb.Transform = bb.Transform
    nb.Min = XYZ(min(xs) - m, min(ys) - m, bb.Min.Z); nb.Max = XYZ(max(xs) + m, max(ys) + m, bb.Max.Z)
    v3.CropBox = nb; v3.CropBoxActive = True; v3.CropBoxVisible = False
    sb = BoundingBoxXYZ(); sb.Min = XYZ(CX + ft(-14), CY + ft(-19), ft(-2.5)); sb.Max = XYZ(CX + ft(15), CY + ft(12), ft(9))
    v3.SetSectionBox(sb); v3.IsSectionBoxActive = True
run("AMB: fit 3D crop", fit)
o = ImageExportOptions()
o.ZoomType = ZoomFitType.FitToPage; o.PixelSize = 1800; o.ImageResolution = ImageResolution.DPI_150
o.FitDirection = FitDirectionType.Horizontal; o.ExportRange = ExportRange.SetOfViews
o.SetViewsAndSheets(List[ElementId]([v3.Id])); o.FilePath = IMG
o.HLRandWFViewsFileType = ImageFileType.PNG; o.ShadowViewsFileType = ImageFileType.PNG
doc.ExportImage(o)
say("3D exported; total model warnings now: %d (baseline before the villa: 2077)" % len(doc.GetWarnings()))
__output__ = "\n".join(LOG)
