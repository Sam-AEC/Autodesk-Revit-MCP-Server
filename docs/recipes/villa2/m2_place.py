# Villa 2 MEP: place the generated connector-bearing families. DATA = dict(phase, items=[{id, family, x, y (DWG), z_m (above level), level, rot_deg}]).
# Each item is tagged (Comments AMB_V2:<phase>, Mark <id>) and its connectors are read back and printed, so a family without
# connectors or an item in the wrong place is visible immediately.
import math
import Autodesk.Revit.DB.Structure as Structure
PH = DATA["phase"]
say("purged %d earlier %s elements" % (purge(PH), PH))
made = []
def sym_of(fname):
    for f in FilteredElementCollector(doc).OfClass(Family):
        if f.Name == fname:
            return doc.GetElement(list(f.GetFamilySymbolIds())[0])
def place(o):
    s = sym_of(o["family"])
    if s is None: say("NO FAMILY " + o["family"]); return
    if not s.IsActive: s.Activate(); doc.Regenerate()
    lvl = level_named(o["level"])
    pt = P(o["x"], o["y"], 0)
    fi = doc.Create.NewFamilyInstance(XYZ(pt.X, pt.Y, lvl.Elevation), s, lvl, Structure.StructuralType.NonStructural)
    tag(fi, PH); fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).Set(o["id"])
    p = fi.get_Parameter(BuiltInParameter.INSTANCE_ELEVATION_PARAM)
    if p is not None and not p.IsReadOnly: p.Set(o.get("z_m", 0.0) / FT)
    if abs(o.get("rot_deg", 0)) > 1e-6:
        ElementTransformUtils.RotateElement(doc, fi.Id, Line.CreateBound(XYZ(pt.X, pt.Y, 0), XYZ(pt.X, pt.Y, 1)), math.radians(o["rot_deg"]))
    made.append((o, fi))
for o in DATA["items"]:
    run("AMB2: place " + o["id"], lambda o=o: place(o))
try:
    for (o, fi) in made:
        cm = fi.MEPModel.ConnectorManager if fi.MEPModel is not None else None
        cs = [(str(c.Domain), str(c.Description) if False else (str(c.PipeSystemType) if c.Domain == Domain.DomainPiping else str(c.DuctSystemType) if c.Domain == Domain.DomainHvac else "power")) for c in cm.Connectors] if cm is not None else []
        bb = fi.get_BoundingBox(None)
        say("%-10s %-24s z %.2f..%.2f connectors %d %s" % (o["id"], o["family"], bb.Min.Z * FT, bb.Max.Z * FT, len(cs), cs[:3]))
except Exception as e:
    say("verification failed: %s" % e)
__output__ = chr(10).join(LOG)
