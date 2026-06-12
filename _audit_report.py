"""Deep audit of the comparison report data."""
import json

data = json.load(open("_audit_response.json"))
report = data.get("report", {})

# Check incident indicators
inc = report.get("incident_indicators", [])
print("=== INCIDENT INDICATORS ===")
for i in inc[:5]:
    print(f"  {i}")

# Check RCA chains
rca = report.get("rca_chains", [])
print(f"\n=== RCA CHAINS ({len(rca)}) ===")
for r in rca[:5]:
    print(f"  {r}")

# Check recommendations
recs = report.get("recommendations", [])
print(f"\n=== RECOMMENDATIONS ({len(recs)}) ===")
for r in recs[:5]:
    print(f"  {r}")

# Check batch groups
bg = report.get("batch_groups", [])
print(f"\n=== BATCH GROUPS ({len(bg)}) ===")
for b in bg[:3]:
    print(f"  {b}")

# Check SQL new in bad
snb = report.get("sql_new_in_bad", [])
print(f"\n=== SQL_NEW_IN_BAD ({len(snb)}) ===")
for s in snb[:5]:
    print(f"  {s}")

# Check SQL plan changes
spc = report.get("sql_plan_changes", [])
print(f"\n=== SQL_PLAN_CHANGES ({len(spc)}) ===")
for s in spc[:5]:
    print(f"  {s}")

# Check SQL regressions detail
regs = report.get("sql_regressions", [])
print(f"\n=== SQL REGRESSIONS ({len(regs)}) ===")
for r in regs[:10]:
    sid = r.get("sql_id","")
    sev = r.get("severity","")
    stat = r.get("status","")
    epeg = r.get("avg_elapsed_good",0)
    epeb = r.get("avg_elapsed_bad",0)
    dpct = r.get("elapsed_delta_pct",0)
    pctdb = r.get("pct_db_time_bad",0)
    mod = r.get("module","")
    plan_g = r.get("plan_hash_good","")
    plan_b = r.get("plan_hash_bad","")
    print(f"  {sid}: sev={sev}, stat={stat}, epe_g={epeg:.3f}, epe_b={epeb:.3f}, delta={dpct:.1f}%, %DB={pctdb:.1f}, mod={mod}, plan_g={plan_g}, plan_b={plan_b}")

# normalized comparison
nc = report.get("normalized_comparison", {})
print(f"\n=== NORMALIZED COMPARISON ===")
for k, v in nc.items():
    val = str(v)[:150]
    print(f"  {k}: {val}")

# load profile delta
lpd = report.get("load_profile_delta", [])
print(f"\n=== LOAD PROFILE DELTA ({len(lpd)}) ===")
for l in sorted(lpd, key=lambda x: -abs(x.get("delta_pct", 0)))[:10]:
    sn = l.get("stat_name","")
    gps = l.get("good_per_sec",0)
    bps = l.get("bad_per_sec",0)
    dp = l.get("delta_pct",0)
    print(f"  {sn:40s} good={gps:>12.2f} bad={bps:>12.2f} delta={dp:>+10.1f}%")

# top wait events
twe = report.get("top_wait_events", [])
print(f"\n=== TOP WAIT EVENTS ({len(twe)}) ===")
for w in twe[:10]:
    print(f"  {w}")

# summary details
summary = report.get("summary", {})
print(f"\n=== SUMMARY ===")
for k,v in summary.items():
    val = str(v)[:200]
    print(f"  {k}: {val}")

# ADDM findings
addm = report.get("addm_findings", [])
print(f"\n=== ADDM FINDINGS ({len(addm)}) ===")
for a in addm[:5]:
    print(f"  {a}")

# logon storm
ls = report.get("logon_storm_explanation", "")
print(f"\n=== LOGON STORM ===")
print(f"  {str(ls)[:200]}")
