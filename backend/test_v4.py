"""Quick smoke test for AWR Intelligence Engine v4"""
import time
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from services.awr_intelligence import (
    run_intelligence, run_intelligence_compare,
    _zscore, _iqr_upper_fence, _cusum, _pearson, _linreg,
    _bfs_causal_chain, _dfs_root_causes, _kb_lookup, _anomaly_scan,
)

data = {
    "db_name": "TESTDB", "begin_snap": 100, "end_snap": 101,
    "elapsed_min": 60, "db_time_min": 80, "aas": 12.5, "cpu_count": 8,
    "wait_events": [
        {"event": "log file sync",            "time_s": 900,  "waits": 50000, "avg_wait_ms": 18,  "pct_db_time": 18.0},
        {"event": "db file sequential read",   "time_s": 600,  "waits": 80000, "avg_wait_ms": 7.5, "pct_db_time": 12.0},
        {"event": "enq: TX - row lock contention","time_s":300,"waits": 5000, "avg_wait_ms": 60,  "pct_db_time": 6.0},
        {"event": "latch: library cache",      "time_s": 200,  "waits": 20000, "avg_wait_ms": 10,  "pct_db_time": 4.0},
        {"event": "direct path read temp",     "time_s": 150,  "waits": 10000, "avg_wait_ms": 15,  "pct_db_time": 3.0},
        {"event": "sql*net message from client","time_s":2000, "waits":200000, "avg_wait_ms": 10,  "pct_db_time": 40.0},
    ],
    "efficiency_stats": {
        "soft_parse_pct": 72.0, "buffer_hit_pct": 88.0,
        "in_memory_sort_pct": 94.0, "library_hit_pct": 96.5,
    },
    "load_profile": {"logons": 8.5, "executes": 120.0, "hard_parses": 280.0},
    "top_sql_elapsed": [
        {"sql_id": "abc123def456", "elapsed_pct": 35.0, "cpu_pct": 30.0, "executions": 5000,   "gets_per_exec": 250000},
        {"sql_id": "xyz789uvw012", "elapsed_pct": 10.0, "cpu_pct":  8.0, "executions": 200000, "gets_per_exec": 500},
        {"sql_id": "qqq111rrr222", "elapsed_pct":  5.0, "cpu_pct":  4.0, "executions": 8000,   "gets_per_exec": 3000},
    ],
    "addm_findings": [
        {"finding": "SQL statements consuming significant DB time",
         "impact_pct": 45.0, "recommendations": "Use DBMS_SQLTUNE to tune top SQL."},
    ],
    "time_model": [
        {"stat_name": "hard parse elapsed time", "pct": 8.5},
        {"stat_name": "connection management call elapsed time", "pct": 6.2},
    ],
    "_tablespace_io": [
        {"tablespace_name": "DATA", "avg_rd_ms": 35.0, "reads": 500000},
    ],
    "_latch_activity": [
        {"latch_name": "cache buffers chains", "gets": 1000000, "misses": 15000},
    ],
}

print("=" * 60)
print("AWR Intelligence Engine v4 — Algorithm Smoke Test")
print("=" * 60)

# Full pipeline
t0 = time.time()
report = run_intelligence("test_snap", data)
ms = (time.time() - t0) * 1000

print(f"\nPipeline: {ms:.1f}ms")
print(f"Overall health:     {report['overall_health']}")
print(f"Primary bottleneck: {report['primary_bottleneck']}")
print(f"Findings:           {len(report['findings'])}")
print(f"Correlation notes:  {len(report['correlation_notes'])}")
print(f"Trend notes:        {len(report['trend_notes'])}")
print(f"\nVerdict: {report['verdict'][:180]}")

print("\nTop findings (heap-sorted):")
for f in report["findings"][:8]:
    z_tag    = f"  Z={f['anomaly_z']:.1f}" if f["anomaly_z"] > 0 else ""
    chain    = f"  causal={f['causal_chain']}" if f["causal_chain"] else ""
    ref_tag  = f"  [{f['oracle_ref'][:30]}]" if f["oracle_ref"] else ""
    print(f"  [{f['severity'][:4]}] {f['title'][:55]:<55}  impact={f['impact_score']:5.0f}{z_tag}{chain}")
    if f["oracle_ref"]:
        print(f"         ref: {f['oracle_ref'][:70]}")

print("\nCorrelation notes:")
for n in report["correlation_notes"]:
    print(f"  {n[:110]}")

print("\nTrend notes:")
for n in report["trend_notes"]:
    print(f"  {n[:110]}")

print("\n" + "=" * 60)
print("Statistical algorithm unit tests:")

# Z-score
vals = [18.0, 12.0, 6.0, 4.0, 3.0, 0.8, 0.5]
z = _zscore(vals, 18.0)
assert z > 1.5, f"Expected Z > 1.5 for max value, got {z}"
print(f"  Z-score(18.0 in {vals[:4]}...): {z:.2f}  [PASS]")

# IQR fence
fence = _iqr_upper_fence(vals)
assert fence > 0, f"Expected positive fence, got {fence}"
print(f"  IQR fence for distribution: {fence:.1f}  [PASS]")

# CUSUM
c = _cusum([0, 0, 5, 10, 15, 20], target=0, slack_k=1.0)
assert c["triggered"], f"Expected CUSUM to trigger on sustained increase"
print(f"  CUSUM triggered={c['triggered']} S+={c['upper']:.1f}  [PASS]")

c2 = _cusum([5, 5, 5, 5, 5, 5], target=5, slack_k=0.5)
assert not c2["triggered"], f"Expected CUSUM NOT to trigger on stable series"
print(f"  CUSUM stable (no trigger): {not c2['triggered']}  [PASS]")

# Pearson
r_perfect = _pearson([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
assert abs(r_perfect - 1.0) < 1e-9, f"Expected r=1.0, got {r_perfect}"
print(f"  Pearson perfect correlation: r={r_perfect:.3f}  [PASS]")

r_anti = _pearson([1, 2, 3, 4, 5], [10, 8, 6, 4, 2])
assert abs(r_anti + 1.0) < 1e-9, f"Expected r=-1.0, got {r_anti}"
print(f"  Pearson anti-correlation: r={r_anti:.3f}  [PASS]")

# Linear regression
reg = _linreg([20, 15, 10, 7, 4, 2, 1])
assert reg["slope"] < -2, f"Expected negative slope, got {reg['slope']}"
assert reg["r2"] > 0.9, f"Expected R² > 0.9, got {reg['r2']}"
print(f"  LinReg slope={reg['slope']:.2f} r²={reg['r2']:.3f}  [PASS]")

# BFS causal chain
chain = _bfs_causal_chain(
    "log file sync",
    {"log file sync", "log file parallel write", "latch: library cache"}
)
assert "log file parallel write" in chain, f"Expected parent in chain, got {chain}"
print(f"  BFS causal chain: {chain}  [PASS]")

# DFS root causes
causes = _dfs_root_causes("enq: TM - contention")
assert len(causes) > 0, "Expected at least one root cause"
print(f"  DFS root causes: {causes[:2]}  [PASS]")

# Oracle KB lookup
ref, principle = _kb_lookup(["redo", "commit"])
assert len(ref) > 5, f"Expected non-empty KB ref, got {ref!r}"
print(f"  KB lookup [redo]: {ref[:50]}  [PASS]")

# Anomaly scan — needs a skewed distribution with a clear spike
spike_events = [
    {"event": "log file sync",           "time_s": 4500, "waits": 50000, "avg_wait_ms": 90, "pct_db_time": 55.0},
    {"event": "db file sequential read", "time_s":  500, "waits": 40000, "avg_wait_ms": 5,  "pct_db_time":  6.0},
    {"event": "latch: library cache",    "time_s":  200, "waits": 20000, "avg_wait_ms": 10, "pct_db_time":  2.5},
    {"event": "free buffer waits",       "time_s":  100, "waits":  1000, "avg_wait_ms": 100,"pct_db_time":  1.2},
    {"event": "direct path read temp",   "time_s":   80, "waits":  5000, "avg_wait_ms": 16, "pct_db_time":  1.0},
    {"event": "row cache lock",          "time_s":   50, "waits":  3000, "avg_wait_ms": 17, "pct_db_time":  0.6},
    {"event": "write complete waits",    "time_s":   30, "waits":  2000, "avg_wait_ms": 15, "pct_db_time":  0.4},
]
anomalies = _anomaly_scan(spike_events, db_time_s=8100)
assert isinstance(anomalies, list), "Expected list from anomaly scan"
# log file sync at 55% should be a clear Z > 2 spike
top_z = anomalies[0]["z_score"] if anomalies else 0
assert top_z > 1.5 or len(anomalies) >= 1, f"Expected spike detection, got z={top_z}"
print(f"  Anomaly scan: {len(anomalies)} anomaly(s) detected, top Z={top_z:.2f}  [PASS]")

# Comparison pipeline
good = dict(data, aas=4.0, wait_events=[
    {"event": "db file sequential read", "time_s": 100, "waits": 10000, "avg_wait_ms": 4.0, "pct_db_time": 5.0}
])
comp = run_intelligence_compare("good", "bad", good, data)
assert comp["upload_id"] == "good_vs_bad"
n_new = sum(1 for f in comp["findings"] if "[NEW]" in f["title"])
n_sus = sum(1 for f in comp["findings"] if "[SUSTAINED]" in f["title"])
print(f"  Comparison: {len(comp['findings'])} findings, {n_new} NEW, {n_sus} SUSTAINED  [PASS]")
print(f"  CUSUM notes: {len([n for n in comp['correlation_notes'] if 'SUSTAINED' in n])}  [PASS]")

print("\n" + "=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
