# Villa 2 review views and image export (run after prelude2). Needs VIEWS = [(name, eye_dx_m, eye_dy_m, eye_dz_m)] relative to villa-2 centre.
# 3D views are boxed around villa 2 so villa 1 and the rest of the project stay out of the picture.
import System
BOX = (-14.0, -12.0, -2.0, 14.0, 14.0, 12.0)         # local metres min x,y,z / max x,y,z
OUTDIR = r"C:\Users\samo3\Documents\AEC Model Bridge\villa2-review"

def vname(v): return v.get_Parameter(BuiltInParameter.VIEW_NAME).AsString()
def find_view(name):
    for v in FilteredElementCollector(doc).OfClass(View):
        if not v.IsTemplate and vname(v) == name: return v
def vft(fam):
    for x in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        if x.ViewFamily == fam: return x

def make3d(name, dx_, dy_, dz_, box=BOX):
    v = find_view(name)
    if v is None:
        v = View3D.CreateIsometric(doc, vft(ViewFamily.ThreeDimensional).Id)
        v.get_Parameter(BuiltInParameter.VIEW_NAME).Set(name)
    c = M(0, 0, 3.0)
    eye = XYZ(c.X + dx_ / FT, c.Y + dy_ / FT, c.Z + dz_ / FT)
    f = (c - eye).Normalize()
    up = XYZ.BasisZ
    right = f.CrossProduct(up).Normalize()
    up = right.CrossProduct(f).Normalize()
    v.SetOrientation(ViewOrientation3D(eye, up, f))
    bb = BoundingBoxXYZ()
    bb.Min = M(box[0], box[1], box[2]); bb.Max = M(box[3], box[4], box[5])
    v.SetSectionBox(bb)
    v.IsSectionBoxActive = True
    v.DetailLevel = ViewDetailLevel.Fine
    v.DisplayStyle = DisplayStyle.ShadingWithEdges     # Realistic ignores the material colours that these recipes set
    # Frame the picture: a never-opened isometric view exports at the project origin. Cropping the view to the projected
    # section box makes the export fit the villa without needing an open UI view.
    v.CropBoxActive = True
    cb = v.CropBox
    inv = cb.Transform.Inverse
    corners = []
    for x in (box[0], box[3]):
        for y in (box[1], box[4]):
            for z in (box[2], box[5]):
                corners.append(inv.OfPoint(M(x, y, z)))
    xs = [q.X for q in corners]; ys = [q.Y for q in corners]; zs = [q.Z for q in corners]
    mrg = 1.0 / FT
    nb = BoundingBoxXYZ(); nb.Transform = cb.Transform
    nb.Min = XYZ(min(xs) - mrg, min(ys) - mrg, min(zs) - 5.0)
    nb.Max = XYZ(max(xs) + mrg, max(ys) + mrg, max(zs) + 5.0)
    v.CropBox = nb
    v.CropBoxVisible = False
    return v

def export(v, stem, px=1800):
    System.IO.Directory.CreateDirectory(OUTDIR)
    base = OUTDIR + "\\" + stem
    o = ImageExportOptions()
    o.ZoomType = ZoomFitType.FitToPage; o.PixelSize = px; o.ImageResolution = ImageResolution.DPI_150
    o.FitDirection = FitDirectionType.Horizontal; o.ExportRange = ExportRange.SetOfViews
    o.SetViewsAndSheets(List[ElementId]([v.Id])); o.FilePath = base
    o.HLRandWFViewsFileType = ImageFileType.PNG; o.ShadowViewsFileType = ImageFileType.PNG
    doc.ExportImage(o)
    for f in System.IO.Directory.GetFiles(OUTDIR):
        if System.IO.Path.GetFileName(f).startswith(stem): return f
    return None

def level_plan(lvl):
    for v in FilteredElementCollector(doc).OfClass(ViewPlan):
        if not v.IsTemplate and v.ViewType == ViewType.FloorPlan and v.GenLevel is not None and v.GenLevel.Id == lvl.Id: return v

def make_plan(name, level_name, cut_m=1.2, box=BOX, scale=100):
    """Plan view of a level. NOTE: the first plan view of a level is the level's own view and its name IS the level name:
    setting VIEW_NAME on it renames the LEVEL. So an existing/primary view is reused as is and never renamed."""
    lvl = level_named(level_name)
    v = find_view(name) or level_plan(lvl)
    if v is None:
        v = ViewPlan.Create(doc, vft(ViewFamily.FloorPlan).Id, lvl.Id)       # new primary view takes the level's name
        if lvl.get_Parameter(BuiltInParameter.DATUM_TEXT).AsString() != level_name:
            lvl.Name = level_name                                            # (undo any rename done by an earlier version)
    v.Scale = scale
    v.DetailLevel = ViewDetailLevel.Fine
    try: v.get_Parameter(BuiltInParameter.VIEW_DISCIPLINE).Set(1)    # Architectural
    except: pass
    vr = v.GetViewRange()
    vr.SetOffset(PlanViewPlane.CutPlane, cut_m / FT)
    v.SetViewRange(vr)
    v.CropBoxActive = True
    cb = BoundingBoxXYZ()
    lo, hi = M(box[0], box[1], 0), M(box[3], box[4], 0)
    cb.Min = XYZ(lo.X, lo.Y, -50); cb.Max = XYZ(hi.X, hi.Y, 50)
    v.CropBox = cb
    v.CropBoxVisible = False
    return v

def export_view(name, stem=None, px=2000):
    v = find_view(name)
    return export(v, stem or name.replace(" ", "_"), px)
