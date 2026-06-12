"""Deep audit: parse real AWR files and dump EVERY metric for manual cross-check."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from services.html_parser import parse_awr_html, normalize_parsed_data
from services.comparator import compare_periods
from services.health_scorer import calculate_health_score

BASE = r"C:\Users\1039081\Downloads\Work\AWR-Reports\FF_NEWSKU_PLAN"
GOOD = os.path.join(BASE, "Good_run_AWR Rpt - ADSPRDDB Snap 203542 thru 203545.html")
BAD  = os.path.join(BASE, "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html")

def dump_period(label, path):
    print(f"\n{'='*80}")
    print(f"  {label}: {os.path.basename(path)}")
    print(f"{'='*80}")
    
    html = open(path, encoding='utf-8', errors='replace').read()
    raw = parse_awr_html(html)
    model = normalize_parsed_data(raw)
    d = model.model_dump()
    d['addm_findings'] = raw.get('addm_findings', [])
    d['_foreground_wait_events'] = raw.get('_foreground_wait_events', [])
    
    # === Instance Info ===
    print(f"\n--- INSTANCE INFO ---")
    print(f"  DB Name:    {d.get('db_name')}")
    print(f"  Instance:   {d.get('instance')}")
    print(f"  Version:    {d.get('db_version')}")
    print(f"  Host:       {d.get('host')}")
    print(f"  Platform:   {d.get('platform')}")
    print(f"  Snap Begin: {d.get('begin_snap')} at {d.get('begin_time')}")
    print(f"  Snap End:   {d.get('end_snap')} at {d.get('end_time')}")
    print(f"  Elapsed:    {d.get('elapsed_min'):.2f} min")
    print(f"  DB Time:    {d.get('db_time_min'):.2f} min")
    print(f"  CPUs:       {d.get('cpus')}")
    
    # === OS Stats ===
    os_s = d.get('os_stats', {})
    print(f"\n--- OS STATS ---")
    print(f"  Num CPUs:      {os_s.get('num_cpus')}")
    print(f"  CPU Busy %:    {os_s.get('cpu_busy_pct'):.2f}")
    print(f"  IO Wait %:     {os_s.get('iowait_pct'):.2f}")
    print(f"  Phys Mem GB:   {os_s.get('phys_mem_gb'):.2f}")
    print(f"  Free Mem GB:   {os_s.get('free_mem_gb'):.2f}")
    
    # === Load Profile (ALL) ===
    print(f"\n--- LOAD PROFILE ({len(d.get('load_profile',[]))} metrics) ---")
    for lp in d.get('load_profile', []):
        print(f"  {lp['stat_name']:40s}  Per Sec: {lp['per_sec']:>14.2f}  Per Txn: {lp['per_txn']:>14.2f}")
    
    # === Instance Efficiency ===
    eff = d.get('efficiency', {})
    print(f"\n--- INSTANCE EFFICIENCY ---")
    for k, v in sorted(eff.items()):
        print(f"  {k:35s}: {v:>8.2f}%")
    
    # === Top Wait Events (ALL) ===
    print(f"\n--- TOP WAIT EVENTS ({len(d.get('wait_events',[]))} events) ---")
    for we in d.get('wait_events', []):
        print(f"  {we['event_name']:45s} Class={we.get('wait_class',''):15s} "
              f"Waits={we.get('total_waits',0):>12} "
              f"Time={we.get('time_waited_secs',0):>12.1f}s "
              f"AvgWait={we.get('avg_wait_ms',0):>8.2f}ms "
              f"PctDB={we.get('pct_db_time',0):>6.1f}%")
    
    # === Time Model (ALL) ===
    print(f"\n--- TIME MODEL ({len(d.get('time_model',[]))} stats) ---")
    for tm in d.get('time_model', []):
        print(f"  {tm['stat_name']:45s}  Time: {tm['time_secs']:>12.2f}s  PctDB: {tm['pct_db_time']:>6.1f}%")
    
    # === SGA ===
    print(f"\n--- SGA ({len(d.get('sga',[]))} components) ---")
    total_sga = 0
    for s in d.get('sga', []):
        print(f"  {s['component']:30s}  Current: {s['current_size_mb']:>10.1f} MB  "
              f"Min: {s.get('min_size_mb',0):>10.1f} MB  Max: {s.get('max_size_mb',0):>10.1f} MB")
        total_sga += s['current_size_mb']
    print(f"  {'TOTAL':30s}  Current: {total_sga:>10.1f} MB")
    
    # === Top SQL by Elapsed ===
    sqls = sorted(d.get('sql_stats', []), key=lambda s: s.get('elapsed_time_secs', 0), reverse=True)
    print(f"\n--- TOP SQL BY ELAPSED ({len(sqls)} total, showing top 10) ---")
    for s in sqls[:10]:
        print(f"  {s['sql_id']:15s} Elapsed={s['elapsed_time_secs']:>10.1f}s "
              f"CPU={s['cpu_time_secs']:>10.1f}s "
              f"Execs={s['executions']:>10} "
              f"AvgE={s['avg_elapsed_secs']:>10.4f}s "
              f"Gets={s['buffer_gets']:>12} "
              f"Reads={s['disk_reads']:>10} "
              f"PctDB={s.get('pct_db_time',0):>5.1f}% "
              f"Plan={s['plan_hash_value']}")
    
    # === Health Score ===
    h = calculate_health_score(d)
    print(f"\n--- HEALTH SCORE ---")
    print(f"  Score: {h['score']} ({h['grade']})")
    print(f"  Deductions:")
    for ded in h.get('deductions', []):
        print(f"    -{ded['points']:>2}  {ded['reason']}")
    
    return d, raw

print("PARSING GOOD PERIOD...")
good_d, good_raw = dump_period("GOOD", GOOD)
print("\n\nPARSING BAD PERIOD...")
bad_d, bad_raw = dump_period("BAD", BAD)

# === COMPARISON ===
print(f"\n\n{'='*80}")
print("COMPARISON ANALYSIS")
print(f"{'='*80}")
report = compare_periods(good_d, bad_d)
s = report.summary

print(f"\n--- SUMMARY ---")
print(f"  Good: Score={s.health_score_good}, DBTime={s.good_period.db_time_secs:.0f}s, Elapsed={s.good_period.elapsed_secs:.0f}s, AAS={s.good_period.aas:.2f}")
print(f"  Bad:  Score={s.health_score_bad}, DBTime={s.bad_period.db_time_secs:.0f}s, Elapsed={s.bad_period.elapsed_secs:.0f}s, AAS={s.bad_period.aas:.2f}")
print(f"  Severity: {s.severity}")
print(f"  Overall: {s.overall_regression}")

# Load profile deltas - show regressions
print(f"\n--- LOAD PROFILE REGRESSIONS (>{50}% change) ---")
for d in sorted(report.load_profile_delta, key=lambda x: abs(x.delta_pct), reverse=True):
    if abs(d.delta_pct) > 50 and d.direction == 'regression':
        print(f"  {d.metric:35s}  Good={d.good_value:>14.2f}  Bad={d.bad_value:>14.2f}  Delta={d.delta_pct:>+10.1f}%  [{d.severity}]")

# Wait events
comps = report.top_wait_events.get('comparisons', []) if isinstance(report.top_wait_events, dict) else []
print(f"\n--- WAIT EVENT CHANGES ({len(comps)} events) ---")
for c in comps:
    if isinstance(c, dict):
        print(f"  {c['event_name']:45s} [{c['classification']:15s}] "
              f"Good={c['good_time_secs']:>10.1f}s Bad={c['bad_time_secs']:>10.1f}s "
              f"GoodPct={c['good_pct_db_time']:>5.1f}% BadPct={c['bad_pct_db_time']:>5.1f}% "
              f"Delta={c['delta_pct']:>+10.1f}%")

# SQL
print(f"\n--- SQL REGRESSIONS ---")
for sr in report.sql_regressions:
    if sr.tag not in ('stable', 'improved'):
        print(f"  {sr.sql_id:15s} [{sr.tag:14s}] "
              f"GoodE={sr.good_elapsed_secs:>10.1f}s BadE={sr.bad_elapsed_secs:>10.1f}s "
              f"GoodAvg={sr.good_avg_elapsed:>8.4f}s BadAvg={sr.bad_avg_elapsed:>8.4f}s "
              f"GoodExecs={sr.good_executions:>8} BadExecs={sr.bad_executions:>8} "
              f"Plan={sr.plan_changed} [{sr.severity}]")

# Efficiency
print(f"\n--- EFFICIENCY COMPARISON ---")
eff_comps = report.instance_efficiency.get('comparisons', []) if isinstance(report.instance_efficiency, dict) else []
for ec in eff_comps:
    if isinstance(ec, dict):
        print(f"  {ec['metric']:35s}  Good={ec['good_val']:>8.2f}%  Bad={ec['bad_val']:>8.2f}%  Delta={ec['delta']:>+6.2f}pp  [{ec['severity']}]")

print("\nDONE.")
