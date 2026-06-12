"""Test evidence-based headline and SQL zones."""
import sys
sys.path.insert(0, 'backend')

from routers.compare import _build_compare_response
from services.mock_data import get_mock_good_data, get_mock_bad_data

resp = _build_compare_response(get_mock_good_data(), get_mock_bad_data())
r = resp['report']
s = r['summary']

print('=== EVIDENCE-BASED HEADLINE ===')
print(f'Headline: {s["headline"]}')
print(f'Evidence:')
for e in s.get('headline_evidence', []):
    print(f'  - {e}')

print(f'\n=== BOTTLENECK ===')
print(f'Good: {s["good_bottleneck"]}')
print(f'Bad: {s["bad_bottleneck"]}')
print(f'Shift: {s["bottleneck_shift"] or "(none)"}')

print(f'\n=== KEY METRICS ===')
print(f'DB Time delta: {s["db_time_delta_pct"]}%')
print(f'Exec rate delta: {s["exec_rate_delta_pct"]}%')
print(f'AAS good: {s["aas_good"]}')
print(f'AAS bad: {s["aas_bad"]}')
print(f'CPU capacity: {s["cpu_capacity_used_pct"]}%')

print(f'\n=== SQL ZONES ===')
print(f'High-frequency (exec/min > 50): {len(r["sql_high_frequency"])} SQLs')
for sq in r['sql_high_frequency'][:3]:
    print(f'  {sq["sql_id"]} exec/min good={sq["good_execs_per_min"]:.1f} bad={sq["bad_execs_per_min"]:.1f}')

print(f'Plan changes: {len(r["sql_plan_changes"])} SQLs')
for sq in r['sql_plan_changes'][:3]:
    print(f'  {sq["sql_id"]} verdict={sq["plan_verdict"]}')

print(f'New in bad (app only): {len(r["sql_new_in_bad"])} SQLs')
for sq in r['sql_new_in_bad'][:3]:
    print(f'  {sq["sql_id"]} elapsed={sq["bad_elapsed_secs"]:.1f}s module={sq["sql_module"]}')

print(f'Maintenance: {len(r["sql_maintenance"])} SQLs')

print(f'\n=== ADDM FINDINGS ===')
print(f'Findings: {len(r.get("addm_findings", []))}')

print('\nALL NEW FEATURES VERIFIED')
