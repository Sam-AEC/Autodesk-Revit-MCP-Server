# Villa 2 MEP: connector-bearing families generated from the project's own generic family "Pole" (no family templates are installed).
# Each family is a body box (real outline) in the right Revit category plus small port cubes; every port carries a real pipe, duct or
# electrical connector on its outward face, so any number of connectors can sit anywhere on the body.
# spec = dict(name, category, w, d, h (m, body centred on x/y, bottom at z=0),
#             ports=[dict(pos=(x, y, z), dir='+x|-x|+y|-y|+z|-z', kind='pipe|duct|elec', system=key, dia_mm | w_mm,h_mm, flow='in|out', label)])
# One family per revit_execute_python call (the bridge gives up after 30 s).
import math, System
from Autodesk.Revit.DB.Plumbing import PipeSystemType
from Autodesk.Revit.DB.Mechanical import DuctSystemType
from Autodesk.Revit.DB.Electrical import ElectricalSystemType

CATS = {"mech": BuiltInCategory.OST_MechanicalEquipment, "plumb": BuiltInCategory.OST_PlumbingFixtures, "air": BuiltInCategory.OST_DuctTerminal,
        "elec_eq": BuiltInCategory.OST_ElectricalEquipment, "elec_fx": BuiltInCategory.OST_ElectricalFixtures, "light": BuiltInCategory.OST_LightingFixtures}
PIPE_SYS = {"cold": PipeSystemType.DomesticColdWater, "hot": PipeSystemType.DomesticHotWater, "san": PipeSystemType.Sanitary, "vent": PipeSystemType.Vent,
            "hsup": PipeSystemType.SupplyHydronic, "hret": PipeSystemType.ReturnHydronic}
DUCT_SYS = {"supply": DuctSystemType.SupplyAir, "return": DuctSystemType.ReturnAir, "exhaust": DuctSystemType.ExhaustAir, "outdoor": DuctSystemType.OtherAir}
ELEC_SYS = {"power": ElectricalSystemType.PowerCircuit, "data": ElectricalSystemType.Data}
PORT = 0.04          # port cube edge, m

def _face_key(face):
    n = face.FaceNormal
    if abs(n.X) > 0.9: return "+x" if n.X > 0 else "-x"
    if abs(n.Y) > 0.9: return "+y" if n.Y > 0 else "-y"
    return "+z" if n.Z > 0 else "-z"

def _box(fd, cx, cy, z0, w, d, h):
    sp = SketchPlane.Create(fd, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ(0, 0, z0 / FT)))
    pts = [(cx - w / 2, cy - d / 2), (cx + w / 2, cy - d / 2), (cx + w / 2, cy + d / 2), (cx - w / 2, cy + d / 2)]
    ca = CurveArray()
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        ca.Append(Line.CreateBound(XYZ(a[0] / FT, a[1] / FT, z0 / FT), XYZ(b[0] / FT, b[1] / FT, z0 / FT)))
    arr = CurveArrArray(); arr.Append(ca)
    return fd.FamilyCreate.NewExtrusion(True, arr, sp, h / FT)

def _faces(fd, ex):
    opt = Options(); opt.ComputeReferences = True; opt.DetailLevel = ViewDetailLevel.Fine
    faces = {}
    for g in ex.get_Geometry(opt):
        if isinstance(g, Solid):
            for f in g.Faces:
                if isinstance(f, PlanarFace): faces[_face_key(f)] = f
    return faces

def _setdia(ce, dia_mm):
    """ConnectorElement.Radius is read-only: the size lives in a built-in parameter."""
    for bip, val in ((BuiltInParameter.CONNECTOR_DIAMETER, dia_mm / 1000.0 / FT), (BuiltInParameter.CONNECTOR_RADIUS, dia_mm / 2000.0 / FT)):
        try:
            pm = ce.get_Parameter(bip)
            if pm is not None and not pm.IsReadOnly:
                pm.Set(val); return True
        except: pass
    return False

def make_mep_family(spec):
    base = [f for f in FilteredElementCollector(doc).OfClass(Family) if f.Name == "Pole"][0]
    fd = doc.EditFamily(base)
    log = []
    try:
        t = Transaction(fd, "AMB2 MEP family " + spec["name"]); t.Start()
        try:
            for e in list(FilteredElementCollector(fd).OfClass(GenericForm)) + list(FilteredElementCollector(fd).OfClass(FamilyInstance)):
                try: fd.Delete(e.Id)            # the base family "Pole" carries a nested "wallbox" (an EV charger): it must not travel into the MEP families
                except: pass
            fd.Regenerate()
            nested = [x for x in FilteredElementCollector(fd).OfClass(FamilyInstance)]
            if nested: log.append("nested instances left: %d" % len(nested))
            fd.OwnerFamily.FamilyCategory = fd.Settings.Categories.get_Item(CATS[spec["category"]])
            _box(fd, 0, 0, 0, spec["w"], spec["d"], spec["h"])
            fd.Regenerate()
            for p in spec.get("ports", []):
                x, y, z = p["pos"]
                ex = _box(fd, x, y, z - PORT / 2, PORT, PORT, PORT)
                fd.Regenerate()
                ref = _faces(fd, ex)[p["dir"]].Reference
                if p["kind"] == "pipe":
                    ce = ConnectorElement.CreatePipeConnector(fd, PIPE_SYS[p["system"]], ref)
                    if not _setdia(ce, p["dia_mm"]): log.append("size not set for " + p.get("label", ""))
                elif p["kind"] == "duct":
                    ce = ConnectorElement.CreateDuctConnector(fd, DUCT_SYS[p["system"]], ConnectorProfileType.Round, ref)
                    if not _setdia(ce, p["dia_mm"]): log.append("size not set for " + p.get("label", ""))
                else:
                    ce = ConnectorElement.CreateElectricalConnector(fd, ELEC_SYS[p.get("system", "power")], ref)
                try:
                    if p.get("flow") and p["kind"] != "elec":
                        pm = ce.get_Parameter(BuiltInParameter.RBS_PIPE_FLOW_DIRECTION_PARAM if p["kind"] == "pipe" else BuiltInParameter.RBS_DUCT_FLOW_DIRECTION_PARAM)
                        if pm is not None: pm.Set({"in": 0, "out": 1, "both": 2}[p["flow"]])
                except Exception as e2: log.append("flow %s: %s" % (p.get("label"), e2))
            t.Commit()
        except Exception as e:
            t.RollBack(); raise
        class Opt(IFamilyLoadOptions):
            def OnFamilyFound(self, inUse, overwrite): return True
            def OnSharedFamilyFound(self, shared, inUse, source, overwrite): return True
        so = SaveAsOptions(); so.OverwriteExistingFile = True
        fd.SaveAs(System.IO.Path.Combine(System.IO.Path.GetTempPath(), spec["name"] + ".rfa"), so)
        fam = fd.LoadFamily(doc, Opt())
        return fam, log
    finally:
        fd.Close(False)

def count_connectors(family_name):
    """Verification: read the connectors of a placed or temporary instance? Here: open the family and count ConnectorElements."""
    fam = [f for f in FilteredElementCollector(doc).OfClass(Family) if f.Name == family_name][0]
    fd = doc.EditFamily(fam)
    try:
        return [(c.Domain.ToString(), str(c.SystemClassification)) for c in FilteredElementCollector(fd).OfClass(ConnectorElement)]
    finally:
        fd.Close(False)
