# Phase 3b2: tag the roof created through the add-in command and measure it.
import sys
rid = ROOF_ID
r = doc.GetElement(ElementId(rid))
def t():
    tag(r, "p3b")
    r.get_Parameter(BuiltInParameter.ROOF_BASE_LEVEL_PARAM)   # touch to confirm it is a roof
run("AMB: tag roof", t)
lo, hi = zrange_m(r)
say("roof id %d type %s  z %.3f .. %.3f m  (thickness %.0f mm)" % (rid, type_name(doc.GetElement(r.GetTypeId())), lo, hi, (hi - lo) * 1000))
__output__ = "\n".join(LOG)
