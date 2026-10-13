# 1) remove the old, untagged slab patch (it overlaps the moved stair); 2) measure every placed bed against standard sizes.
def old_patch():
    out = []
    for f in FilteredElementCollector(doc).OfClass(Floor):
        if type_name(doc.GetElement(f.GetTypeId())) != "AMB_Floor_Upper_280": continue
        bb = f.get_BoundingBox(None)
        if bb is None: continue
        w, d = (bb.Max.X - bb.Min.X) * FT, (bb.Max.Y - bb.Min.Y) * FT
        if w < 1.5 and d < 6.0: out.append((f, w, d))      # the patch is ~1 m wide; the slab is 19 m
    return out
cands = old_patch()
for f, w, d in cands: say("floor %d : %.2f x %.2f m  tagged=%s" % (f.Id.Value, w, d, (_comments_param(f).AsString() or "") if _comments_param(f) else "-"))
# beds
for fam in ("Bed01", "Bed04"):
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if s.FamilyName == fam:
            ps = [(p.Definition.Name, p.AsValueString()) for p in s.Parameters if p.StorageType == StorageType.Double and p.AsDouble() > 0]
            say("%s type '%s' parameters: %s" % (fam, s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString(), ", ".join(["%s=%s" % x for x in ps][:14])))
for e in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Furniture).WhereElementIsNotElementType():
    if isinstance(e, FamilyInstance) and e.Symbol.FamilyName in ("Bed01", "Bed04"):
        bb = e.get_BoundingBox(None)
        p = e.Location.Point
        say("%s id %d at (%.2f, %.2f) m: size %.2f x %.2f x %.2f m (X x Y x Z), rotation %.0f deg, facing=%s" % (e.Symbol.FamilyName, e.Id.Value, (p.X - CX) * FT, (p.Y - CY) * FT,
            (bb.Max.X - bb.Min.X) * FT, (bb.Max.Y - bb.Min.Y) * FT, (bb.Max.Z - bb.Min.Z) * FT, e.Location.Rotation * 57.2958, e.FacingOrientation))
__output__ = "\n".join(LOG)
