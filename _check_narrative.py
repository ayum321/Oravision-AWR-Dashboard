"""Render the PE Narrative for the current comparison in browser and extract it."""
import requests, json

# Check what the narrative actually says
r = requests.get("http://127.0.0.1:8000/")
html = r.text

# Find the PE NARRATIVE section in the rendered page
# It's inside <div id="pe-narrative-deterministic">
idx = html.find('pe-narrative-deterministic')
if idx == -1:
    print("PE Narrative div not found in page")
    # Let's check if the comparison data is available
    print("Page length:", len(html))
else:
    print("Found pe-narrative-deterministic at pos:", idx)

# The narrative is generated client-side via JS, not server-side
# We need to check the ctx and the function logic
# Let me check the backend data that feeds it
data = json.load(open("_audit_full.json"))
good = data["good_data"]
bad = data["bad_data"]
report = data["report"]
summary = report["summary"]

# What the narrative engine sees:
print("=== NARRATIVE ENGINE INPUTS ===")
print(f"primaryVerdict: {summary.get('good_bottleneck')} -> {summary.get('bad_bottleneck')}")
print(f"Bottleneck shift: {summary.get('bottleneck_shift')}")

# Top SQL in bad
bad_sqls = sorted(bad.get("sql_stats", []), key=lambda x: -x.get("pct_db_time", 0))
top = bad_sqls[0] if bad_sqls else None
good_sqls = {s["sql_id"]: s for s in good.get("sql_stats", [])}

if top:
    g = good_sqls.get(top["sql_id"])
    print(f"\nDominant SQL: {top['sql_id']}")
    print(f"  pct_db_time: {top.get('pct_db_time', 0)}%")
    print(f"  is_new: {g is None}")
    print(f"  module: {top.get('module', '')}")
    print(f"  elapsed: {top.get('elapsed_time_secs', 0):.0f}s")
    print(f"  executions: {top.get('executions', 0)}")
    print(f"  epe: {top.get('avg_elapsed_secs', 0):.2f}s")
    print(f"  cpu: {top.get('cpu_time_secs', 0):.0f}s")
    print(f"  gets: {top.get('buffer_gets', 0)}")
    print(f"  reads: {top.get('disk_reads', 0)}")
    print(f"  plan_hash: {top.get('plan_hash_value', '')}")
    if g:
        print(f"  baseline plan_hash: {g.get('plan_hash_value', '')}")
        print(f"  plan_changed: {top.get('plan_hash_value', '') != g.get('plan_hash_value', '')}")

# Wait events analysis
print("\n=== WAIT EVENT INPUTS ===")
for w in sorted(bad.get("wait_events", []), key=lambda x: -x.get("pct_db_time", 0))[:8]:
    print(f"  {w['event_name']:40s} %DB={w['pct_db_time']:5.1f}")

# CPU saturation signals
cpus = bad.get("cpus", 8)
aas = summary.get("aas_bad", 0)
cpu_pct = 0
for w in bad.get("wait_events", []):
    if w["event_name"] == "DB CPU":
        cpu_pct = w["pct_db_time"]
print(f"\n=== CPU ANALYSIS ===")
print(f"  CPUs: {cpus}, AAS: {aas}, CPU%_of_DB_Time: {cpu_pct}%")
print(f"  CPU saturated: {aas > cpus}")

# Latch/concurrency analysis
latch_pct = 0
for w in bad.get("wait_events", []):
    en = w["event_name"].lower()
    if any(p in en for p in ["latch", "buffer busy", "cursor", "enq"]):
        latch_pct += w.get("pct_db_time", 0)
print(f"  Latch/concurrency: {latch_pct:.1f}%")

# Now let's manually trace the narrative logic:
print("\n=== NARRATIVE PATH TRACE ===")

# isSqlDom = domSqlShare >= 25
domSqlShare = top["pct_db_time"] if top else 0
print(f"  domSqlShare: {domSqlShare}% -> isSqlDom={domSqlShare >= 25}")

# _finalPv determination
isCpuBound = cpu_pct >= 35
print(f"  isCpuBound: {isCpuBound} (cpu_pct={cpu_pct})")

# Is the top SQL new?
isNew = top and top["sql_id"] not in good_sqls
print(f"  isNew: {isNew}")

# What path does the narrative take?
# isSqlVerdict: need _finalPv to be in SQL verdicts
# The _pv comes from ctx.evidence.primaryVerdict which is built elsewhere
# But based on the data:
# - top SQL is new (75.6% DB Time)
# - CPU is dominant (43.4%)  
# - no enqueue contention
# So likely _finalPv = 'DOMINANT_SQL' or 'NEW_SQL' or 'CPU_SATURATION'

# SQL is dominant at 75.6%, which is isSqlDom=True
# But _finalPv depends on the evidence/verdict object built upstream

# Check what the evidence/verdict would be
print(f"\n  Based on data: SQL 60yw3d76rn9vt is NEW, 75.6% DB Time, single exec")
print(f"  isSqlVerdict should trigger PART 1 'isNew' branch:")
print(f"  -> 'SQL ID 60yw3d76rn9vt was absent from baseline...'")
print(f"  PART 2 'isNew' branch:")
print(f"  -> 'Root cause: Unvalidated New Workload...'")
print(f"  PART 3: 'workload introduction regression'")

# Check what PART 2 would say specifically
gets_per_exec = top["buffer_gets"] / max(top["executions"], 1)
cpu_frac = (top["cpu_time_secs"] / max(top["elapsed_time_secs"], 1)) * 100
print(f"\n  PART 2 decision tree inputs:")
print(f"    gets/exec: {gets_per_exec:,.0f}")
print(f"    cpu%_of_elapsed: {cpu_frac:.1f}%")
print(f"    execs: {top['executions']}")
print(f"    physReadSpike: {(bad.get('os_stats', {}).get('iowait_pct', 0))}%")

# Load profile physical reads
lp_bad = {m["stat_name"]: m for m in bad.get("load_profile", [])}
lp_good = {m["stat_name"]: m for m in good.get("load_profile", [])}
phys_g = 0
phys_b = 0
for k, m in lp_good.items():
    if "physical read" in k.lower() and "block" in k.lower():
        phys_g = m.get("per_sec", 0)
for k, m in lp_bad.items():
    if "physical read" in k.lower() and "block" in k.lower():
        phys_b = m.get("per_sec", 0)
print(f"    physical_reads/s: good={phys_g}, bad={phys_b}, spike={phys_b > phys_g * 2}")

# PART 1 expected output for isNew:
print(f"\n=== EXPECTED NARRATIVE ===")
print(f"PART 1 (What Happened):")
print(f"  SQL ID 60yw3d76rn9vt was absent from the Good (Baseline) baseline")
print(f"  and appeared in the Bad (Problem) problem period —")
print(f"  consuming 75.6% of DB Time across 1 executions, {gets_per_exec:,.0f} buffer gets/exec,")
print(f"  71,657.3s avg elapsed.")
print(f"  [This is CORRECT — the SQL IS new and IS the dominant consumer]")

print(f"\nPART 2 (Why It Happened):")
print(f"  Root cause: Unvalidated New Workload. SQL 60yw3d76rn9vt has no baseline AWR history.")
print(f"  At 1 executions and {gets_per_exec:,.0f} buffer gets/exec, resource cost dominates DB Time.")
print(f"  [This is CORRECT — it IS new, the optimizer had no feedback]")

print(f"\nPART 3 (What It Means):")
print(f"  Workload introduction regression — at 75.6%, resolving this single SQL")
print(f"  will directly restore baseline performance.")
print(f"  [This is CORRECT — fixing this one SQL recovers 75.6% of DB Time]")

print(f"\nPART 4 (Oracle Mechanism):")
print(f"  Should reference PARALLEL hint, single exec, batch module jbn008_ins_hist")

# But we should check: does the narrative engine actually see _pv as a SQL verdict?
# The _pv comes from ctx.evidence.primaryVerdict
# Let's check what the frontend evidence object looks like
print(f"\n=== CONCERN: Does _finalPv route to SQL path? ===")
print(f"  If evidence.primaryVerdict is 'UNKNOWN' or 'CPU_SATURATION'")
print(f"  and domSqlShare >= 25, the narrative SHOULD still hit the SQL path")
print(f"  because isSqlVerdict checks against the _finalPv value")
print(f"  BUT _finalPv might be overridden to CPU_SATURATION")
print(f"  because aas={aas} > cpus={cpus}")
print(f"  The code checks: if _finalPv == 'CPU_SATURATION' AFTER checking")
print(f"  isSqlVerdict = ['DOMINANT_SQL','NEW_SQL','PLAN_CHANGE','SQL_REGRESSION','SQL_DOMINANT'].includes(_finalPv)")
print(f"  So if _pv starts as 'UNKNOWN' and doesn't get overridden to a SQL verdict,")
print(f"  it goes to CPU_SATURATION path instead of SQL path.")
print(f"  This would be INCORRECT for this data — the root cause is SQL, not CPU.")
