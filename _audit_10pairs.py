"""Audit: run all 10 AWR pairs through the parser API and capture key extraction data.

For each pair, saves the full response to _audit_p<N>.json and prints a compact
extraction summary: instance, snaps, DB time, AAS, top waits, top SQL, segments found.
This audits the PARSER layer. The verdict layer (client-side JS) is audited separately.
"""
import requests, json, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PAIRS = [
    # (num, good_path, bad_path, label, order_confidence)
    (1, r"C:\Users\1039081\Downloads\AWR Rpt - ALBPRDDB Snap_8thApril_goodrun.html",
        r"C:\Users\1039081\Downloads\AWR Rpt - ALBPRDDB_9thApril.html", "ALBPRDDB", "explicit"),
    (2, r"C:\Users\1039081\Downloads\awr_adsprddb_19april_1210_1240PM.html",
        r"C:\Users\1039081\Downloads\awr_adsprddb_23april_1210_1240AM.html", "ADSPRDDB", "ASSUMED first=good"),
    (3, r"C:\Users\1039081\Downloads\AWR_REPORT_Good_run.html",
        r"C:\Users\1039081\Downloads\AWR Rpt _MFR_JOB_Bad_Run.html", "MFR_JOB", "explicit"),
    (4, r"C:\Users\1039081\Downloads\GOOD.html",
        r"C:\Users\1039081\Downloads\BAD.html", "GOOD/BAD", "explicit"),
    (5, r"C:\Users\1039081\Downloads\AWR Rpt_storefcst_0531.html",
        r"C:\Users\1039081\Downloads\AWR Rpt_storefcst_0607.html", "STOREFCST", "ASSUMED first=good"),
    (6, r"C:\Users\1039081\Downloads\AWR Rpt - PRNEI77C Snap 7642 thru 7643 SUCCESS.html",
        r"C:\Users\1039081\Downloads\AWR Rpt - PRNEI77C Snap 7933 thru 7935 FAIL.html", "PRNEI77C", "explicit"),
    (7, r"C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt -goodrun.html",
        r"C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - badrun.html", "goodrun/badrun", "explicit"),
    (8, r"C:\Users\1039081\Downloads\Work\AWR-Reports\2025-04-14_calc_plan2_14Apr25.html",
        r"C:\Users\1039081\Downloads\Work\AWR-Reports\2025-04-16_calc_plan2_16Apr25.html", "CALC_PLAN2", "ASSUMED 14Apr=good"),
    (9, r"C:\Users\1039081\Downloads\Work\AWR-Reports\2025-03-13_MAP_AWR.html",
        r"C:\Users\1039081\Downloads\Work\AWR-Reports\2025-03-18_MAP1_AWR.html", "MAP", "ASSUMED 13Mar=good"),
    (10, r"C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - PRGD5GV4 Snap 122559 thru 122562--Good Run 19th sep.html",
         r"C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - PRGD5GV4 Snap 122665 thru 122669.html", "PRGD5GV4", "explicit"),
]

API = "http://127.0.0.1:8010/api/upload/compare"

def summarize(num, label, conf, data):
    good, bad = data.get("good_data", {}), data.get("bad_data", {})
    out = []
    out.append(f"\n{'='*100}")
    out.append(f"PAIR {num} — {label}  (order: {conf})")
    out.append(f"{'='*100}")
    for tag, d in (("GOOD", good), ("BAD ", bad)):
        lp = {m.get('stat_name',''): m for m in d.get('load_profile', [])}
        dbt = d.get('db_time_min', 0); el = d.get('elapsed_min', 1) or 1
        aas = dbt / el if el else 0
        out.append(f"  [{tag}] {d.get('db_name')}@{d.get('host')} snap {d.get('begin_snap')}-{d.get('end_snap')} "
                   f"| {d.get('begin_time')} | elapsed {el}m dbtime {dbt}m AAS {aas:.1f} cpus {d.get('cpus')}")
    # Top waits delta
    wg = {w['event_name']: w for w in good.get('wait_events', [])}
    wb = sorted(bad.get('wait_events', []), key=lambda x: -x.get('pct_db_time', 0))[:6]
    out.append("  TOP BAD WAITS (vs good):")
    for w in wb:
        g = wg.get(w['event_name'], {})
        out.append(f"    {w['event_name'][:46]:48s} {g.get('pct_db_time',0):5.1f}% -> {w.get('pct_db_time',0):5.1f}%  avg {w.get('avg_wait_ms',0):.1f}ms cls={w.get('wait_class','?')}")
    # Top SQL delta
    sg = {s.get('sql_id'): s for s in good.get('top_sql', [])}
    sb = sorted(bad.get('top_sql', []), key=lambda x: -(x.get('pct_db_time') or x.get('elapsed_pct') or 0))[:5]
    out.append("  TOP BAD SQL:")
    for s in sb:
        sid = s.get('sql_id'); g = sg.get(sid, {})
        out.append(f"    {sid:16s} pct {g.get('pct_db_time') or g.get('elapsed_pct') or 0:5.1f} -> {s.get('pct_db_time') or s.get('elapsed_pct') or 0:5.1f}"
                   f"  ex {g.get('executions',0)} -> {s.get('executions',0)}"
                   f"  ph {g.get('plan_hash_value','-')} -> {s.get('plan_hash_value','-')}"
                   f"  new={'Y' if sid not in sg else 'n'}")
    # Segments presence
    for tag, d in (("GOOD", good), ("BAD ", bad)):
        segkeys = [k for k in d.keys() if 'seg' in k.lower()]
        seginfo = []
        for k in segkeys:
            v = d.get(k)
            if isinstance(v, list) and v:
                seginfo.append(f"{k}={len(v)}")
        out.append(f"  [{tag}] segment sections: {', '.join(seginfo) if seginfo else 'NONE PARSED'}")
    # Key load profile deltas
    lpg = {m.get('stat_name',''): m for m in good.get('load_profile', [])}
    lpb = {m.get('stat_name',''): m for m in bad.get('load_profile', [])}
    keys = ['Redo size', 'Logical read', 'Physical read', 'Physical write', 'Executes', 'Transactions', 'Hard parses', 'User calls', 'Parses']
    out.append("  LOAD PROFILE (per-sec good -> bad):")
    for k in keys:
        gk = next((v for n, v in lpg.items() if n.lower().startswith(k.lower())), None)
        bk = next((v for n, v in lpb.items() if n.lower().startswith(k.lower())), None)
        if gk or bk:
            gv = (gk or {}).get('per_sec', 0) or 0; bv = (bk or {}).get('per_sec', 0) or 0
            d = ((bv-gv)/gv*100) if gv else (999 if bv else 0)
            out.append(f"    {k:18s} {gv:>14,.1f} -> {bv:>14,.1f}  ({d:+.0f}%)")
    # ADDM
    addm_b = bad.get('addm_findings') or bad.get('addm_report') or []
    out.append(f"  ADDM findings (bad): {len(addm_b) if isinstance(addm_b, list) else 'text-block'}")
    return "\n".join(out)


results = {}
for num, gpath, bpath, label, conf in PAIRS:
    try:
        with open(gpath, "rb") as g, open(bpath, "rb") as b:
            r = requests.post(API, files={"good_file": ("good.html", g), "bad_file": ("bad.html", b)}, timeout=300)
        if r.status_code != 200:
            print(f"\nPAIR {num} {label}: HTTP {r.status_code} — {r.text[:300]}")
            continue
        data = r.json()
        with open(f"_audit_p{num}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, default=str)
        print(summarize(num, label, conf, data))
        results[num] = "OK"
    except Exception as e:
        print(f"\nPAIR {num} {label}: EXCEPTION {e}")
        results[num] = f"FAIL: {e}"

print("\n\n=== SUMMARY ===")
for n, s in results.items():
    print(f"  Pair {n}: {s}")
