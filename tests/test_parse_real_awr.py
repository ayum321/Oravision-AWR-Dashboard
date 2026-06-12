"""Test script: parse real AWR HTML files and dump extracted metrics for validation."""
import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from services.html_parser import parse_awr_html, normalize_parsed_data

AWR_DIR = r"C:\Users\1039081\Downloads\Work\AWR-Reports"

# Test files: pick a variety
TEST_FILES = [
    os.path.join(AWR_DIR, "FF_NEWSKU_PLAN", "Good_run_AWR Rpt - ADSPRDDB Snap 203542 thru 203545.html"),
    os.path.join(AWR_DIR, "FF_NEWSKU_PLAN", "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html"),
    os.path.join(AWR_DIR, "AWR Rpt - badrun.html"),
    os.path.join(AWR_DIR, "AWR Rpt -goodrun.html"),
    os.path.join(AWR_DIR, "awrrpt_1_76061_76066.html"),
    os.path.join(AWR_DIR, "2025-03-13_MAP_AWR.html"),
    os.path.join(AWR_DIR, "AWR_CCH.html"),
    os.path.join(AWR_DIR, "FAMESA.html"),
]

def dump_key_metrics(filepath):
    if not os.path.exists(filepath):
        print(f"\n--- SKIP (not found): {os.path.basename(filepath)} ---")
        return None
    
    print(f"\n{'='*80}")
    print(f"FILE: {os.path.basename(filepath)}")
    print(f"{'='*80}")
    
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        html = f.read()
    
    raw = parse_awr_html(html)
    model = normalize_parsed_data(raw)
    data = model.model_dump()
    
    # Key scalar fields
    print(f"  DB Name:       {data.get('db_name', 'MISSING')}")
    print(f"  Instance:      {data.get('instance', 'MISSING')}")
    print(f"  Host:          {data.get('host', 'MISSING')}")
    print(f"  Release:       {data.get('release', 'MISSING')}")
    print(f"  CPUs:          {data.get('cpus', 'MISSING')}")
    print(f"  Snap Range:    {data.get('begin_snap', '?')} - {data.get('end_snap', '?')}")
    print(f"  Begin Time:    {data.get('begin_time', 'MISSING')}")
    print(f"  End Time:      {data.get('end_time', 'MISSING')}")
    print(f"  Elapsed (min): {data.get('elapsed_min', 'MISSING')}")
    print(f"  DB Time (min): {data.get('db_time_min', 'MISSING')}")
    
    # Efficiency
    eff = data.get("efficiency", {})
    print(f"\n  EFFICIENCY:")
    print(f"    Buffer Cache Hit:   {eff.get('buffer_cache_hit_pct', 'MISSING')}%")
    print(f"    Library Cache Hit:  {eff.get('library_cache_hit_pct', 'MISSING')}%")
    print(f"    Soft Parse:         {eff.get('soft_parse_pct', 'MISSING')}%")
    print(f"    Execute to Parse:   {eff.get('execute_to_parse_pct', 'MISSING')}%")
    print(f"    Latch Hit:          {eff.get('latch_hit_pct', 'MISSING')}%")
    
    # Load Profile - key metrics
    lp = data.get("load_profile", [])
    print(f"\n  LOAD PROFILE ({len(lp)} metrics):")
    key_lp = ["redo size", "logical read", "physical read", "hard parse", 
              "parse count", "execute count", "transactions", "db time"]
    for item in lp:
        name = item.get("stat_name", "").lower()
        for kw in key_lp:
            if kw in name:
                print(f"    {item['stat_name']:40s} Per Sec: {item['per_sec']:>12.2f}  Per Txn: {item['per_txn']:>12.2f}")
                break
    
    # Wait Events
    we = data.get("wait_events", [])
    print(f"\n  WAIT EVENTS ({len(we)} events):")
    for w in we[:10]:
        print(f"    {w['event_name']:45s}  Waits: {w['total_waits']:>10}  Time(s): {w['time_waited_secs']:>10.2f}  AvgMs: {w['avg_wait_ms']:>8.2f}  %DB: {w['pct_db_time']:>6.2f}  Class: {w.get('wait_class', '?')}")
    
    # SQL Stats
    sql = data.get("sql_stats", [])
    print(f"\n  SQL STATS ({len(sql)} statements):")
    for s in sql[:5]:
        print(f"    {s['sql_id']:15s}  Elapsed: {s['elapsed_time_secs']:>10.2f}s  CPU: {s['cpu_time_secs']:>10.2f}s  Execs: {s['executions']:>8}  AvgE: {s['avg_elapsed_secs']:>8.4f}s  Plan: {s.get('plan_hash_value', '?')}")
    
    # OS Stats
    os_stats = data.get("os_stats", {})
    print(f"\n  OS STATS:")
    print(f"    CPUs:        {os_stats.get('num_cpus', 'MISSING')}")
    print(f"    CPU Busy %:  {os_stats.get('cpu_busy_pct', 'MISSING')}")
    print(f"    IO Wait %:   {os_stats.get('iowait_pct', 'MISSING')}")
    print(f"    Phys Mem GB: {os_stats.get('phys_mem_gb', 'MISSING')}")
    
    # SGA
    sga = data.get("sga", [])
    print(f"\n  SGA ({len(sga)} components):")
    for s in sga:
        print(f"    {s['component']:40s}  Current: {s['current_size_mb']:>10.2f} MB")
    
    # Time Model
    tm = data.get("time_model", [])
    print(f"\n  TIME MODEL ({len(tm)} stats):")
    for t in tm[:8]:
        print(f"    {t['stat_name']:45s}  Time(s): {t['time_secs']:>12.2f}  %DB: {t['pct_db_time']:>6.2f}")
    
    # Segments
    segs = data.get("segments", [])
    print(f"\n  SEGMENTS ({len(segs)} objects)")
    
    return data

# Parse all test files
results = {}
for fp in TEST_FILES:
    data = dump_key_metrics(fp)
    if data:
        results[os.path.basename(fp)] = data

# Now test comparison with the Good/Bad pair
print("\n\n" + "="*80)
print("COMPARISON TEST: Good vs Bad (FF_NEWSKU_PLAN)")
print("="*80)

good_key = "Good_run_AWR Rpt - ADSPRDDB Snap 203542 thru 203545.html"
bad_key = "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html"

if good_key in results and bad_key in results:
    from services.comparator import compare_periods
    from services.health_scorer import calculate_health_score
    
    good = results[good_key]
    bad = results[bad_key]
    
    h_good = calculate_health_score(good)
    h_bad = calculate_health_score(bad)
    
    print(f"  Health Good: {h_good['score']} ({h_good['grade']})")
    print(f"  Health Bad:  {h_bad['score']} ({h_bad['grade']})")
    
    report = compare_periods(good, bad)
    report_dict = report.model_dump()
    
    print(f"\n  SUMMARY:")
    print(f"    Severity: {report_dict['summary']['severity']}")
    print(f"    Overall:  {report_dict['summary']['overall_regression']}")
    
    print(f"\n  LOAD PROFILE DELTAS (regressions only):")
    for d in report_dict["load_profile_delta"]:
        if d["direction"] == "regression":
            print(f"    {d['metric']:40s}  Good: {d['good_value']:>12.2f}  Bad: {d['bad_value']:>12.2f}  Delta: {d['delta_pct']:>+8.2f}%  [{d['severity']}]")
    
    print(f"\n  WAIT EVENT CHANGES:")
    for w in report_dict["top_wait_events"]["comparisons"]:
        if w["classification"] in ("new_bottleneck", "worsening"):
            print(f"    {w['event_name']:45s}  Good: {w['good_time_secs']:>8.1f}s  Bad: {w['bad_time_secs']:>8.1f}s  Delta: {w['delta_pct']:>+8.0f}%  [{w['classification']}]")
    
    print(f"\n  SQL REGRESSIONS:")
    for s in report_dict["sql_regressions"]:
        if s["tag"] in ("regression", "new_offender"):
            print(f"    {s['sql_id']:15s}  Good: {s['good_elapsed_secs']:>8.1f}s  Bad: {s['bad_elapsed_secs']:>8.1f}s  Delta: {s['delta_pct']:>+8.0f}%  Plan Changed: {s['plan_changed']}  [{s['tag']}]")
    
    print(f"\n  EFFICIENCY COMPARISON:")
    for e in report_dict["instance_efficiency"]["comparisons"]:
        print(f"    {e['metric']:30s}  Good: {e['good_val']:>8.2f}%  Bad: {e['bad_val']:>8.2f}%  Delta: {e['delta']:>+8.2f}pp  [{e['severity']}]")
    
    print(f"\n  INCIDENTS:")
    for i in report_dict["incident_indicators"]:
        print(f"    [{i['severity']}] {i['indicator']}: {i['description'][:120]}")
else:
    print("  Could not find both files")

print("\n\nDONE.")
