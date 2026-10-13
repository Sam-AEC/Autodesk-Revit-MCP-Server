# remove the four first-run pool/driveway floors that were left behind (untagged), tag the survivors, recheck warnings
dups = [23840502, 23840513, 23840520, 23840531]
def d():
    for i in dups:
        e = doc.GetElement(ElementId(i))
        if e is not None and isinstance(e, Floor): doc.Delete(e.Id); say("deleted duplicate floor %d" % i)
run("AMB: remove duplicate floors", d)
def tg():
    for e in FilteredElementCollector(doc).OfClass(Floor):
        n = type_name(doc.GetElement(e.GetTypeId()))
        if n in ("AMB_Floor_Terrace_150", "AMB_Floor_Water_50") and e.Id.Value >= 23840580: tag(e, "p5")
        if n == "AMB_Floor_Ground_370" and e.Id.Value >= 23840580: tag(e, "p5")
run("AMB: tag p5 floors", tg)
mine = set([e.Id.Value for e in tagged()])
bad = []
for w in doc.GetWarnings():
    ids = [i.Value for i in w.GetFailingElements()] + [i.Value for i in w.GetAdditionalElements()]
    if any([i in mine for i in ids]): bad.append(w.GetDescriptionText())
say("tagged villa elements: %d ; warnings touching them: %d %s" % (len(mine), len(bad), sorted(set(bad))))
__output__ = "\n".join(LOG)
