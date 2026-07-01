"""
Proves the Diagnostic Memory CBR engine: signature, match, golden consensus,
learning (record), self-audit drift flag, and feedback confirmation.

Run:  python tests/test_diagnostic_memory.py
"""
from __future__ import annotations
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models.snapshot import AWRData
from services.comparator import compare_periods
from services import diagnostic_memory as dm

# Use an isolated temp store so the test never pollutes real data.
dm._store = dm.CaseStore(path=os.path.join(tempfile.gettempdir(), "dm_test_store.json"))
if os.path.exists(dm._store.path):
    os.remove(dm._store.path)
dm._store = dm.CaseStore(path=dm._store.path)

EFF = ["buffer_cache_hit_pct", "library_cache_hit_pct", "soft_parse_pct", "execute_to_parse_pct", "latch_hit_pct"]

def snap(dbmin, waits, cpus=16):
    return AWRData(db_name="ORCL", cpus=cpus, memory_gb=128, begin_snap=1, end_snap=2,
                   elapsed_min=60, db_time_min=dbmin, efficiency_available=EFF,
                   load_profile=[{"stat_name": "Transactions", "per_sec": 200}],
                   wait_events=waits).model_dump()

def w(name, cls, pct, ms):
    return {"event_name": name, "wait_class": cls, "pct_db_time": pct, "avg_wait_ms": ms,
            "time_waited_secs": 2000, "total_waits": 100000}

def report(good, bad):
    return compare_periods(good, bad).model_dump()

results = []
def check(name, ok):
    results.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")

print("\n=== DIAGNOSTIC MEMORY (CBR) ENGINE ===")

# 1. Golden library seeded
check("golden library seeded (>=12 cases)", len(dm._get_store().cases) >= 12)

# 2. A log-file-sync regression matches the golden Commit case
r1 = report(snap(120, [w("log file sync", "Commit", 15, 3)]),
            snap(600, [w("log file sync", "Commit", 72, 40)]))
m1 = dm.match(r1)
check("commit case matches history", m1["matched"] >= 1)
check("consensus = Commit", m1["consensus_root_cause"] == "Commit")
check("aligns with history", m1["aligns_with_history"] is True)
check("confidence boosted (>0)", m1["confidence_delta"] > 0)

# 3. Learning: record a brand-new live case, library grows
before = len(dm._get_store().cases)
dm.record_case(report(snap(120, [w("db file sequential read", "User I/O", 20, 4)]),
                       snap(700, [w("db file sequential read", "User I/O", 78, 18)])),
               db_name="PRODX")
check("library grows after record", len(dm._get_store().cases) == before + 1)

# 4. Self-audit drift: in an ISOLATED store, two CONFIRMED neighbours share the
#    live signature but their ground-truth root cause differs from the live verdict.
#    The engine must raise a silent drift flag and penalise confidence.
store = dm._get_store()
saved = list(store.cases)
io_sig_case = report(snap(120, [w("db file sequential read", "User I/O", 20, 4)]),
                     snap(700, [w("db file sequential read", "User I/O", 80, 18)]))
live_sig = dm.build_signature(io_sig_case)
store.cases = []
for i in range(2):
    c = dm._golden(live_sig["bottleneck"], live_sig["severity"], live_sig["dbt_bucket"],
                   live_sig["saturated"], live_sig["top_waits"], "CPU (masked saturation)")
    c["id"] = f"audit-{i}"; c["source"] = "live"
    store.cases.append(c)
m4 = dm.match(io_sig_case)
check("self-audit drift flag raised", bool(m4["drift_warning"]))
check("confidence penalised (<0)", m4["confidence_delta"] < 0)
store.cases = saved  # restore

# 5. Feedback loop: confirm a case
rec = dm.record_case(report(snap(120, [w("gc buffer busy acquire", "Cluster", 10, 5)]),
                            snap(650, [w("gc buffer busy acquire", "Cluster", 70, 28)])),
                     db_name="RAC1")
ok = dm.confirm_case(rec["id"], "Cluster")
check("feedback confirm_case works", ok)
check("confirmed flag persisted",
      any(c.get("id") == rec["id"] and c.get("confirmed") for c in store.cases))

# 6. Determinism: same input -> same signature hash
s_a = dm.build_signature(r1)["hash"]
s_b = dm.build_signature(report(snap(120, [w("log file sync", "Commit", 15, 3)]),
                                snap(600, [w("log file sync", "Commit", 72, 40)])))["hash"]
check("signature is deterministic", s_a == s_b)

# 7. Novelty: a never-seen pattern in an isolated store is flagged novel
store.cases = []  # empty library -> nothing can match
nov = dm.match(report(snap(120, [w("undocumented strange event", "Other", 20, 9)]),
                      snap(500, [w("undocumented strange event", "Other", 70, 30)])))
check("novel pattern flagged", nov["is_novel"] is True and bool(nov["novelty_reason"]))
store.cases = saved  # restore golden+learned

# 8. Stats expose coverage
st = dm.stats()
check("stats report library size", st.get("library_size", 0) >= 12)
check("stats list known classes", "Commit" in st.get("known_bottleneck_classes", []))

# 9. all_cases listing works
check("all_cases returns list", isinstance(dm.all_cases(limit=10), list))

# 10. Failure-proof: malformed report never raises
bad = dm.match({"not": "a report"})
check("malformed input safe", bad.get("matched") == 0 and bad.get("is_novel") in (True, False))

passed = sum(1 for _, o in results if o)
print(f"\nDIAGNOSTIC MEMORY: {passed}/{len(results)} checks passed")
if passed != len(results):
    sys.exit(1)
