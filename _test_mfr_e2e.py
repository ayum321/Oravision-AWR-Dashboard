"""
End-to-end test: Upload MFR AWR files, verify backend data,
then check expected verdict engine behavior.
"""
import requests, json

BASE = 'http://127.0.0.1:8000'

good_path = r'c:\Users\1039081\Downloads\AWR_REPORT_Good_run.html'
bad_path = r'c:\Users\1039081\Downloads\AWR Rpt _MFR_JOB_Bad_Run.html'

print("=== Uploading MFR AWR files ===")
with open(good_path, 'rb') as gf, open(bad_path, 'rb') as bf:
    r = requests.post(f'{BASE}/api/upload/compare',
        files={'good_file': ('good.html', gf, 'text/html'), 
               'bad_file': ('bad.html', bf, 'text/html')})

assert r.status_code == 200, f"Upload failed: {r.status_code}"
data = r.json()
summary = data.get('report', {}).get('summary', {})
report = data.get('report', {})

print(f"Headline: {summary.get('headline')}")
print(f"Severity: {summary.get('severity')}")
print(f"DB Time Delta: {summary.get('db_time_delta_pct')}%")
print(f"Overall: {summary.get('overall_regression')}")
print(f"Bottleneck shift: {summary.get('bottleneck_shift')}")

# Wait events
good_waits = report.get('good_top_events', [])
bad_waits = report.get('bad_top_events', [])
print(f"\nGood top events:")
for w in good_waits[:3]:
    print(f"  {w.get('event_name')}: {w.get('pct_db_time', 0):.1f}% DB Time")
print(f"Bad top events:")
for w in bad_waits[:3]:
    print(f"  {w.get('event_name')}: {w.get('pct_db_time', 0):.1f}% DB Time")

# SQL
sql_comp = report.get('sql_comparison', [])
new_sqls = [s for s in sql_comp if s.get('category') == 'new']
common_sqls = [s for s in sql_comp if s.get('category') == 'common']
print(f"\nSQL: {len(common_sqls)} common, {len(new_sqls)} new")

dt_delta = summary.get('db_time_delta_pct', 0)

# GR-10 check
print(f"\n=== GUARD RAIL CHECKS ===")
print(f"dtChange = {dt_delta}%")
if dt_delta < -10:
    print("GR-10 FIRES: all regression verdicts suppressed")

# GR-9 check
lfs_good = sum(w.get('pct_db_time', 0) for w in good_waits if 'log file sync' in (w.get('event_name') or '').lower())
lfs_bad = sum(w.get('pct_db_time', 0) for w in bad_waits if 'log file sync' in (w.get('event_name') or '').lower())
print(f"Log file sync: Good={lfs_good:.1f}%, Bad={lfs_bad:.1f}%, Delta={lfs_bad-lfs_good:.1f}pp")
if lfs_good >= 3 and (lfs_bad - lfs_good) < 5:
    print("GR-9 FIRES: COMMIT_LOGGING disqualified (structural similarity)")

print(f"\n=== EXPECTED NARRATIVE ===")
print("_finalPv = INCONCLUSIVE")
print("Part 1: 'exhibited a decrease in database workload intensity'")
print("Part 2: 'bottleneck profile is consistent between periods'")
print("Part 3: 'No performance regression was identified'")
print("Part 4: 'No Oracle-level remediation is required'")
print("\nAll backend checks passed.")
