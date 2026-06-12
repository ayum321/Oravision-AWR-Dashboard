"""Final end-to-end verification of all parsing fixes."""
import sys, os
sys.path.insert(0, 'backend')
from services.html_parser import parse_awr_html, normalize_parsed_data
from services.comparator import compare_periods
from services.health_scorer import calculate_health_score

base = r'C:\Users\1039081\Downloads\Work\AWR-Reports\FF_NEWSKU_PLAN'
good_f = os.path.join(base, 'Good_run_AWR Rpt - ADSPRDDB Snap 203542 thru 203545.html')
bad_f = os.path.join(base, 'Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html')

dicts = {}
for label, path in [('Good', good_f), ('Bad', bad_f)]:
    raw = parse_awr_html(open(path, encoding='utf-8', errors='replace').read())
    model = normalize_parsed_data(raw)
    d = model.model_dump()
    d['addm_findings'] = raw.get('addm_findings', [])
    d['_foreground_wait_events'] = raw.get('_foreground_wait_events', [])
    dicts[label] = d
    h = calculate_health_score(d)
    print(f"\n{'='*60}")
    print(f"  {label} Period: Health={h['score']}({h['grade']})")
    print(f"  CPUs={d['os_stats']['num_cpus']}, Mem={d['os_stats']['phys_mem_gb']:.1f}GB")
    print(f"  SGA components={len(d['sga'])}")
    sga_total = sum(c.get('current_size_mb', 0) for c in d['sga'])
    print(f"  SGA Total={sga_total:.0f} MB")
    print(f"  SQL={len(d['sql_stats'])} statements")
    
    # Top 3 SQL by avg elapsed
    top3 = sorted(d['sql_stats'], key=lambda s: s.get('avg_elapsed_secs', 0) or 0, reverse=True)[:3]
    for s in top3:
        print(f"    SQL {s['sql_id']}: Execs={s['executions']} AvgE={s['avg_elapsed_secs']:.4f}s Total={s['elapsed_time_secs']:.1f}s")
    
    # Top 5 wait events
    print(f"  Top Wait Events:")
    for we in d['wait_events'][:5]:
        wc = we.get('wait_class', '')
        print(f"    {we['event_name']:40s} class={wc:15s} pct={we['pct_db_time']:6.1f}% time={we['time_waited_secs']:.1f}s")
    
    # Efficiency
    eff = d.get('efficiency', {})
    print(f"  Efficiency: BufCache={eff.get('buffer_cache_hit_pct', 0):.1f}%, LibCache={eff.get('library_cache_hit_pct', 0):.1f}%, SoftParse={eff.get('soft_parse_pct', 0):.1f}%")

# Comparison
print(f"\n{'='*60}")
print("COMPARISON RESULTS")
print(f"{'='*60}")
report = compare_periods(dicts['Good'], dicts['Bad'])
s = report.summary
print(f"  Good Health: {s.health_score_good} | Bad Health: {s.health_score_bad}")
print(f"  Severity: {s.severity}")
print(f"  Overall: {s.overall_regression}")

# Top regressions in load profile
print(f"\n  Load Profile Regressions (top 5):")
regressions = [d for d in report.load_profile_delta if d.direction == 'regression']
regressions.sort(key=lambda d: abs(d.delta_pct), reverse=True)
for d in regressions[:5]:
    print(f"    {d.metric:30s} Good={d.good_value:12.2f} Bad={d.bad_value:12.2f} Delta={d.delta_pct:+.1f}% [{d.severity}]")

# SQL regressions
print(f"\n  SQL Issues (non-stable):")
for sr in report.sql_regressions:
    if sr.tag != 'stable':
        print(f"    {sr.sql_id} [{sr.tag}] Good={sr.good_elapsed_secs:.1f}s Bad={sr.bad_elapsed_secs:.1f}s AvgGood={sr.good_avg_elapsed:.4f}s AvgBad={sr.bad_avg_elapsed:.4f}s")

# Wait events
print(f"\n  Wait Event Changes:")
comps = report.top_wait_events.get('comparisons', []) if isinstance(report.top_wait_events, dict) else []
for c in comps:
    if isinstance(c, dict):
        cls = c.get('classification', '')
        if cls in ('new_bottleneck', 'worsening'):
            print(f"    {c['event_name']:40s} [{cls}] Good={c['good_time_secs']:.1f}s Bad={c['bad_time_secs']:.1f}s Delta={c['delta_pct']:+.1f}%")

print("\nDONE.")
