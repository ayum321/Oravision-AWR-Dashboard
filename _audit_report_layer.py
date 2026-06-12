"""Audit step 3: server report internals — plan changes, rca_chains, incident indicators, recommendations."""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LABELS = {1:"ALBPRDDB",2:"ADSPRDDB",3:"MFR_JOB",4:"GOOD/BAD",5:"STOREFCST",
          6:"PRNEI77C",7:"goodrun/badrun",8:"CALC_PLAN2",9:"MAP",10:"PRGD5GV4"}

for n in range(1, 11):
    d = json.load(open(f"_audit_p{n}.json", encoding="utf-8"))
    rep = d.get("report") or {}
    print(f"\n{'='*100}\nPAIR {n} — {LABELS[n]}\n{'='*100}")

    pc = rep.get("sql_plan_changes") or []
    print(f"  sql_plan_changes: {len(pc)}")
    for p in pc[:4]:
        print(f"    {json.dumps(p, default=str)[:220]}")

    sr = rep.get("sql_regressions") or []
    print(f"  sql_regressions: {len(sr)}")
    for p in sr[:4]:
        if isinstance(p, dict):
            print(f"    {p.get('sql_id','?'):16s} {str(p.get('reason') or p.get('regression_type') or '')[:80]} ela_delta={p.get('elapsed_delta_pct', p.get('delta_pct','?'))}")
        else:
            print(f"    {str(p)[:150]}")

    nb = rep.get("sql_new_in_bad") or []
    print(f"  sql_new_in_bad: {len(nb)} -> {[x.get('sql_id') if isinstance(x,dict) else x for x in nb[:6]]}")

    ii = rep.get("incident_indicators") or []
    print(f"  incident_indicators: {len(ii)}")
    for i in ii[:6]:
        if isinstance(i, dict):
            print(f"    [{i.get('severity','?'):8s}] {str(i.get('title') or i.get('indicator') or '')[:90]}")
        else:
            print(f"    {str(i)[:120]}")

    rc = rep.get("rca_chains") or []
    print(f"  rca_chains: {len(rc)}")
    for c in rc[:4]:
        if isinstance(c, dict):
            print(f"    {str(c.get('title') or c.get('root_cause') or c.get('chain') or '')[:130]}")
        else:
            print(f"    {str(c)[:130]}")

    recs = rep.get("recommendations") or []
    print(f"  recommendations: {len(recs)}")
    for r in recs[:5]:
        if isinstance(r, dict):
            print(f"    [{str(r.get('priority','?')):4s}] {str(r.get('title') or r.get('recommendation') or '')[:110]}")
        else:
            print(f"    {str(r)[:120]}")

    dbwr = rep.get("dbwr_activity")
    if dbwr:
        print(f"  dbwr_activity: {json.dumps(dbwr, default=str)[:250]}")
