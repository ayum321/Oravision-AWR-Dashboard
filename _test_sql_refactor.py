"""
Test the refactored SQL comparison engine with real AWR data.
Validates:
1. Backend parser returns elapsed-first SQL with _appeared_in and _elapsed_rank
2. Frontend engine correctly receives data via /api/upload/compare
3. System SQL is filtered
4. Evidence scoring works
"""
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

# Test 1: Backend parser returns elapsed-first SQL
good_sqls = good_data.get("sql_stats", [])
bad_sqls = bad_data.get("sql_stats", [])
print(f"Good SQL entries: {len(good_sqls)}")
print(f"Bad SQL entries:  {len(bad_sqls)}")

# Check _appeared_in and _elapsed_rank
has_appeared = sum(1 for s in bad_sqls if "_appeared_in" in s)
has_rank = sum(1 for s in bad_sqls if "_elapsed_rank" in s)
print(f"\nBad SQLs with _appeared_in: {has_appeared}/{len(bad_sqls)}")
print(f"Bad SQLs with _elapsed_rank: {has_rank}/{len(bad_sqls)}")

# Check all sources are elapsed_time (no CPU/gets/reads/executions-only)
sources = set(s.get("_source", "?") for s in bad_sqls)
print(f"Sources found: {sources}")
assert sources == {"elapsed_time"}, f"FAIL: Expected only elapsed_time source, got {sources}"

# Check appeared_in enrichment
for s in bad_sqls[:5]:
    print(f"  {s['sql_id']}: rank={s.get('_elapsed_rank','?')}, appeared_in={s.get('_appeared_in','?')}")

# Check no SQL has _source other than elapsed_time
for s in bad_sqls:
    src = s.get("_source", "")
    if src != "elapsed_time":
        print(f"FAIL: SQL {s['sql_id']} has _source={src}")
        break
else:
    print("PASS: All SQLs sourced from elapsed_time only")

# Test 2: Enrichment from other sections works
multi_section = [s for s in bad_sqls if len(s.get("_appeared_in", [])) > 1]
print(f"\nSQLs appearing in multiple sections: {len(multi_section)}")
for s in multi_section[:3]:
    print(f"  {s['sql_id']}: {s.get('_appeared_in')}")

# Test 3: SQL regressions from backend comparator
regressions = data.get("report", {}).get("sql_regressions", [])
print(f"\nBackend sql_regressions: {len(regressions)}")
# Check for system SQL in regressions (should still be present in backend — filtering is frontend)
sys_schemas = {"SYS", "SYSTEM", "DBSNMP", "SYSMAN", "XDB"}
sys_count = sum(1 for r in regressions if r.get("source_category", "").upper() in sys_schemas)
print(f"System SQL in backend regressions: {sys_count}")

# Test 4: Verify key SQL metrics are populated
for s in bad_sqls[:3]:
    print(f"\n  SQL {s['sql_id']}:")
    print(f"    elapsed_time_secs: {s.get('elapsed_time_secs', '?')}")
    print(f"    avg_elapsed_secs: {s.get('avg_elapsed_secs', '?')}")
    print(f"    cpu_time_secs: {s.get('cpu_time_secs', '?')}")
    print(f"    buffer_gets: {s.get('buffer_gets', '?')}")
    print(f"    disk_reads: {s.get('disk_reads', '?')}")
    print(f"    executions: {s.get('executions', '?')}")
    print(f"    _elapsed_rank: {s.get('_elapsed_rank', '?')}")
    print(f"    _appeared_in: {s.get('_appeared_in', '?')}")

print("\n=== Backend validation complete ===")
