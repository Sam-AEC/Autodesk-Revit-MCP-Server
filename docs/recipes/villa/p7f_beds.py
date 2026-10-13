# Beds placed by MEASUREMENT, not by assumed origin: place roughly, read the real bounding box, snap the head to the wall face,
# centre on the room axis, then put nightstands flush to the same wall either side of the bed.
import math
PH = "p7"
L0, L1 = level_named("00 begane grond"), level_named("AMB_01 First Floor")
BED_FAMS = ("Bed04", "Bed01", "AMB_Bed_King"); NS_FAM = "Mesa de noche - 3D - Genérico - Con cajón y estante"
def sym(fam):
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if s.FamilyName == fam: return s
def old():
    return [e for e in tagged(PH) if isinstance(e, FamilyInstance) and (e.Symbol.FamilyName in BED_FAMS or e.Symbol.FamilyName == NS_FAM)]
def rm():
    ids = List[ElementId]([e.Id for e in old()])
    if ids.Count: doc.Delete(ids)
    return ids.Count
say("removed %s earlier beds/nightstands" % run("AMB: remove beds", rm))
def bb(e, regen=True):
    if regen: doc.Regenerate()
    b = e.get_BoundingBox(None)
    return ((b.Min.X - CX) * FT, (b.Min.Y - CY) * FT, (b.Max.X - CX) * FT, (b.Max.Y - CY) * FT)      # villa-local metres
def move(e, dx, dy):
    if abs(dx) > 1e-6 or abs(dy) > 1e-6: ElementTransformUtils.MoveElement(doc, e.Id, XYZ(ft(dx), ft(dy), 0))
def place(fam, lvl, x, y, rot):
    s = sym(fam)
    if not s.IsActive: s.Activate()
    fi = doc.Create.NewFamilyInstance(XYZ(CX + ft(x), CY + ft(y), 0.0), s, lvl, Structure.StructuralType.NonStructural)
    if rot:
        loc = fi.Location.Point; ElementTransformUtils.RotateElement(doc, fi.Id, Line.CreateBound(loc, loc + XYZ.BasisZ), math.radians(rot))
    tag(fi, PH); return fi
import Autodesk.Revit.DB.Structure as Structure
ROT = {"W": 0, "E": 180, "N": -90, "S": 90}
# (family, level, head side, wall-face coordinate (m), centre of the bed along the wall (m), room name)
BEDS = [("Bed04", L0, "W", -4.93, 5.5, "Guest Suite"), ("AMB_Bed_King", L1, "N", 0.43, 7.0, "Master Bedroom"), ("Bed04", L1, "E", -4.57, -1.75, "Bedroom 2"),
        ("Bed04", L1, "W", -4.43, -1.75, "Bedroom 3"), ("Bed04", L1, "E", -5.07, 5.5, "Bedroom 4")]
report = []
import Autodesk.Revit.DB as DB
def build():
    for (fam, lvl, head, face, along, room) in BEDS:
        bed = place(fam, lvl, face - 1.2 * (1 if head == "W" else -1) if head in "WE" else along, along if head in "WE" else face - 1.2, ROT[head])
        x0, y0, x1, y1 = bb(bed)
        if head == "W": move(bed, face - x0, along - (y0 + y1) / 2)
        elif head == "E": move(bed, face - x1, along - (y0 + y1) / 2)
        elif head == "N": move(bed, along - (x0 + x1) / 2, face - y1)
        x0, y0, x1, y1 = bb(bed)
        w = (y1 - y0) if head in "WE" else (x1 - x0)
        # nightstands: flush to the head wall, one each side of the bed, 40 mm gap
        for side in (-1, 1):
            if head in "WE":
                nx = face + (0.25 if head == "W" else -0.25); ny = (y0 + y1) / 2 + side * (w / 2 + 0.25)
            else:
                nx = (x0 + x1) / 2 + side * (w / 2 + 0.25); ny = face - 0.25
            ns = place(NS_FAM, lvl, nx, ny, ROT[head])
            a0, b0, a1, b1 = bb(ns)                    # rotation is about the family ORIGIN, so re-measure and place by footprint
            if head == "W": move(ns, face - a0, ny - (b0 + b1) / 2)
            elif head == "E": move(ns, face - a1, ny - (b0 + b1) / 2)
            else: move(ns, nx - (a0 + a1) / 2, face - b1)
        report.append((room, fam, head, bed))
run("AMB: beds and nightstands, snapped to the wall", build)
for (room, fam, head, bed) in report:
    x0, y0, x1, y1 = bb(bed, False)
    say("%-14s %-13s head %s : bed footprint x %.2f..%.2f  y %.2f..%.2f m  (%.2f x %.2f)" % (room, fam, head, x0, x1, y0, y1, x1 - x0, y1 - y0))
__output__ = "\n".join(LOG)
