# Villa 2 MEP: electrical. Native power circuits (ElectricalSystem) from the panel to lights, sockets and the heat pump.
# Each circuit lists real family instances with electrical connectors; the panel is selected, so Revit reports circuit membership.
from Autodesk.Revit.DB.Electrical import ElectricalSystem, ElectricalSystemType
def inst(mark):
    for e in FilteredElementCollector(doc).OfClass(FamilyInstance):
        c = cmt(e)
        if c and c.startswith(TAG) and e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK).AsString() == mark: return e
    raise Exception("no " + mark)
L0, L1 = level_named("00 begane grond"), level_named("AMB2_01 First Floor")
def level_of(e): return e.LevelId.IntegerValue
CIRC = [("C1 Lighting ground floor", ["LT%d" % i for i in range(1, 12)]), ("C2 Lighting first floor", ["LT%d" % i for i in range(12, 21)]),
        ("C3 Sockets ground floor", ["SO%d" % i for i in range(1, 9)]), ("C4 Sockets first floor", ["SO%d" % i for i in range(9, 17)]), ("C5 Heat pump", ["HP"])]
panel = inst("PANEL")
made = []
def one(name, marks):
    ids = List[ElementId]()
    for m in marks: ids.Add(inst(m).Id)
    es = ElectricalSystem.Create(doc, ids, ElectricalSystemType.PowerCircuit)
    es.SelectPanel(panel)
    try: es.get_Parameter(BuiltInParameter.RBS_ELEC_CIRCUIT_NAME).Set(name)
    except Exception as e: say("name: %s" % e)
    tag(es, "m7_electrical")
    made.append((name, es))
for (n, ms) in CIRC:
    run("AMB2: circuit " + n, lambda n=n, ms=ms: one(n, ms))
for (n, es) in made:
    try:
        say("%-26s elements %d  panel %s  circuit no %s  load %s VA" % (n, es.Elements.Size, es.PanelName, es.CircuitNumber, es.ApparentLoad))
    except Exception as e: say("%s: read failed %s" % (n, e))
say("circuits created: %d of %d" % (len(made), len(CIRC)))
__output__ = chr(10).join(LOG)
