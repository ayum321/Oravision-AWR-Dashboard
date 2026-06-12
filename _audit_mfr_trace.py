"""Trace the narrative engine decision path for MFR_JOB data."""
import json

data = json.load(open('_audit_mfr_compare.json'))
good = data['good_data']
bad  = data['bad_data']
report = data['report']
summary = report['summary']

print('=== NARRATIVE ENGINE INPUTS ===')
print(f'DB Time Delta: {summary.get("db_time_delta_pct")}%')
print(f'Severity: {summary.get("severity")}')
print(f'Bottleneck shift: {summary.get("bottleneck_shift")}')
print(f'Health: {data["health_good"]["score"]} -> {data["health_bad"]["score"]}')

# What the frontend verdict engine would see:
bad_sqls = sorted(bad.get('sql_stats', []), key=lambda x: -x.get('pct_db_time', 0))
good_sqls = {s['sql_id']: s for s in good.get('sql_stats', [])}

top = bad_sqls[0] if bad_sqls else None
if top:
    g = good_sqls.get(top['sql_id'])
    print(f'\nTop bad SQL: {top["sql_id"]} pct_db={top["pct_db_time"]}% execs={top["executions"]}')
    print(f'  Is new: {g is None}')
    if g:
        print(f'  Good: pct_db={g["pct_db_time"]}% execs={g["executions"]}')

# Check if any SQL dominates (>= 25%)
print('\n--- Top 5 bad SQLs ---')
for s in bad_sqls[:5]:
    is_new = s["sql_id"] not in good_sqls
    print(f'  {s["sql_id"]}: {s["pct_db_time"]}% DB Time (new={is_new})')

# Frontend verdict trace:
# isDominant = topPctDb >= 25 -> NO (top is 10.4%)
# So verdict falls to infrastructure path
print(f'\nisdDominant: {top["pct_db_time"] >= 25 if top else "N/A"} (need >=25%, got {top["pct_db_time"] if top else "?"})') 

# CPU path
print(f'\nDB CPU in bad: 66.7%')
print(f'AAS: Good={summary.get("aas_good")}, Bad={summary.get("aas_bad")}')
print(f'CPUs: {good.get("cpus", 16)}')
print(f'CPU saturated: {summary.get("aas_bad",0) > good.get("cpus",16)}')

# This is a DB Time DECREASE case
print(f'\n{"="*60}')
print(f'KEY ANALYSIS: DB Time DECREASED by 39%')
print(f'{"="*60}')
print(f'Good: 1375s DB Time, AAS=0.39, 1309 execs/s')
print(f'Bad:  838s DB Time,  AAS=0.23, 537 execs/s')
print(f'')
print(f'Headline: "{summary.get("headline")}"')
print(f'Severity: {summary.get("severity")}')
print(f'Overall:  {summary.get("overall_regression")}')

# SQL that DISAPPEARED
print(f'\n=== DISAPPEARED SQLS (Good-only) ===')
bad_ids = {s['sql_id'] for s in bad_sqls}
disappeared_total = 0
for s in sorted(good.get('sql_stats', []), key=lambda x: -x.get('pct_db_time', 0)):
    if s['sql_id'] not in bad_ids:
        print(f'  {s["sql_id"]}: {s["pct_db_time"]}% DB Time, {s["executions"]} execs, {s.get("elapsed_time_secs",0):.0f}s')
        disappeared_total += s.get('elapsed_time_secs', 0)
print(f'  TOTAL disappeared: {disappeared_total:.0f}s')

# SQL that APPEARED
print(f'\n=== NEW SQLS (Bad-only) ===')
good_ids = {s['sql_id'] for s in good.get('sql_stats', [])}
new_total = 0
for s in sorted(bad_sqls, key=lambda x: -x.get('pct_db_time', 0)):
    if s['sql_id'] not in good_ids:
        print(f'  {s["sql_id"]}: {s["pct_db_time"]}% DB Time, {s["executions"]} execs, {s.get("elapsed_time_secs",0):.0f}s')
        new_total += s.get('elapsed_time_secs', 0)
print(f'  TOTAL new: {new_total:.0f}s')

# Common SQL that changed
print(f'\n=== COMMON SQL CHANGES ===')
for sid in good_ids & bad_ids:
    gs = good_sqls[sid]
    bs = {s['sql_id']: s for s in bad_sqls}[sid]
    g_elapsed = gs.get('elapsed_time_secs', 0)
    b_elapsed = bs.get('elapsed_time_secs', 0)
    delta = b_elapsed - g_elapsed
    if abs(delta) > 5:
        print(f'  {sid}: {g_elapsed:.0f}s -> {b_elapsed:.0f}s (delta={delta:+.0f}s)')

print(f'\n{"="*60}')
print(f'INTERPRETATION ASSESSMENT')
print(f'{"="*60}')
print(f'''
This is NOT a regression — DB Time DECREASED 39%.
The "Bad" period label likely refers to a job-level perspective 
(e.g., MFR job timing/throughput), not a database performance regression.

From Oracle DB perspective:
- Both periods are healthy (AAS << CPUs)
- Both are CPU-bound (normal for OLTP/batch)
- No wait event anomalies
- No per-exec regressions in common SQLs
- Storage latency excellent (<0.3ms sequential reads)

The "Bad" run simply had LESS workload:
- Fewer executions (537/s vs 1309/s)
- Lower DB Time (838s vs 1375s)
- Lower redo (378K/s vs 898K/s)
- Lower logical reads (19.8K/s vs 46.2K/s)

Key question: What makes this a "bad" run?
- Likely: the MFR job completed differently (failed, ran partial, etc.)
- The database was NOT the bottleneck in either period
- The performance issue, if any, is at the application/job layer
''')
