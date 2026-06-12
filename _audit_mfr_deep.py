"""
Deep audit: MFR_JOB Good vs Bad AWR - cross-check dashboard vs raw evidence.
"""
import json

data = json.load(open('_audit_mfr_compare.json'))
good = data['good_data']
bad  = data['bad_data']
report = data['report']
summary = report['summary']
rca = data['comparison_rca']

print("=" * 80)
print("1. DATABASE IDENTITY")
print("=" * 80)
print(f"  Good: DB={good.get('db_name')} Instance={good.get('instance_name')} Host={good.get('host')}")
print(f"  Bad:  DB={bad.get('db_name')} Instance={bad.get('instance_name')} Host={bad.get('host')}")
print(f"  CPUs: Good={good.get('cpus')} Bad={bad.get('cpus')}")
print(f"  Release: Good={good.get('db_version')} Bad={bad.get('db_version')}")
print(f"  Same DB: {good.get('db_name') == bad.get('db_name')}")
print(f"  Same Host: {good.get('host') == bad.get('host')}")

print("\n" + "=" * 80)
print("2. TIME WINDOWS")
print("=" * 80)
gp = summary.get('good_period', {})
bp = summary.get('bad_period', {})
print(f"  Good: snap {gp.get('snap_begin')}-{gp.get('snap_end')}, elapsed={gp.get('elapsed_min',0):.1f} min")
print(f"  Bad:  snap {bp.get('snap_begin')}-{bp.get('snap_end')}, elapsed={bp.get('elapsed_min',0):.1f} min")
print(f"  Good DB Time: {gp.get('db_time_secs',0):.0f}s ({gp.get('db_time_secs',0)/60:.1f} min)")
print(f"  Bad DB Time:  {bp.get('db_time_secs',0):.0f}s ({bp.get('db_time_secs',0)/60:.1f} min)")
print(f"  Good AAS: {gp.get('aas',0):.2f}")
print(f"  Bad AAS:  {bp.get('aas',0):.2f}")

dt_good = gp.get('db_time_secs', 0)
dt_bad = bp.get('db_time_secs', 0)
if dt_good > 0:
    dt_delta = (dt_bad - dt_good) / dt_good * 100
    print(f"\n  DB Time Delta: {dt_delta:+.1f}%")
    if dt_bad < dt_good:
        print("  *** NOTE: BAD period has LOWER DB Time than GOOD period! ***")
        print("  *** This may be a job completion / throughput issue, not a DB Time regression ***")

print("\n" + "=" * 80)
print("3. WAIT EVENTS COMPARISON")
print("=" * 80)

good_waits = sorted(good.get('wait_events', []), key=lambda x: -x.get('pct_db_time', 0))
bad_waits = sorted(bad.get('wait_events', []), key=lambda x: -x.get('pct_db_time', 0))

print("\n  GOOD period top waits:")
for w in good_waits[:10]:
    print(f"    {w['event_name']:45s} %DB={w.get('pct_db_time',0):6.1f}  avg={w.get('avg_wait_ms',0):8.2f}ms")

print("\n  BAD period top waits:")
for w in bad_waits[:10]:
    print(f"    {w['event_name']:45s} %DB={w.get('pct_db_time',0):6.1f}  avg={w.get('avg_wait_ms',0):8.2f}ms")

# Wait event shifts
good_wait_map = {w['event_name']: w for w in good_waits}
bad_wait_map = {w['event_name']: w for w in bad_waits}

print("\n  SIGNIFICANT SHIFTS:")
all_events = set(good_wait_map.keys()) | set(bad_wait_map.keys())
shifts = []
for evt in all_events:
    g = good_wait_map.get(evt, {}).get('pct_db_time', 0)
    b = bad_wait_map.get(evt, {}).get('pct_db_time', 0)
    delta = b - g
    if abs(delta) >= 2 or b >= 5 or g >= 5:
        shifts.append((evt, g, b, delta))
shifts.sort(key=lambda x: -abs(x[3]))
for evt, g, b, d in shifts[:10]:
    direction = "↑" if d > 0 else "↓"
    print(f"    {evt:45s} {g:5.1f}% → {b:5.1f}% ({direction}{abs(d):.1f}pp)")

print("\n" + "=" * 80)
print("4. SQL ANALYSIS")
print("=" * 80)

good_sqls = sorted(good.get('sql_stats', []), key=lambda x: -x.get('pct_db_time', 0))
bad_sqls = sorted(bad.get('sql_stats', []), key=lambda x: -x.get('pct_db_time', 0))

good_sql_map = {s['sql_id']: s for s in good_sqls}
bad_sql_map = {s['sql_id']: s for s in bad_sqls}

print("\n  GOOD period top SQLs:")
for s in good_sqls[:10]:
    module = s.get('module', '') or ''
    print(f"    {s['sql_id']:15s} %DB={s.get('pct_db_time',0):5.1f} execs={s.get('executions',0):>8} elapsed={s.get('elapsed_time_secs',0):>10.1f}s epe={s.get('avg_elapsed_secs',0):>8.2f}s  {module[:30]}")

print("\n  BAD period top SQLs:")
for s in bad_sqls[:10]:
    module = s.get('module', '') or ''
    g = good_sql_map.get(s['sql_id'])
    tag = "NEW" if not g else "COMMON"
    print(f"    {s['sql_id']:15s} %DB={s.get('pct_db_time',0):5.1f} execs={s.get('executions',0):>8} elapsed={s.get('elapsed_time_secs',0):>10.1f}s epe={s.get('avg_elapsed_secs',0):>8.2f}s  [{tag}] {module[:30]}")

# SQL overlap analysis
good_ids = set(good_sql_map.keys())
bad_ids = set(bad_sql_map.keys())
common = good_ids & bad_ids
new_in_bad = bad_ids - good_ids
gone_from_good = good_ids - bad_ids
print(f"\n  SQL Overlap: {len(common)} common, {len(new_in_bad)} new in bad, {len(gone_from_good)} gone from good")

# Common SQL per-exec comparison
print("\n  COMMON SQL per-exec comparison:")
for sid in common:
    g = good_sql_map[sid]
    b = bad_sql_map[sid]
    g_epe = g.get('avg_elapsed_secs', 0) or 0
    b_epe = b.get('avg_elapsed_secs', 0) or 0
    if g_epe > 0:
        ratio = b_epe / g_epe
    else:
        ratio = 0
    g_execs = g.get('executions', 0)
    b_execs = b.get('executions', 0)
    if b.get('pct_db_time', 0) >= 1 or g.get('pct_db_time', 0) >= 1:
        chg = ""
        if ratio > 2: chg = " *** PER-EXEC REGRESSION"
        elif ratio < 0.5: chg = " (improved)"
        print(f"    {sid:15s} epe: {g_epe:8.2f}s → {b_epe:8.2f}s ({ratio:.2f}x) execs: {g_execs} → {b_execs}{chg}")

print("\n" + "=" * 80)
print("5. LOAD PROFILE COMPARISON")
print("=" * 80)

good_lp = {m['stat_name']: m for m in good.get('load_profile', [])}
bad_lp = {m['stat_name']: m for m in bad.get('load_profile', [])}

for key in ['DB Time(s)', 'DB CPU(s)', 'Redo size (bytes)', 'Logical read (blocks)', 
            'Block changes', 'Physical read (blocks)', 'Physical write (blocks)',
            'Executes (SQL)', 'Hard parses (SQL)', 'Parses (SQL)', 'Transactions']:
    g = good_lp.get(key, {}).get('per_sec', 0)
    b = bad_lp.get(key, {}).get('per_sec', 0)
    if g > 0:
        delta = (b - g) / g * 100
        print(f"    {key:30s} {g:>12.1f} → {b:>12.1f}/s ({delta:+.0f}%)")
    elif b > 0:
        print(f"    {key:30s} {g:>12.1f} → {b:>12.1f}/s (NEW)")

print("\n" + "=" * 80)
print("6. DASHBOARD RCA VERDICT")  
print("=" * 80)

print(f"\n  Headline: {summary.get('headline', 'N/A')}")
print(f"  Severity: {summary.get('severity', 'N/A')}")
print(f"  Overall:  {summary.get('overall_regression', 'N/A')}")
print(f"  Bottleneck shift: {summary.get('bottleneck_shift', 'N/A')}")
print(f"  DB Time Δ%: {summary.get('db_time_delta_pct', 'N/A')}")

print(f"\n  Good bottleneck: {summary.get('good_bottleneck', 'N/A')}")
print(f"  Bad bottleneck:  {summary.get('bad_bottleneck', 'N/A')}")

# Headline evidence
print(f"\n  Headline evidence:")
for e in summary.get('headline_evidence', []):
    print(f"    - {e}")

# RCA details
print(f"\n  GOOD RCA verdict:")
rca1 = rca.get('rca1', {}).get('verdict', {})
print(f"    Finding:    {rca1.get('primary_finding', 'N/A')}")
print(f"    Root cause: {rca1.get('root_cause', 'N/A')[:120]}")
print(f"    Bottleneck: {rca1.get('primary_bottleneck', 'N/A')}")
print(f"    Severity:   {rca1.get('severity', 'N/A')}")

print(f"\n  BAD RCA verdict:")
rca2 = rca.get('rca2', {}).get('verdict', {})
print(f"    Finding:    {rca2.get('primary_finding', 'N/A')}")
print(f"    Root cause: {rca2.get('root_cause', 'N/A')[:120]}")
print(f"    Bottleneck: {rca2.get('primary_bottleneck', 'N/A')}")
print(f"    Severity:   {rca2.get('severity', 'N/A')}")

print("\n" + "=" * 80)
print("7. ADVANCED ANALYTICS (CULPRITS, BATCH, COMPOSITION)")
print("=" * 80)

# Get from separate API call
import requests
r = requests.post('http://127.0.0.1:8000/api/compare/', json={'good_snapshot_id': '1', 'bad_snapshot_id': '2'})
if r.status_code == 200:
    api_data = r.json()
    adv = api_data.get('advanced', {})
    
    culprits = adv.get('culprits', [])
    print(f"\n  Culprits ({len(culprits)}):")
    for c in culprits[:5]:
        print(f"    {c.get('sql_id','?'):15s} tag={c.get('tag','?'):20s} %DB={c.get('pct_db_time',0):5.1f} elapsed={c.get('total_elapsed_secs',0):.0f}s batch={c.get('batch_group','')}")
    
    batches = adv.get('batch_groups', [])
    print(f"\n  Batch groups ({len(batches)}):")
    for b in batches:
        print(f"    {b}")
    
    comp = adv.get('workload_composition', {})
    if comp:
        print(f"\n  Workload composition:")
        for k, v in comp.items():
            print(f"    {k}: {v}")
else:
    print(f"  Compare API returned {r.status_code}")

print("\n" + "=" * 80)
print("8. INSTANCE EFFICIENCY COMPARISON")
print("=" * 80)
good_ie = good.get('instance_efficiency', {})
bad_ie = bad.get('instance_efficiency', {})
for k in set(list(good_ie.keys()) + list(bad_ie.keys())):
    gv = good_ie.get(k, 'N/A')
    bv = bad_ie.get(k, 'N/A')
    print(f"    {k:35s} {gv} → {bv}")

print("\n" + "=" * 80)
print("9. I/O & STORAGE")
print("=" * 80)
for period, label, pdata in [('good', 'GOOD', good), ('bad', 'BAD', bad)]:
    io = pdata.get('io_stats', {})
    if io:
        print(f"\n  {label} I/O:")
        for k, v in io.items():
            print(f"    {k}: {v}")
    # Check specific wait events for storage latency
    for w in pdata.get('wait_events', []):
        if 'sequential' in w.get('event_name', '').lower() or 'scattered' in w.get('event_name', '').lower():
            print(f"  {label} {w['event_name']}: avg={w.get('avg_wait_ms',0):.2f}ms %DB={w.get('pct_db_time',0):.1f}%")

print("\n" + "=" * 80)
print("10. KEY OBSERVATIONS FOR VALIDATION")
print("=" * 80)

# Is this a regression or improvement?
if dt_bad < dt_good:
    print("  *** DB Time DECREASED in 'Bad' period — may not be a typical regression ***")
    print("  *** Possible scenarios:")
    print("    - MFR job completed faster (fewer SQLs running)")
    print("    - Job failed or was killed early")
    print("    - Different workload phase (startup vs steady-state)")
    
# AAS analysis
aas_g = gp.get('aas', 0)
aas_b = bp.get('aas', 0)
cpus = good.get('cpus', 16)
print(f"\n  AAS vs CPUs: Good={aas_g:.2f}, Bad={aas_b:.2f}, CPUs={cpus}")
print(f"  CPU saturated Good: {aas_g > cpus}")
print(f"  CPU saturated Bad:  {aas_b > cpus}")
