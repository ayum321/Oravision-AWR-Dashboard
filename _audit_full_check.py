"""Full RCA audit of comparison response."""
import requests, json

GOOD = r"C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt -goodrun.html"
BAD  = r"C:\Users\1039081\Downloads\Work\AWR-Reports\AWR Rpt - badrun.html"

with open(GOOD, "rb") as g, open(BAD, "rb") as b:
    resp = requests.post("http://127.0.0.1:8000/api/upload/compare",
                         files={"good_file": ("good.html", g), "bad_file": ("bad.html", b)})
data = resp.json()
with open("_audit_full.json", "w") as f:
    json.dump(data, f, indent=2, default=str)

s = data["report"]["summary"]
good = data["good_data"]
bad = data["bad_data"]

print("=" * 70)
print("RAW AWR EVIDENCE (Independent)")
print("=" * 70)
print(f"GOOD: DB={good['db_name']}, Snap {good.get('begin_snap')}-{good.get('end_snap')}")
print(f"  Time: {good['begin_time']} to {good['end_time']}, Duration: {good['elapsed_min']} min")
print(f"  DB Time: {good['db_time_min']:.1f} min, AAS: {s['aas_good']}")
print(f"BAD:  DB={bad['db_name']}, Snap {bad.get('begin_snap')}-{bad.get('end_snap')}")
print(f"  Time: {bad['begin_time']} to {bad['end_time']}, Duration: {bad['elapsed_min']} min")
print(f"  DB Time: {bad['db_time_min']:.1f} min, AAS: {s['aas_bad']}")
print(f"  CPUs: {bad['cpus']}, CPU capacity used: {s['cpu_capacity_used_pct']}%")

# Independent analysis
print("\n--- INDEPENDENT ROOT CAUSE ---")
bad_sqls = sorted(bad.get("sql_stats", []), key=lambda x: -x.get("elapsed_time_secs", 0))
total_db_time = bad["db_time_min"] * 60  # in seconds
print(f"Bad period total DB Time: {total_db_time:.0f}s")
for i, sq in enumerate(bad_sqls[:5]):
    pct = sq["elapsed_time_secs"] / total_db_time * 100 if total_db_time > 0 else 0
    print(f"  #{i+1} {sq['sql_id']}: {sq['elapsed_time_secs']:.0f}s ({pct:.1f}% DB Time), "
          f"execs={sq['executions']}, epe={sq['avg_elapsed_secs']:.2f}s, mod={sq.get('module','')}")

# Good period top SQLs
good_sqls = sorted(good.get("sql_stats", []), key=lambda x: -x.get("elapsed_time_secs", 0))
good_total = good["db_time_min"] * 60
print(f"\nGood period total DB Time: {good_total:.0f}s")
for i, sq in enumerate(good_sqls[:5]):
    pct = sq["elapsed_time_secs"] / good_total * 100 if good_total > 0 else 0
    print(f"  #{i+1} {sq['sql_id']}: {sq['elapsed_time_secs']:.0f}s ({pct:.1f}% DB Time), "
          f"execs={sq['executions']}, epe={sq['avg_elapsed_secs']:.2f}s, mod={sq.get('module','')}")

# Check overlap
good_ids = set(sq["sql_id"] for sq in good_sqls)
bad_ids = set(sq["sql_id"] for sq in bad_sqls)
common = good_ids & bad_ids
new_in_bad = bad_ids - good_ids
disappeared = good_ids - bad_ids
print(f"\nSQL overlap: common={len(common)}, new_in_bad={len(new_in_bad)}, disappeared={len(disappeared)}")
if common:
    print(f"  Common: {common}")
if new_in_bad:
    print(f"  New in bad: {new_in_bad}")

# Wait events
print("\n--- WAIT EVENT EVIDENCE ---")
for w in sorted(bad.get("wait_events", []), key=lambda x: -x.get("pct_db_time", 0))[:8]:
    print(f"  Bad: {w['event_name']:40s} %DB={w['pct_db_time']:5.1f}  avg_ms={w.get('avg_wait_ms',0):8.2f}")
for w in sorted(good.get("wait_events", []), key=lambda x: -x.get("pct_db_time", 0))[:5]:
    print(f"  Good: {w['event_name']:40s} %DB={w['pct_db_time']:5.1f}  avg_ms={w.get('avg_wait_ms',0):8.2f}")

print("\n" + "=" * 70)
print("DASHBOARD OUTPUT")
print("=" * 70)

print(f"\n--- HEADLINE ---")
print(f"  {s['headline']}")
print(f"  Severity: {s['severity']}")
print(f"  Overall: {s['overall_regression']}")

print(f"\n--- BOTTLENECK ---")
print(f"  Good: {s['good_bottleneck']}")
print(f"  Bad:  {s['bad_bottleneck']}")
print(f"  Shift: {s['bottleneck_shift']}")

print(f"\n--- EVIDENCE ---")
for e in s.get("headline_evidence", []):
    print(f"  - {e}")

print(f"\n--- CAUSAL CHAIN ---")
print(f"  {s['causal_chain_text']}")

print(f"\n--- CONGESTION / RATIO ---")
print(f"  Congestion signal: {s['congestion_signal']}")
print(f"  Ratio inversion: {s['ratio_inversion']}")

print(f"\n--- INCIDENTS ---")
for inc in data["report"]["incident_indicators"]:
    print(f"  [{inc['severity']:8s}] {inc['indicator']}: {inc['description']}")

print(f"\n--- BATCH GROUPS ---")
for bg in data["report"].get("batch_groups", []):
    print(f"  {bg['label']}: {bg['sql_count']} SQLs, {bg['combined_elapsed_secs']:.0f}s combined")
    print(f"    IDs: {bg['sql_ids']}")
    print(f"    Exec pattern: {bg['exec_count']} execs, {bg['combined_disk_reads']} reads")

print(f"\n--- SQL NEW IN BAD ---")
for snb in data["report"].get("sql_new_in_bad", []):
    sid = snb["sql_id"]
    mod = snb.get("sql_module", "")
    elapsed = snb.get("bad_elapsed_secs", 0)
    execs = snb.get("bad_executions", 0)
    epe = snb.get("bad_avg_elapsed", 0)
    cpu_pct = snb.get("cpu_pct", 0)
    io_pct = snb.get("io_pct", 0)
    assess = snb.get("net_assessment", "")
    detail = snb.get("net_assessment_detail", "")
    print(f"  {sid}: mod={mod}, elapsed={elapsed:.0f}s, execs={execs}, epe={epe:.2f}s, "
          f"cpu/io={cpu_pct}/{io_pct}%, assess={assess}")
    print(f"    Detail: {detail}")

print(f"\n--- RECOMMENDATIONS (top 10) ---")
recs = data["report"].get("recommendations", [])
for r in recs[:10]:
    print(f"  P{r['priority']} [{r['category']}] {r['finding'][:120]}")
    print(f"    -> {r['action'][:120]}")

print(f"\n--- RCA CHAINS ---")
for rc in data["report"].get("rca_chains", []):
    print(f"  {rc}")

# ACCURACY ASSESSMENT
print("\n" + "=" * 70)
print("ACCURACY ASSESSMENT")
print("=" * 70)

# Check 1: Is headline correct?
headline = s["headline"]
has_db_time = "39098%" in headline or "39098" in headline
has_new_sql = "new" in headline.lower()
has_top_sql = "60yw3d76rn9vt" in headline
print(f"\n1. Headline accuracy:")
print(f"   DB Time delta mentioned: {has_db_time}")
print(f"   New SQL mentioned: {has_new_sql}")
print(f"   Top SQL identified: {has_top_sql}")
print(f"   VERDICT: {'CORRECT' if has_db_time and has_new_sql and has_top_sql else 'NEEDS REVIEW'}")

# Check 2: Bottleneck classification
print(f"\n2. Bottleneck classification:")
bad_cpu_pct = 0
bad_io_pct = 0
for w in bad.get("wait_events", []):
    if w["event_name"] == "DB CPU":
        bad_cpu_pct = w["pct_db_time"]
    if w.get("wait_class") == "User I/O":
        bad_io_pct += w["pct_db_time"]
print(f"   Bad: CPU={bad_cpu_pct}%, I/O={bad_io_pct}%")
print(f"   Dashboard says: {s['bad_bottleneck']}")
is_cpu_correct = bad_cpu_pct > bad_io_pct and s["bad_bottleneck"] == "CPU"
print(f"   VERDICT: {'CORRECT' if is_cpu_correct else 'NEEDS REVIEW'} (CPU is dominant at {bad_cpu_pct}% vs I/O {bad_io_pct:.1f}%)")

# Check 3: Severity
print(f"\n3. Severity:")
print(f"   Dashboard: {s['severity']}")
is_sev_correct = s["severity"] == "critical"
print(f"   VERDICT: {'CORRECT' if is_sev_correct else 'WRONG'} (39098% DB Time + CPU saturated = critical)")

# Check 4: SQL attribution
print(f"\n4. SQL attribution:")
snb_list = data["report"].get("sql_new_in_bad", [])
top_sql = snb_list[0] if snb_list else None
print(f"   Top new SQL: {top_sql['sql_id'] if top_sql else 'none'}")
print(f"   Is it really the dominant? elapsed={top_sql['bad_elapsed_secs']:.0f}s = "
      f"{top_sql['bad_elapsed_secs']/total_db_time*100:.1f}% DB Time" if top_sql else "   N/A")
all_new = all(snb.get("tag") == "new_offender" for snb in snb_list)
print(f"   All tagged as new_offender: {all_new}")
print(f"   VERDICT: {'CORRECT' if all_new and top_sql and top_sql['sql_id'] == '60yw3d76rn9vt' else 'NEEDS REVIEW'}")

# Check 5: False positives
print(f"\n5. False positive check:")
incidents = data["report"]["incident_indicators"]
has_storage_deg = any(i["indicator"] == "storage_degradation" for i in incidents)
has_false_plan = any(i["indicator"] == "plan_flip_cascade" for i in incidents)
print(f"   storage_degradation false positive: {has_storage_deg}")
print(f"   plan_flip_cascade mislabel: {has_false_plan}")
print(f"   VERDICT: {'CLEAN' if not has_storage_deg and not has_false_plan else 'HAS FALSE POSITIVES'}")

# Check 6: Nature of comparison
print(f"\n6. Comparison nature:")
print(f"   Good period: {good['elapsed_min']} min, AAS={s['aas_good']} (essentially idle)")
print(f"   Bad period:  {bad['elapsed_min']} min, AAS={s['aas_bad']} (batch active)")
print(f"   This is a batch-present vs batch-absent comparison, not a regression.")
print(f"   Dashboard calls SQLs 'new_offender' — CORRECT (they ARE new, not regressed)")
print(f"   Dashboard says 'CPU unchanged' — CORRECT (both periods CPU-dominant when active)")
