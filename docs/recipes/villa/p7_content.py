# Phase 7: furniture, sanitary, planting and PV from the project's own Heijmans/Revit content (tagged AMB_VILLA:p7).
PH = "p7"
say("purged %d earlier p7 elements" % purge(PH))
import math
import Autodesk.Revit.DB.Structure as Structure
L0, L1 = level_named("00 begane grond"), level_named("AMB_01 First Floor")
def sym(fam, typ):
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if s.FamilyName == fam and (typ is None or s.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString() == typ): return s
# (family, type or None, x, y, rotation degrees, level)
G, U = L0, L1
ITEMS = [
 # --- ground floor
 ("Bed04", None, -3.8, 5.5, 0, G), ("Mesa de noche - 3D - Genérico - Con cajón y estante", None, -4.7, 4.3, 0, G), ("Mesa de noche - 3D - Genérico - Con cajón y estante", None, -4.7, 6.7, 0, G),
 ("COR_Elm_Sofa 1", "22233_ Sofa_2100w 2", -7.0, -3.2, 0, G), ("COR_Elm_Sofa 1", "22301_ Sofa_Right_2200w 2", -4.2, -1.2, 90, G), ("COR_Elm_Sofa 1", "22251_Recamiere with extension_Left 2", -8.2, 0.8, 270, G),
 ("NLRS_82_FU_UN_tafel 1_gen_ISR", "eettafel ovaal gen bxd 2200x900", -1.0, -2.2, 0, G),
 ("COR_Jalis Chair", None, -1.8, -2.2, 90, G), ("COR_Jalis Chair", None, -0.2, -2.2, 270, G), ("COR_Jalis Chair", None, -1.4, -1.5, 0, G), ("COR_Jalis Chair", None, -0.6, -2.9, 180, G),
 ("73_HB_keukenkast_hoog", None, -2.6, 2.55, 180, G), ("73_HB_keukenkast_ombouw", "kast_indicatief_600_vaatwasser", -2.0, 2.55, 180, G),
 ("73_HB_keukenkast_ombouw", "kast_indicatief_900_wasbak", -1.25, 2.55, 180, G), ("73_HB_keukenkast_ombouw", "kast_indicatief_900_kooktoestel", -0.35, 2.55, 180, G),
 ("NLRS_82_FU_UN_tafel 1_gen_ISR", "eettafel ovaal gen bxd 1800x900", -7.0, 6.0, 0, G), ("COR_Jalis Chair", None, -7.0, 5.2, 0, G),
 # --- first floor
 ("AMB_Bed_King", None, 7.0, -0.65, -90, U), ("Mesa de noche - 3D - Genérico - Con cajón y estante", None, 5.6, 0.05, -90, U), ("Mesa de noche - 3D - Genérico - Con cajón y estante", None, 8.4, 0.05, -90, U),
 ("Bed04", None, -5.7, -1.75, 180, U), ("Mesa de noche - 3D - Genérico - Con cajón y estante", None, -4.8, -3.0, 180, U), ("Mesa de noche - 3D - Genérico - Con cajón y estante", None, -4.8, -0.5, 180, U),
 ("Bed04", None, -3.25, -1.75, 0, U), ("Mesa de noche - 3D - Genérico - Con cajón y estante", None, -4.2, -3.0, 0, U), ("Mesa de noche - 3D - Genérico - Con cajón y estante", None, -4.2, -0.5, 0, U),
 ("Bed04", None, -6.3, 5.5, 180, U), ("Mesa de noche - 3D - Genérico - Con cajón y estante", None, -5.3, 4.2, 180, U), ("Mesa de noche - 3D - Genérico - Con cajón y estante", None, -5.3, 6.8, 180, U),
 # --- sanitary
 ("74_HB_Wandcloset", None, 9.4, 1.0, 270, U), ("52_BZ_wastafel_60", None, 7.5, 2.75, 180, U), ("52_BZ_wastafel_60", None, 8.4, 2.75, 180, U),
 ("74_HB_doucheopsteling_met_mengkraan2", None, 9.3, 2.2, 0, U), ("74_HB_spiegel", None, 8.0, 2.9, 180, U),
 ("74_HB_Wandcloset", None, -1.8, 4.0, 90, U), ("53_BZ_fontein 36cm", None, -1.4, 6.5, 270, U), ("52_BZ_wastafel_60", None, -1.4, 7.4, 270, U),
 ("74_HB_doucheopsteling_met_mengkraan2", None, -4.4, 7.4, 0, U), ("74_HB_spiegel", None, -1.1, 6.9, 270, U),
]
placed = []; failed = []
def build():
    for (fam, typ, x, y, rot, lvl) in ITEMS:
        s = sym(fam, typ)
        if s is None: failed.append("%s/%s: not in model" % (fam, typ)); continue
        try:
            if not s.IsActive: s.Activate()
            loc = XYZ(CX + ft(x), CY + ft(y), 0.0)      # level-based families: z is an offset FROM the level
            fi = doc.Create.NewFamilyInstance(loc, s, lvl, Structure.StructuralType.NonStructural)
            if rot:
                ElementTransformUtils.RotateElement(doc, fi.Id, Line.CreateBound(loc, loc + XYZ.BasisZ), math.radians(rot))
            tag(fi, PH); placed.append((fam, x, y, lvl, fi))
        except Exception as e:
            failed.append("%s at (%.1f,%.1f): %s" % (fam, x, y, str(e)[:70]))
run("AMB: furniture and sanitary", build)
say("placed %d of %d ; failed %d" % (len(placed), len(ITEMS), len(failed)))
for f in failed[:8]: say("   FAILED " + f)
# are they inside a room?
rooms = [r for r in tagged("p3d") if r.Category.Id.IntegerValue == int(BuiltInCategory.OST_Rooms)]
outside = []
for (fam, x, y, lvl, fi) in placed:
    p = XYZ(CX + ft(x), CY + ft(y), lvl.Elevation + 1.0)
    if doc.GetRoomAtPoint(p) is None: outside.append("%s at (%.1f,%.1f)" % (fam[:24], x, y))
say("items whose insertion point is not inside any room: %d %s" % (len(outside), outside[:6]))
__output__ = "\n".join(LOG)
