"""
Reverse-engineering benchmark: 100 known-answer good->bad AWR comparison cases.

We KNOW the correct Oracle root cause for each case (built from canonical wait-event
taxonomy). We feed each pair blind through the real engines (comparator.compare_periods,
rca_engine.run_comparison_rca, awr_intelligence_v4.run_intelligence_compare) and score
how often the tool's verdict agrees with the known answer. Contradictions reveal where
the wiring is disturbed.

Run:  python tests/test_known_answer_benchmark.py
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from models.snapshot import AWRData
from services.comparator import compare_periods
from services.rca_engine import run_comparison_rca
from services import awr_intelligence_v4 as intel

EFF_AVAIL = ["buffer_cache_hit_pct", "library_cache_hit_pct", "soft_parse_pct",
             "execute_to_parse_pct", "latch_hit_pct"]


def _eff(buf=99.0, lib=99.0, soft=98.0, e2p=95.0, latch=99.9):
    return {"buffer_cache_hit_pct": buf, "library_cache_hit_pct": lib,
            "soft_parse_pct": soft, "execute_to_parse_pct": e2p, "latch_hit_pct": latch}


def _wait(name, cls, secs, pct, avg_ms, total=100000, cat=""):
    return {"event_name": name, "wait_class": cls, "wait_class_category": cat,
            "time_waited_secs": secs, "pct_db_time": pct, "avg_wait_ms": avg_ms,
            "total_waits": total}


def _snap(db_time_min, waits, eff=None, cpus=16, sql=None, lp=None, txn=200.0):
    return AWRData(
        db_name="ORCL", instance="orcl1", release="19.0.0.0", cpus=cpus, memory_gb=128,
        begin_snap=100, end_snap=101, elapsed_min=60.0, db_time_min=db_time_min,
        load_profile=lp or [{"stat_name": "Transactions", "per_sec": txn},
                            {"stat_name": "DB Time", "per_sec": db_time_min/60.0}],
        efficiency=eff or _eff(), efficiency_available=EFF_AVAIL,
        wait_events=waits, sql_stats=sql or [],
    ).model_dump()


# ---- Canonical bottleneck profiles: (event, wait_class, expected_class) ----
PROFILES = {
    "CPU":        ("CPU", "CPU time",     "CPU"),
    "USER_IO":    ("db file sequential read", "User I/O", "I/O"),
    "SYS_IO":     ("db file scattered read",  "User I/O", "I/O"),
    "DIRECT_IO":  ("direct path read",        "User I/O", "I/O"),
    "COMMIT":     ("log file sync",       "Commit",       "Commit"),
    "BUF_BUSY":   ("buffer busy waits",   "Concurrency",  "Concurrency"),
    "LIB_LOCK":   ("library cache lock",  "Concurrency",  "Concurrency"),
    "LATCH":      ("latch: shared pool",  "Concurrency",  "Concurrency"),
    "ROW_LOCK":   ("enq: TX - row lock contention", "Application", "Concurrency"),
    "CLUSTER":    ("gc buffer busy acquire", "Cluster",   "Cluster"),
    "NETWORK":    ("SQL*Net more data to client", "Network", "Network"),
}

# comparator._classify_bottleneck now covers all six classes (fix verified by this run).
TOOL_BUCKET = {"CPU": "CPU", "I/O": "I/O", "Concurrency": "Concurrency",
               "Commit": "Commit", "Cluster": "Cluster", "Network": "Network"}


def build_corpus():
    cases = []
    # 11 bottleneck classes x ~8 variations = 88 + 12 controls = 100
    for key, (ev, cls, expected) in PROFILES.items():
        for i in range(8):
            sev = 60 + i * 5            # bad DB time pct on the event
            good = _snap(120, [_wait(ev, cls, 200, 10, 5)])
            bad = _snap(120 + 40 + i * 8,
                        [_wait(ev, cls, 3000 + i * 200, sev, 12 + i)], eff=_eff(buf=85, soft=70))
            cases.append({"id": f"{key}_{i}", "expected": expected, "event": ev,
                          "good": good, "bad": bad, "kind": "regression"})
    # 12 control cases: no regression (healthy stays healthy)
    for i in range(12):
        good = _snap(110, [_wait("db file sequential read", "User I/O", 200, 12, 5)])
        bad = _snap(112, [_wait("db file sequential read", "User I/O", 210, 12, 5)])
        cases.append({"id": f"HEALTHY_{i}", "expected": "I/O", "event": "db file sequential read",
                      "good": good, "bad": bad, "kind": "healthy"})
    return cases


def run():
    cases = build_corpus()
    ideal_hits = tool_hits = sev_hits = 0
    contradictions = []
    bucket_gap = []
    for c in cases:
        rep = compare_periods(c["good"], c["bad"]).model_dump()
        summ = rep["summary"]
        bad_b = summ.get("bad_bottleneck", "?")
        sev = summ.get("severity", "?")
        try:
            ic = intel.run_intelligence_compare("g", "b", c["good"], c["bad"])
            prim = ic.get("primary_bottleneck", "?")
        except Exception as e:
            prim = f"ERR:{e}"
        exp = c["expected"]
        tool_ok = bad_b == TOOL_BUCKET.get(exp, exp)
        ideal_ok = bad_b == exp
        if ideal_ok: ideal_hits += 1
        if tool_ok: tool_hits += 1
        if c["kind"] == "regression" and sev in ("degraded", "critical"): sev_hits += 1
        if c["kind"] == "healthy" and sev == "healthy": sev_hits += 1
        if not ideal_ok:
            contradictions.append((c["id"], exp, bad_b, prim))
            if TOOL_BUCKET.get(exp) == "Mixed":
                bucket_gap.append(c["id"])
    n = len(cases)
    print(f"\n=== AWR 100-CASE KNOWN-ANSWER BENCHMARK (n={n}) ===")
    print(f"Ideal bottleneck match (exact Oracle class): {ideal_hits}/{n}")
    print(f"Tool-design match (CPU/IO/Conc taxonomy):    {tool_hits}/{n}")
    print(f"Severity correct:                            {sev_hits}/{n}")
    print(f"Mixed-bucket taxonomy gap (Commit/Cluster/Net): {len(bucket_gap)}")
    print("\nFirst contradictions vs ideal (id, expected, tool_class, intel_primary):")
    for row in contradictions[:15]:
        print("  ", row)
    return ideal_hits, tool_hits, sev_hits, n


if __name__ == "__main__":
    run()
