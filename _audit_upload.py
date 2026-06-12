"""Upload new AWR files and dump key data for audit."""
import requests, json

GOOD = r"C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt -goodrun.html"
BAD  = r"C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - badrun.html"

with open(GOOD, "rb") as g, open(BAD, "rb") as b:
    resp = requests.post(
        "http://127.0.0.1:8000/api/upload/compare",
        files={"good_file": ("good.html", g), "bad_file": ("bad.html", b)},
    )

if resp.status_code != 200:
    print(f"FAIL: Upload returned {resp.status_code}")
    print(resp.text[:500])
    exit(1)

data = resp.json()
print("Upload OK")
with open("_audit_response.json", "w") as f:
    json.dump(data, f, indent=2, default=str)
print("Response saved to _audit_response.json")

good = data.get("good_data", {})
bad = data.get("bad_data", {})
report = data.get("report", {})

print("\n=== GOOD (BASELINE) ===")
print(f"DB: {good.get('db_name')}, Host: {good.get('host')}, Instance: {good.get('instance')}")
print(f"Release: {good.get('release')}, CPUs: {good.get('cpus')}, Memory: {good.get('memory_gb')} GB")
print(f"Snap: {good.get('begin_snap')}-{good.get('end_snap')}, Time: {good.get('begin_time')} to {good.get('end_time')}")
print(f"Duration: {good.get('elapsed_min')} min, DB Time: {good.get('db_time_min')} min")
lp = {m['stat_name']: m for m in good.get('load_profile', [])}
aas_g = lp.get('DB Time(s)', {}).get('per_sec', 0) if 'DB Time(s)' in lp else good.get('db_time_min', 0) * 60 / max(good.get('elapsed_min', 1), 1)
print(f"AAS (DB Time/s): {aas_g}")

print("\n=== BAD (PROBLEM) ===")
print(f"DB: {bad.get('db_name')}, Host: {bad.get('host')}, Instance: {bad.get('instance')}")
print(f"Release: {bad.get('release')}, CPUs: {bad.get('cpus')}, Memory: {bad.get('memory_gb')} GB")
print(f"Snap: {bad.get('begin_snap')}-{bad.get('end_snap')}, Time: {bad.get('begin_time')} to {bad.get('end_time')}")
print(f"Duration: {bad.get('elapsed_min')} min, DB Time: {bad.get('db_time_min')} min")
lp2 = {m['stat_name']: m for m in bad.get('load_profile', [])}
aas_b = lp2.get('DB Time(s)', {}).get('per_sec', 0) if 'DB Time(s)' in lp2 else bad.get('db_time_min', 0) * 60 / max(bad.get('elapsed_min', 1), 1)
print(f"AAS (DB Time/s): {aas_b}")

print("\n=== LOAD PROFILE COMPARISON ===")
all_stats = sorted(set(list(lp.keys()) + list(lp2.keys())))
for stat in all_stats:
    g_ps = lp.get(stat, {}).get('per_sec', 0)
    b_ps = lp2.get(stat, {}).get('per_sec', 0)
    if g_ps > 0 or b_ps > 0:
        delta = ((b_ps - g_ps) / g_ps * 100) if g_ps > 0 else float('inf')
        print(f"  {stat:40s}: G={g_ps:>12.2f}  B={b_ps:>12.2f}  Δ={delta:>+8.1f}%")

print("\n=== WAIT EVENTS (Bad Period) ===")
for w in sorted(bad.get('wait_events', []), key=lambda x: -x.get('pct_db_time', 0))[:15]:
    print(f"  {w['event_name']:50s} class={w.get('wait_class','?'):20s} %DB={w.get('pct_db_time',0):5.1f}  avg_ms={w.get('avg_wait_ms',0):8.2f}")

print("\n=== WAIT EVENTS (Good Period) ===")
for w in sorted(good.get('wait_events', []), key=lambda x: -x.get('pct_db_time', 0))[:10]:
    print(f"  {w['event_name']:50s} class={w.get('wait_class','?'):20s} %DB={w.get('pct_db_time',0):5.1f}  avg_ms={w.get('avg_wait_ms',0):8.2f}")

print("\n=== SQL STATS (Bad Period - by elapsed) ===")
bad_sqls = sorted(bad.get('sql_stats', []), key=lambda x: -x.get('elapsed_time_secs', 0))
for i, s in enumerate(bad_sqls[:10]):
    print(f"  #{i+1} {s['sql_id']} rank={s.get('elapsed_rank',999)} elapsed={s.get('elapsed_time_secs',0):.1f}s cpu={s.get('cpu_time_secs',0):.1f}s "
          f"execs={s.get('executions',0)} epe={s.get('avg_elapsed_secs',0):.3f}s %DB={s.get('pct_db_time',0):.1f} "
          f"gets={s.get('buffer_gets',0)} reads={s.get('disk_reads',0)} sections={s.get('appeared_in',[])} "
          f"mod={s.get('module','')[:30]}")

print("\n=== SQL STATS (Good Period - by elapsed) ===")
good_sqls = sorted(good.get('sql_stats', []), key=lambda x: -x.get('elapsed_time_secs', 0))
for i, s in enumerate(good_sqls[:10]):
    print(f"  #{i+1} {s['sql_id']} rank={s.get('elapsed_rank',999)} elapsed={s.get('elapsed_time_secs',0):.1f}s cpu={s.get('cpu_time_secs',0):.1f}s "
          f"execs={s.get('executions',0)} epe={s.get('avg_elapsed_secs',0):.3f}s %DB={s.get('pct_db_time',0):.1f} "
          f"gets={s.get('buffer_gets',0)} reads={s.get('disk_reads',0)} sections={s.get('appeared_in',[])} "
          f"mod={s.get('module','')[:30]}")

print("\n=== EFFICIENCY (Good) ===")
eff_g = good.get('efficiency', {})
for k, v in eff_g.items():
    print(f"  {k}: {v}")

print("\n=== EFFICIENCY (Bad) ===")
eff_b = bad.get('efficiency', {})
for k, v in eff_b.items():
    print(f"  {k}: {v}")

print("\n=== REPORT: SQL REGRESSIONS ===")
regs = report.get('sql_regressions', [])
print(f"Total regressions: {len(regs)}")
for r in regs[:10]:
    print(f"  {r.get('sql_id','')} severity={r.get('severity','')} status={r.get('status','')} "
          f"epe_good={r.get('avg_elapsed_good',0):.3f} epe_bad={r.get('avg_elapsed_bad',0):.3f} "
          f"delta={r.get('elapsed_delta_pct',0):.1f}%")

print("\n=== REPORT: BOTTLENECK SHIFT ===")
bs = report.get('bottleneck_shift', {})
print(f"Primary: {bs.get('primary_bottleneck','?')}")
print(f"Secondary: {bs.get('secondary_factors',[])}")

print("\n=== REPORT: SEVERITY ===")
print(f"Overall: {report.get('severity','?')}")
print(f"Summary: {report.get('summary','?')[:200]}")

print("\n=== OS STATS ===")
os_g = good.get('os_stats', {})
os_b = bad.get('os_stats', {})
print(f"Good: CPUs={os_g.get('num_cpus',0)}, CPU%={os_g.get('cpu_busy_pct',0)}, IO Wait%={os_g.get('iowait_pct',0)}")
print(f"Bad:  CPUs={os_b.get('num_cpus',0)}, CPU%={os_b.get('cpu_busy_pct',0)}, IO Wait%={os_b.get('iowait_pct',0)}")
