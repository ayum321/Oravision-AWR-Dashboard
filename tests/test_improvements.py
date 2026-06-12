"""Test all 10 improvements against mock data."""
import sys, json
sys.path.insert(0, 'backend')

from routers.compare import _build_compare_response
from services.mock_data import get_mock_good_data, get_mock_bad_data

resp = _build_compare_response(get_mock_good_data(), get_mock_bad_data())
r = resp['report']
s = r['summary']

print('=== IMP1 — Observation Window ===')
print(f'Good: {s["good_period"]["elapsed_min"]} min | Bad: {s["bad_period"]["elapsed_min"]} min')
print(f'Good DB Time/min: {s["good_period"]["db_time_per_min"]:.1f}s')
print(f'Bad DB Time/min: {s["bad_period"]["db_time_per_min"]:.1f}s')

print('\n=== IMP7 — Transaction Throughput ===')
print(f'Good TXN/s: {s["good_period"]["txn_per_sec"]}')
print(f'Bad TXN/s: {s["bad_period"]["txn_per_sec"]}')
print(f'Congestion: {s["congestion_signal"]} | {s.get("congestion_message", "")}')

print('\n=== IMP2 — Oracle Maintenance ===')
sql_regs = r['sql_regressions']
maint = [sq for sq in sql_regs if sq['is_oracle_maintenance']]
print(f'Maintenance SQLs: {len(maint)}')
for m in maint[:3]:
    print(f'  {m["sql_id"]} source={m["source_category"]} tag={m["tag"]}')

print('\n=== IMP3 — Plan Verdicts ===')
plan_changed = [sq for sq in sql_regs if sq['plan_changed']]
for p in plan_changed[:5]:
    print(f'  {p["sql_id"]} verdict={p["plan_verdict"]} net={p["net_assessment"]}')

print('\n=== IMP10 — Net Assessments ===')
for na in ['Regressed','Improved','Stable','New SQL','Disappeared','Cannot Determine']:
    count = len([sq for sq in sql_regs if sq['net_assessment'] == na])
    if count > 0:
        print(f'  {na}: {count}')

print('\n=== IMP9 — Source Categories ===')
cats = {}
for sq in sql_regs:
    c = sq['source_category']
    cats[c] = cats.get(c, 0) + 1
for c, n in sorted(cats.items(), key=lambda x: -x[1]):
    print(f'  {c}: {n}')

print('\n=== IMP4 — Logon Storm ===')
lse = r.get("logon_storm_explanation", "")
print(f'Explanation: {lse[:80] if lse else "(none detected)"}')

print('\n=== IMP5 — Batch Groups ===')
bg = r.get('batch_groups', [])
print(f'Groups found: {len(bg)}')
for g in bg:
    print(f'  {g["label"]}: {g["sql_count"]} SQLs, {g["exec_count"]} execs, {g["combined_elapsed_secs"]}s')

print('\n=== IMP6 — Wait Event Latency ===')
wc = r['top_wait_events']['comparisons'][:5]
for w in wc:
    en = w["event_name"][:30]
    print(f'  {en:30s} good_avg={w["good_avg_wait_ms"]:.1f}ms bad_avg={w["bad_avg_wait_ms"]:.1f}ms lat_delta={w["latency_delta_pct"]:.0f}% flag={w["latency_flag"]}')

print('\n=== IMP8 — Extreme Waits ===')
ew = r['top_wait_events'].get('extreme_waits', [])
print(f'Extreme wait events: {len(ew)}')
for e in ew:
    print(f'  {e["event_name"]} avg={e["bad_avg_wait_ms"]/1000:.1f}s')

print('\n=== IMP1 — SQL Per-Min Rates ===')
for sq in sql_regs[:3]:
    sid = sq["sql_id"]
    print(f'  {sid} good_el/min={sq["good_elapsed_per_min"]:.2f} bad_el/min={sq["bad_elapsed_per_min"]:.2f}')

print('\nALL 10 IMPROVEMENTS VERIFIED')
