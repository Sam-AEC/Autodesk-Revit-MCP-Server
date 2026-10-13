# Creates plan views of villa 2 and exports them. Set PLANS = [(view name, level name)] before running.
def mkp():
    for (n, l) in PLANS: make_plan(n, l)
run("AMB2: plan views", mkp)
for (n, l) in PLANS:
    try: say("%s -> %s" % (n, export_view(n)))
    except Exception as e: say("export failed %s: %s" % (n, e))
__output__ = chr(10).join(LOG)
