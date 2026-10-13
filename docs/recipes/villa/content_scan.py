cats = [("Plumbing Fixtures", BuiltInCategory.OST_PlumbingFixtures), ("Casework", BuiltInCategory.OST_Casework), ("Furniture", BuiltInCategory.OST_Furniture),
        ("Furniture Systems", BuiltInCategory.OST_FurnitureSystems), ("Planting", BuiltInCategory.OST_Planting), ("Entourage", BuiltInCategory.OST_Entourage),
        ("Lighting Fixtures", BuiltInCategory.OST_LightingFixtures), ("Specialty Equipment", BuiltInCategory.OST_SpecialityEquipment), ("Site", BuiltInCategory.OST_Site),
        ("Structural Columns", BuiltInCategory.OST_StructuralColumns), ("Structural Framing", BuiltInCategory.OST_StructuralFraming), ("Railings", BuiltInCategory.OST_StairsRailing),
        ("Parking", BuiltInCategory.OST_Parking), ("Mechanical Equipment", BuiltInCategory.OST_MechanicalEquipment), ("Electrical Fixtures", BuiltInCategory.OST_ElectricalFixtures)]
for label, bic in cats:
    fams = {}
    for s in FilteredElementCollector(doc).OfCategory(bic).OfClass(FamilySymbol):
        fams.setdefault(s.FamilyName, []).append(s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString())
    names = sorted(fams.keys())
    say("%-20s %3d families, %4d types ; e.g. %s" % (label, len(names), sum([len(v) for v in fams.values()]), "; ".join(names[:5])))
__output__ = "\n".join(LOG)
