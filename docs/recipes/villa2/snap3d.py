# Creates (or updates) the AMB2 3D review views and exports PNGs. Set SHOTS before running.
def mk():
    vs = {}
    for (name, a, b, c) in SHOTS: vs[name] = make3d(name, a, b, c)
    return vs
vs = run("AMB2: review views", mk)
for (name, a, b, c) in SHOTS:
    try:
        v = find_view(name)
        f = export(v, name.replace(" ", "_"))
        say("%s -> %s" % (name, f))
    except Exception as e:
        say("export failed for %s: %s" % (name, e))
__output__ = chr(10).join(LOG)
