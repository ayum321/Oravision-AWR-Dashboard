"""Audit step 2: per-pair verdict + evidence dump from saved responses."""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

LABELS = {1:"ALBPRDDB",2:"ADSPRDDB",3:"MFR_JOB",4:"GOOD/BAD",5:"STOREFCST",
          6:"PRNEI77C",7:"goodrun/badrun",8:"CALC_PLAN2",9:"MAP",10:"PRGD5GV4"}

for n in range(1, 11):
    try:
        d = json.load(open(f"_audit_p{n}.json", encoding="utf-8"))
    except FileNotFoundError:
        print(f"PAIR {n}: missing"); continue
    good, bad = d.get("good_data", {}), d.get("bad_data", {})
    rca = d.get("comparison_rca") or {}
    rep = d.get("report") or {}
    print(f"\n{'='*100}\nPAIR {n} — {LABELS[n]}\n{'='*100}")

    # server-side RCA
    if isinstance(rca, dict):
        print(f"  comparison_rca keys: {sorted(rca.keys())[:20]}")
        for k in ("verdict","primary_verdict","primary","root_cause","summary","confidence","headline"):
            if k in rca:
                v = rca[k]
                print(f"    rca.{k}: {json.dumps(v, default=str)[:400]}")
    # report
    if isinstance(rep, dict):
        print(f"  report keys: {sorted(rep.keys())[:20]}")
        for k in ("verdict","primary_bottleneck","summary","headline","regression_summary"):
            if k in rep:
                print(f"    report.{k}: {json.dumps(rep[k], default=str)[:400]}")

    # SQL deltas
    sg = {s.get("sql_id"): s for s in good.get("sql_stats", [])}
    sb = sorted(bad.get("sql_stats", []), key=lambda x: -(x.get("pct_db_time") or 0))[:6]
    print("  TOP BAD SQL (sql_stats):")
    for s in sb:
        sid = s.get("sql_id"); g = sg.get(sid, {})
        print(f"    {sid:16s} pct {g.get('pct_db_time') or 0:5.1f}->{s.get('pct_db_time') or 0:5.1f}"
              f"  ela {g.get('elapsed_time_secs') or 0:>9.0f}->{s.get('elapsed_time_secs') or 0:>9.0f}s"
              f"  ex {g.get('executions') or 0:>8}->{s.get('executions') or 0:>8}"
              f"  ph {g.get('plan_hash_value') or '-'}-> {s.get('plan_hash_value') or '-'}"
              f"  {'NEW' if sid not in sg else ''} src={s.get('source_section','')[:18]}")
    # Hot segments in bad by contention metrics
    segs = bad.get("segments", [])
    print("  BAD HOT SEGMENTS:")
    for metric in ("buffer_busy_waits","row_lock_waits","itl_waits","physical_writes","physical_reads","logical_reads"):
        top = sorted([s for s in segs if (s.get(metric) or 0) > 0], key=lambda x: -(x.get(metric) or 0))[:2]
        for t in top:
            print(f"    {metric:18s} {t.get('owner','?')}.{t.get('object_name','?')[:36]:38s} ({t.get('object_type','?')}) = {t.get(metric):,}  ({t.get(metric+'_pct') or 0}%)")
    # ASH activity (bad)
    ash = bad.get("_ash_activity", [])
    if ash:
        print("  BAD _ash_activity:")
        for a in ash[:5]:
            print(f"    {a.get('sql_id','?'):16s} {a.get('pct_activity','?'):>6}%  ev={str(a.get('event','?'))[:40]:42s} ph={a.get('plan_hash_value','?')}")
    # ADDM
    print("  BAD ADDM:")
    for f in (bad.get("addm_findings") or [])[:5]:
        print(f"    {str(f.get('finding_name'))[:80]:82s} {f.get('pct_active_sessions','?')}%")
