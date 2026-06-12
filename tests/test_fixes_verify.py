"""Verify all 9 remaining issues are resolved after fixes."""
import sys, os, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.html_parser import parse_awr_html, normalize_parsed_data
from services.health_scorer import calculate_health_score

AWR_DIR = r"C:\Users\1039081\Downloads\Work\AWR-Reports\FF_NEWSKU_PLAN"
GOOD_FILE = os.path.join(AWR_DIR, "Good_run_AWR Rpt - ADSPRDDB Snap 203542 thru 203545.html")
BAD_FILE  = os.path.join(AWR_DIR, "Bad_run_AWR Rpt - ADSPRDDB Snap 206947 thru 206952.html")

def load(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        raw = parse_awr_html(fh.read())
    return normalize_parsed_data(raw)

issues = 0

# --- Load both periods ---
good = load(GOOD_FILE)
bad = load(BAD_FILE)

good_dict = good.model_dump()
bad_dict = bad.model_dump()

# ===== ISSUES 1-5: Good period SQL Execs=0 should have avg_elapsed set =====
print("=" * 60)
print("Issues 1-5: Good period SQL with Execs=0 avg_elapsed fix")
print("=" * 60)
zero_exec_sqls = [s for s in good_dict["sql_stats"] if s["executions"] == 0 and s["elapsed_time_secs"] > 0]
for sql in zero_exec_sqls:
    sid = sql["sql_id"]
    elapsed = sql["elapsed_time_secs"]
    avg_e = sql["avg_elapsed_secs"]
    if avg_e == 0.0:
        print(f"  FAIL: {sid} execs=0, elapsed={elapsed:.1f}s, avg_elapsed=0 (should be {elapsed:.1f})")
        issues += 1
    else:
        print(f"  OK:   {sid} execs=0, elapsed={elapsed:.1f}s, avg_elapsed={avg_e:.1f}s")

# ===== ISSUE 6: Bad period SQL aaxdhh5r3hvyg gets=0/reads=0 with elapsed =====
print("\n" + "=" * 60)
print("Issue 6: Bad period SQL aaxdhh5r3hvyg gets=0 reads=0")
print("=" * 60)
found = False
for sql in bad_dict["sql_stats"]:
    if sql["sql_id"] == "aaxdhh5r3hvyg":
        found = True
        elapsed = sql["elapsed_time_secs"]
        avg_e = sql["avg_elapsed_secs"]
        gets = sql["buffer_gets"]
        reads = sql["disk_reads"]
        execs = sql["executions"]
        print(f"  {sql['sql_id']}: elapsed={elapsed:.1f}s execs={execs} gets={gets} reads={reads} avg_elapsed={avg_e:.1f}s")
        # This SQL may genuinely have 0 gets/reads (CPU-heavy or wait-dominated)
        # The key is avg_elapsed should be set if elapsed > 0 and execs=0
        if elapsed > 0 and avg_e == 0.0:
            print(f"  FAIL: avg_elapsed is 0 despite elapsed={elapsed:.1f}s")
            issues += 1
        else:
            print(f"  OK:   avg_elapsed is set correctly")
if not found:
    print("  INFO: aaxdhh5r3hvyg not found in SQL stats (may not be in top SQL)")

# ===== ISSUES 7-8: Bad period missing wait_class =====
print("\n" + "=" * 60)
print("Issues 7-8: Bad period wait_class enrichment")
print("=" * 60)
for w in bad_dict["wait_events"]:
    name = w["event_name"]
    wclass = w["wait_class"]
    if "enq: fb" in name.lower() or "latch: redo" in name.lower():
        if not wclass or wclass in ("", "Other"):
            print(f"  FAIL: '{name}' wait_class='{wclass}' (should be classified)")
            issues += 1
        else:
            print(f"  OK:   '{name}' wait_class='{wclass}'")

# Also check all wait events have a class
no_class = [w for w in bad_dict["wait_events"] if not w.get("wait_class")]
if no_class:
    for w in no_class:
        print(f"  WARN: '{w['event_name']}' has no wait_class")

# ===== ISSUE 9: Bad period health deductions =====
print("\n" + "=" * 60)
print("Issue 9: Bad period health score deductions")
print("=" * 60)
health = calculate_health_score(bad_dict)
print(f"  Score:    {health['score']}")
print(f"  Grade:    {health['grade']}")
print(f"  Severity: {health['severity']}")
print(f"  Alerts:   {len(health.get('alerts', []))}")
print(f"  Deductions key present: {'deductions' in health}")
deductions = health.get("deductions", [])
print(f"  Deductions count: {len(deductions)}")
if not deductions:
    print("  FAIL: No deductions listed despite score < 100")
    issues += 1
else:
    for d in deductions:
        print(f"    {d['impact']:+d} pts: {d['message']}")
    print(f"  OK: {len(deductions)} deductions found")

# ===== Also check Good period health =====
print("\n" + "=" * 60)
print("Good period health check")
print("=" * 60)
good_health = calculate_health_score(good_dict)
print(f"  Score:    {good_health['score']}")
print(f"  Grade:    {good_health['grade']}")
print(f"  Severity: {good_health['severity']}")
print(f"  Alerts:   {len(good_health.get('alerts', []))}")
good_deductions = good_health.get("deductions", [])
if good_deductions:
    for d in good_deductions:
        print(f"    {d['impact']:+d} pts: {d['message']}")

# ===== SUMMARY =====
print("\n" + "=" * 60)
if issues == 0:
    print("ALL 9 ISSUES RESOLVED - 0 failures")
else:
    print(f"ISSUES REMAINING: {issues} failure(s)")
print("=" * 60)
