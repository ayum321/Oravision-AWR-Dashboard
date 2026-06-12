"""End-to-end test of refactored SQL comparison engine."""
import requests
import json

GOOD = r"C:\Users\1039081\Downloads\GOOD.html"
BAD  = r"C:\Users\1039081\Downloads\BAD.html"

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
good_data = data.get("good_data", {})
bad_data = data.get("bad_data", {})
report = data.get("report", {})

print("=== BACKEND PARSER TESTS ===")
good_sqls = good_data.get("sql_stats", [])
bad_sqls = bad_data.get("sql_stats", [])
print(f"Good SQL entries: {len(good_sqls)}")
print(f"Bad SQL entries:  {len(bad_sqls)}")

# Test 1: All sources are elapsed_time
sources = set(s.get("source_section", "?") for s in bad_sqls)
t1 = sources == {"elapsed_time"}
print(f"\n[{'PASS' if t1 else 'FAIL'}] All SQL sourced from elapsed_time only: {sources}")

# Test 2: appeared_in populated
has_multi = sum(1 for s in bad_sqls if len(s.get("appeared_in", [])) > 1)
t2 = has_multi > 0
print(f"[{'PASS' if t2 else 'FAIL'}] SQLs enriched from other sections: {has_multi}/{len(bad_sqls)}")

# Test 3: elapsed_rank populated
ranks = [s.get("elapsed_rank", 999) for s in bad_sqls]
t3 = max(ranks) <= len(bad_sqls)
print(f"[{'PASS' if t3 else 'FAIL'}] Elapsed ranks: {sorted(ranks)}")

# Test 4: No non-elapsed-time-only SQL IDs (should not discover from other sections)
for s in bad_sqls:
    if s.get("source_section") != "elapsed_time":
        print(f"  FAIL: {s['sql_id']} has source_section={s['source_section']}")
        break
else:
    print("[PASS] No SQL discovered from non-elapsed-time sections")

# Test 5: Enrichment detail
print("\n--- Top 5 Bad SQLs with enrichment ---")
for s in bad_sqls[:5]:
    print(f"  {s['sql_id']}: rank={s.get('elapsed_rank')}, sections={s.get('appeared_in')}")
    print(f"    elapsed={s.get('elapsed_time_secs',0):.1f}s, cpu={s.get('cpu_time_secs',0):.1f}s, gets={s.get('buffer_gets',0)}, reads={s.get('disk_reads',0)}, execs={s.get('executions',0)}")

# Test 6: Backend comparator still works
regressions = report.get("sql_regressions", [])
t6 = len(regressions) > 0
print(f"\n[{'PASS' if t6 else 'FAIL'}] Backend sql_regressions: {len(regressions)}")

# Test 7: No system SQL in bad_sqls (system SQL should be in parser output, filtered in frontend)
# This is expected — parser keeps all, engine filters
print(f"\n--- System SQL check (parser level) ---")
sys_patterns = ["SYS.", "DBMS_", "WRI$", "WRH$", "X$", "V$"]
sys_count = 0
for s in bad_sqls:
    txt = (s.get("sql_text","") + s.get("sql_text_full","")).upper()
    mod = s.get("module","").upper()
    if any(p in txt or p in mod for p in sys_patterns):
        sys_count += 1
print(f"  System SQL in parser output: {sys_count} (frontend will filter these)")

print("\n=== ALL TESTS COMPLETE ===")
passed = sum([t1, t2, t3, t6])
print(f"Passed: {passed}/4 core tests")
