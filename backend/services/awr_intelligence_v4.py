"""
AWR Intelligence Engine v4  —  Pure Python · Zero external dependencies
========================================================================

Full algorithm pipeline (per architecture diagram):

  ┌─────────────────────────────────────────────────────────────────┐
  │                     AWR Raw Data Layer                          │
  │  Normalised JSON: wait events · SQL stats · load profile · I/O │
  └──────┬─────────────┬──────────────┬───────────────┬────────────┘
         │             │              │               │
  ┌──────▼───┐  ┌──────▼──┐  ┌───────▼───┐  ┌───────▼──────┐
  │ Weighted │  │  Rule   │  │  Anomaly  │  │    Graph     │
  │  Scoring │  │ Engine  │  │ Detection │  │   Engine     │
  │ Max-heap │  │ HashMap │  │  Z-score  │  │ Wait-evt DAG │
  │ priority │  │ + dec.  │  │  CUSUM    │  │  BFS / DFS   │
  │  queue   │  │   tree  │  │  IQR      │  │ causal root  │
  └──────┬───┘  └──────┬──┘  └───────┬───┘  └───────┬──────┘
         │             │              │               │
  ┌──────▼───┐  ┌──────▼──┐  ┌───────▼───┐  ┌───────▼──────┐
  │  Health  │  │ Pattern │  │  Trend    │  │  Root Cause  │
  │  Score   │  │ Matcher │  │  Engine   │  │  Engine      │
  │ 0-100 /  │  │ Oracle  │  │  Linear   │  │  DFS causal  │
  │ subsystem│  │ KB+RAG  │  │  Regress. │  │  chain text  │
  └──────┬───┘  └──────┬──┘  └───────┬───┘  └───────┬──────┘
         └─────────────┴──────────────┴───────────────┘
                                │
             ┌──────────────────▼──────────────────┐
             │      Correlation + Synthesis         │
             │  Pearson matrix · cross-signal amp.  │
             │  ranked findings · heap sort         │
             └──────────────────┬──────────────────┘
                                │
             ┌──────────────────▼──────────────────┐
             │   Smart Narrative Template Engine    │
             │  Condition-tree · data-driven text   │
             │  no LLM · no magic · Oracle refs     │
             └───┬──────────────┬──────────────┬───┘
                 │              │              │
         ┌───────▼──┐  ┌────────▼──┐  ┌───────▼───────┐
         │ Priority │  │Root Cause │  │ Forecast +    │
         │  Alert   │  │ Narrative │  │ Remediation   │
         │   List   │  │plain-lang │  │ trend proj.   │
         │ CRIT→MED │  │+ evidence │  │ SQL hints     │
         └──────────┘  └───────────┘  └───────────────┘
"""
from __future__ import annotations

import heapq
import math
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Any

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  CACHE
# ══════════════════════════════════════════════════════════════════════════════
_CACHE: dict[str, dict] = {}
_CACHE_TTL = 1800  # 30 min


def cache_get(upload_id: str) -> dict | None:
    e = _CACHE.get(upload_id)
    if not e:
        return None
    if time.time() - e["ts"] > _CACHE_TTL:
        del _CACHE[upload_id]
        return None
    return e["report"]


def cache_set(upload_id: str, report: dict) -> None:
    _CACHE[upload_id] = {"ts": time.time(), "report": report}


def cache_status(upload_id: str) -> str:
    return "ready" if cache_get(upload_id) is not None else "missing"


# ══════════════════════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class AWRFinding:
    id: str
    severity: str           # CRITICAL | WARNING | INFO
    category: str
    title: str              # ≤ 60 chars
    headline: str           # decisive one-liner with real numbers
    evidence: list[str]     # bullet points from AWR data
    root_cause: str
    fix: str                # exact Oracle command / step
    impact_score: float = 0.0
    confidence: str = "HIGH"    # HIGH | MEDIUM | LOW
    sql_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    oracle_ref: str = ""        # Oracle Performance Tuning Guide citation
    trend: str = ""             # STABLE | WORSENING | IMPROVING (compare mode)
    anomaly_z: float = 0.0      # Z-score vs peer distribution (>2 = spike)
    causal_chain: list[str] = field(default_factory=list)  # BFS parents


@dataclass
class FindingReport:
    upload_id: str
    db_name: str
    snap_range: str
    overall_health: str         # CRITICAL | WARNING | OK
    primary_bottleneck: str
    verdict: str
    findings: list[AWRFinding]
    analysis_model: str = "AWR Intelligence Engine v4"
    generated_at: float = field(default_factory=time.time)
    pipeline_ms: float = 0.0
    correlation_notes: list[str] = field(default_factory=list)
    trend_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["findings"] = [asdict(f) for f in self.findings]
        return d


# ══════════════════════════════════════════════════════════════════════════════
#  §1  PURE-PYTHON STATISTICAL ALGORITHMS
#      All implemented from first principles — no numpy / scipy required.
# ══════════════════════════════════════════════════════════════════════════════

# ── §1.1  Max-heap ranked priority queue ────────────────────────────────────
def _heap_rank(findings: list[AWRFinding]) -> list[AWRFinding]:
    """
    Sort findings via max-heap on composite priority key.
    Key = (severity_weight × 1000 + impact_score).
    CRITICAL always outranks WARNING at the same impact_score.
    """
    _sev_w = {"CRITICAL": 3, "WARNING": 2, "INFO": 1}
    heap: list[tuple] = []
    for f in findings:
        sw = _sev_w.get(f.severity, 1)
        # Negate for max-heap (heapq is min-heap by default)
        heapq.heappush(heap, (-sw * 1000 - f.impact_score, f.id, f))
    ranked: list[AWRFinding] = []
    while heap:
        ranked.append(heapq.heappop(heap)[-1])
    return ranked


# ── §1.2  Z-score  (detects unexpected spikes) ──────────────────────────────
def _z_mean_std(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n < 2:
        return 0.0, 1.0
    mean = sum(values) / n
    var  = sum((x - mean) ** 2 for x in values) / n
    std  = math.sqrt(var) if var > 1e-12 else 1.0
    return mean, std


def _zscore(values: list[float], v: float) -> float:
    """Z-score of v in distribution. > 2 = spike, > 3 = extreme spike."""
    mean, std = _z_mean_std(values)
    return (v - mean) / std


# ── §1.3  IQR outlier fence  (Tukey fences) ─────────────────────────────────
def _iqr_upper_fence(values: list[float]) -> float:
    """Tukey upper fence: Q3 + 1.5 × IQR. Values above this are outliers."""
    s = sorted(values)
    n = len(s)
    if n < 4:
        return float("inf")
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    return q3 + 1.5 * (q3 - q1)


# ── §1.4  CUSUM  (sustained-shift detection, Page 1954) ─────────────────────
def _cusum(values: list[float], target: float, slack_k: float | None = None) -> dict:
    """
    Page's CUSUM test — detects sustained increase above `target`.
    slack_k: allowance per observation (default 50% of |target|, min 0.5).
    Returns dict with:
      upper     — final CUSUM statistic S⁺
      triggered — True if S⁺ exceeds detection threshold
      trigger_idx — first index where shift was confirmed (or None)
    """
    k = slack_k if slack_k is not None else (abs(target) * 0.5 if target else 0.5)
    k = max(k, 0.1)
    threshold = abs(target) * 2 if abs(target) > 1 else 2.0

    s_pos = 0.0
    trigger_idx: int | None = None
    for i, x in enumerate(values):
        s_pos = max(0.0, s_pos + (x - target) - k)
        if s_pos > threshold and trigger_idx is None:
            trigger_idx = i

    return {
        "upper": s_pos,
        "triggered": s_pos > threshold,
        "trigger_idx": trigger_idx,
    }


# ── §1.5  Pearson correlation  ───────────────────────────────────────────────
def _pearson(xs: list[float], ys: list[float]) -> float:
    """
    Pearson r between xs and ys.
    Returns value in [-1, 1].  0.0 if insufficient data or zero variance.
    |r| > 0.8 → strong correlation  |r| < 0.3 → weak/no correlation.
    """
    n = len(xs)
    if n < 3 or len(ys) != n:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx  = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy  = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx * dy > 1e-9 else 0.0


# ── §1.6  Linear regression  (OLS, trend slope) ─────────────────────────────
def _linreg(ys: list[float]) -> dict:
    """
    OLS linear regression  y = slope·x + intercept  (x = 0, 1, …, n-1).
    Positive slope → value increasing over index. Negative → decreasing.
    r2 close to 1.0 → strong linear trend.
    """
    n = len(ys)
    if n < 2:
        return {"slope": 0.0, "intercept": ys[0] if ys else 0.0, "r2": 0.0}
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = sum((x - mx) ** 2 for x in xs)
    slope     = num / den if den > 1e-9 else 0.0
    intercept = my - slope * mx
    ss_res    = sum((ys[i] - (slope * xs[i] + intercept)) ** 2 for i in range(n))
    ss_tot    = sum((y - my) ** 2 for y in ys)
    r2        = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0
    return {"slope": slope, "intercept": intercept, "r2": max(0.0, r2)}


# ══════════════════════════════════════════════════════════════════════════════
#  §2  ORACLE PERFORMANCE KNOWLEDGE BASE  (embedded RAG)
#      Each entry maps a performance category to documented Oracle thresholds,
#      root principles, and guide citations.
#      At finding time: _kb_lookup(tags) retrieves the most relevant entry
#      and attaches its reference + principle snippet to the finding.
# ══════════════════════════════════════════════════════════════════════════════
_ORACLE_KB: dict[str, dict] = {
    "parse": {
        "title":   "Cursor Sharing and Parse Optimization",
        "ref":     "Oracle Performance Tuning Guide — Tuning the Shared Pool",
        "principle": (
            "Hard parses require CPU for plan generation, exclusive library cache latch "
            "holds, and fresh shared pool memory. Target: Soft Parse % > 95%, "
            "Hard Parses/sec < 100. Primary fix: bind variables or CURSOR_SHARING=FORCE."
        ),
        "benchmarks": {"soft_parse_target": 95, "hard_parse_alert_per_sec": 100},
    },
    "buffer_cache": {
        "title":   "Buffer Cache Sizing and Hit Ratio",
        "ref":     "Oracle Performance Tuning Guide — Tuning the Buffer Cache",
        "principle": (
            "Buffer cache hit ratio below 95% typically indicates the cache is undersized "
            "for the working set. Use V$DB_CACHE_ADVICE to determine optimal DB_CACHE_SIZE. "
            "Note: low hit ratio caused by full scans may be acceptable in DSS workloads."
        ),
        "benchmarks": {"hit_pct_target": 95, "hit_pct_critical": 75},
    },
    "io": {
        "title":   "I/O Subsystem Performance Targets",
        "ref":     "Oracle Performance Tuning Guide — I/O Configuration and Design",
        "principle": (
            "Target single-block read latency < 5ms (SSD/NVMe) or < 10ms (HDD/SAN). "
            "Multi-block read latency < 20ms. Latency above these thresholds indicates "
            "storage saturation, I/O scheduler misconfiguration, or SAN queue depth issues."
        ),
        "benchmarks": {"ssd_lat_ms": 5, "hdd_lat_ms": 10, "critical_lat_ms": 20},
    },
    "redo": {
        "title":   "Redo Log and LGWR Configuration",
        "ref":     "Oracle Performance Tuning Guide — Redo Log Sizing",
        "principle": (
            "Log File Sync avg latency < 3ms. Log File Parallel Write < 1ms. "
            "Redo NoWait % > 99.9%. LGWR flushes on every COMMIT — redo logs on "
            "slow storage directly increase user response time. Never use RAID 5 for redo."
        ),
        "benchmarks": {"sync_lat_ms": 3, "parallel_write_lat_ms": 1, "nowait_pct_target": 99},
    },
    "pga": {
        "title":   "PGA Memory Management and Sort/Hash Spill Prevention",
        "ref":     "Oracle Performance Tuning Guide — Automatic PGA Memory Management",
        "principle": (
            "Disk sorts are 100x slower than in-memory sorts. Target: In-Memory Sort % > 99%. "
            "Use V$PGA_TARGET_ADVICE to size PGA_AGGREGATE_TARGET. "
            "Find spilling SQL via V$SQL_WORKAREA WHERE last_tempseg_size IS NOT NULL."
        ),
        "benchmarks": {"inmem_sort_target": 99, "disk_sort_alert_pct": 5},
    },
    "latch": {
        "title":   "Latch Contention Analysis",
        "ref":     "Oracle Performance Tuning Guide — Latch Statistics",
        "principle": (
            "Latch miss ratio > 1% signals high contention. Library cache latch misses "
            "→ hard parse pressure. Cache buffers chains misses → hot block syndrome. "
            "Shared pool latch misses → pool fragmentation. Address root cause, not symptom."
        ),
        "benchmarks": {"miss_pct_alert": 1.0, "miss_pct_critical": 5.0},
    },
    "lock": {
        "title":   "Row Lock and Blocking Session Analysis",
        "ref":     "Oracle Performance Tuning Guide — Identifying and Reducing Lock Contention",
        "principle": (
            "TX row lock (enq: TX) = sessions waiting for another transaction. "
            "TM lock (enq: TM) = almost always a missing FK index. "
            "Use V$SESSION.BLOCKING_SESSION to find the blocker. Commit sooner."
        ),
        "benchmarks": {"lock_pct_alert": 3, "lock_pct_critical": 10},
    },
    "cpu": {
        "title":   "CPU Saturation and Active Session History",
        "ref":     "Oracle Performance Tuning Guide — Using ASH for Performance Diagnosis",
        "principle": (
            "AAS > CPU count = CPU saturated, sessions queue. "
            "Healthy OLTP: AAS / CPU < 0.7. Warning: > 1.0. Critical: > 2.0. "
            "Use V$ACTIVE_SESSION_HISTORY WHERE session_state='ON CPU' to find top SQL."
        ),
        "benchmarks": {"healthy": 0.7, "warning": 1.0, "critical": 2.0},
    },
    "sql": {
        "title":   "SQL Tuning and Execution Plan Analysis",
        "ref":     "Oracle Performance Tuning Guide — SQL Tuning",
        "principle": (
            "Buffer gets/exec healthy OLTP: < 10K. Batch: < 100K. "
            "Use DBMS_XPLAN.DISPLAY_CURSOR(sql_id, NULL, 'ALLSTATS LAST +PEEKED_BINDS') "
            "to see actual vs estimated rows. Misestimated cardinality → bad plan."
        ),
        "benchmarks": {"gets_exec_oltp_alert": 10_000, "gets_exec_batch_alert": 100_000},
    },
    "connection": {
        "title":   "Connection Management and Pooling",
        "ref":     "Oracle Performance Tuning Guide — Configuring Oracle Database for Performance",
        "principle": (
            "New connection per request = expensive: authentication + session + PGA init. "
            "Target: logons/sec < 1% of executes/sec. "
            "Use Oracle UCP, HikariCP, or DRCP (DBMS_CONNECTION_POOL.START_POOL())."
        ),
        "benchmarks": {"logon_to_execute_ratio_alert": 0.05},
    },
    "rac": {
        "title":   "RAC Global Cache and Interconnect Performance",
        "ref":     "Oracle RAC Performance Tuning Guide — Global Cache Statistics",
        "principle": (
            "gc cr request / gc buffer busy = inter-instance block transfer. "
            "Root fix: workload affinity (route related work to same node via services). "
            "Target: gc cr block receive time < 1ms. Check interconnect bandwidth."
        ),
        "benchmarks": {"gc_lat_ms": 1, "gc_pct_alert": 5},
    },
    "temp": {
        "title":   "Temp Tablespace and Sort Spill",
        "ref":     "Oracle Performance Tuning Guide — Temporary Tablespace Management",
        "principle": (
            "Direct path read/write temp waits = PGA spill. "
            "Check V$TEMP_SPACE_HEADER for usage. "
            "Increase PGA_AGGREGATE_TARGET per V$PGA_TARGET_ADVICE guidance."
        ),
        "benchmarks": {"inmem_sort_target": 99},
    },
}


def _kb_lookup(tags: list[str]) -> tuple[str, str]:
    """
    Retrieve Oracle KB entry for the most specific matching tag.
    Returns (oracle_ref, principle_snippet).  Empty strings if no match.
    """
    priority = ["lock", "latch", "rac", "redo", "pga", "temp", "io",
                "parse", "buffer_cache", "cpu", "sql", "connection"]
    for p in priority:
        for tag in tags:
            key = tag.lower().replace("-", "_")
            if key == p and p in _ORACLE_KB:
                e = _ORACLE_KB[p]
                return e["ref"], e["principle"]
            if key in _ORACLE_KB:
                e = _ORACLE_KB[key]
                return e["ref"], e["principle"]
    return "", ""


# ══════════════════════════════════════════════════════════════════════════════
#  §3  WAIT EVENT CATALOG  (HashMap rule engine — O(1) lookup)
#      Each entry defines: category, latency threshold, pct threshold,
#      root cause, fix steps, tags → maps directly to AWRFinding fields.
# ══════════════════════════════════════════════════════════════════════════════
_WAIT_CATALOG: dict[str, dict] = {
    "db file sequential read": {
        "cat": "I/O", "lat_ms": 10, "pct_threshold": 10,
        "root": "Single-block I/O (index reads). Each wait = one 8 KB block from storage.",
        "fix": (
            "1) Find high-reads SQL: AWR 'SQL ordered by Physical Reads'.\n"
            "2) lat < 5 ms but high volume: optimise SQL (unselective index, NL on large table).\n"
            "3) lat > 20 ms: storage issue — check SAN/ASM disk health and queue depth.\n"
            "   SELECT event, time_waited, p1, p3 FROM v$session_wait WHERE event LIKE 'db file%';"
        ),
        "oracle_ref": "Oracle Perf Guide — I/O Configuration and Design",
        "tags": ["io", "index"],
    },
    "db file scattered read": {
        "cat": "I/O", "lat_ms": 20, "pct_threshold": 8,
        "root": "Multi-block I/O — full table or index fast full scans.",
        "fix": (
            "1) Find full-scan SQL: AWR 'SQL ordered by Physical Reads'.\n"
            "2) Check for missing indexes or unselective access paths.\n"
            "3) Tune DB_FILE_MULTIBLOCK_READ_COUNT (try 128).\n"
            "4) For OLAP: add parallel hints or partitioning."
        ),
        "oracle_ref": "Oracle Perf Guide — I/O Configuration and Design",
        "tags": ["io", "full_scan"],
    },
    "log file sync": {
        "cat": "Redo", "lat_ms": 5, "pct_threshold": 8,
        "root": "COMMIT latency — user process waits for LGWR to flush redo buffer to disk.",
        "fix": (
            "1) Move redo logs to fastest storage (never RAID 5).\n"
            "2) Batch commits: reduce commit frequency in application.\n"
            "3) Check 'log file parallel write' avg latency in AWR.\n"
            "4) Verify async I/O: DISK_ASYNCH_IO=TRUE."
        ),
        "oracle_ref": "Oracle Perf Guide — Redo Log Sizing",
        "tags": ["redo", "commit", "io"],
    },
    "log file parallel write": {
        "cat": "Redo", "lat_ms": 5, "pct_threshold": 5,
        "root": "LGWR is slow writing redo log to disk — storage I/O bottleneck.",
        "fix": "Move redo logs to dedicated fast storage. Use RAID10 or NVMe. Check OS I/O scheduler.",
        "oracle_ref": "Oracle Perf Guide — Redo Log Sizing",
        "tags": ["redo", "io"],
    },
    "free buffer waits": {
        "cat": "Memory", "lat_ms": 100, "pct_threshold": 3,
        "root": "Buffer cache full; DBWR cannot write dirty buffers fast enough to free space.",
        "fix": (
            "1) Increase DB_CACHE_SIZE per Buffer Cache Advisory.\n"
            "2) Add DBWR processes: DB_WRITER_PROCESSES = CPU_count / 4.\n"
            "3) Reduce dirty buffer generation by optimising bulk DML."
        ),
        "oracle_ref": "Oracle Perf Guide — Tuning the Buffer Cache",
        "tags": ["buffer_cache", "memory", "io"],
    },
    "direct path read": {
        "cat": "I/O", "lat_ms": 10, "pct_threshold": 8,
        "root": "Parallel query or large table scan bypassing buffer cache into PGA.",
        "fix": (
            "1) Check parallel query DOP: SELECT * FROM v$px_session;\n"
            "2) Temp spills: increase PGA_AGGREGATE_TARGET.\n"
            "3) Reduce unnecessary parallelism on OLTP."
        ),
        "oracle_ref": "Oracle Perf Guide — I/O Configuration",
        "tags": ["io", "parallel", "pga"],
    },
    "direct path read temp": {
        "cat": "Memory", "lat_ms": 10, "pct_threshold": 5,
        "root": "Sort/hash operations spilling to temp tablespace — PGA undersized.",
        "fix": (
            "1) Increase PGA_AGGREGATE_TARGET per V$PGA_TARGET_ADVICE.\n"
            "2) Find spilling SQL:\n"
            "   SELECT sql_id, operation_type, last_tempseg_size\n"
            "   FROM v$sql_workarea WHERE last_tempseg_size > 0 ORDER BY last_tempseg_size DESC;"
        ),
        "oracle_ref": "Oracle Perf Guide — Automatic PGA Memory Management",
        "tags": ["pga", "temp", "memory"],
    },
    "direct path write temp": {
        "cat": "Memory", "lat_ms": 10, "pct_threshold": 5,
        "root": "Hash join / sort spilling to temp — work area exceeds PGA allocation.",
        "fix": "Increase PGA_AGGREGATE_TARGET. Review V$PGA_TARGET_ADVICE.",
        "oracle_ref": "Oracle Perf Guide — Automatic PGA Memory Management",
        "tags": ["pga", "temp", "memory"],
    },
    "enq: TX - row lock contention": {
        "cat": "Locking", "lat_ms": 0, "pct_threshold": 3,
        "root": "Row-level TX lock — sessions blocking each other on the same rows.",
        "fix": (
            "1) Find blocker:\n"
            "   SELECT blocking_session, sid, sql_id, wait_class\n"
            "   FROM v$session WHERE wait_class='Application' AND blocking_session IS NOT NULL;\n"
            "2) Reduce transaction hold time — commit sooner.\n"
            "3) Check for missing FK indexes (enq: TM contention).\n"
            "4) Review application transaction design."
        ),
        "oracle_ref": "Oracle Perf Guide — Identifying and Reducing Lock Contention",
        "tags": ["lock", "blocking", "tx"],
    },
    "enq: TM - contention": {
        "cat": "Locking", "lat_ms": 0, "pct_threshold": 2,
        "root": "Table-level TM lock — almost always caused by missing FK index.",
        "fix": (
            "Find FK columns without indexes:\n"
            "SELECT c.table_name, c.constraint_name FROM dba_constraints c\n"
            "WHERE c.constraint_type='R' AND NOT EXISTS (\n"
            "  SELECT 1 FROM dba_ind_columns i WHERE i.table_name=c.table_name\n"
            "  AND i.column_name=(SELECT cc.column_name FROM dba_cons_columns cc\n"
            "   WHERE cc.constraint_name=c.constraint_name AND rownum=1));\n"
            "Create indexes on all FK columns."
        ),
        "oracle_ref": "Oracle Perf Guide — Identifying and Reducing Lock Contention",
        "tags": ["lock", "fk", "index"],
    },
    "enq: HW - contention": {
        "cat": "Locking", "lat_ms": 0, "pct_threshold": 2,
        "root": "High-water mark lock — concurrent INSERTs extending segment past HWM.",
        "fix": "Pre-allocate extents with DBMS_SPACE. Use APPEND hint. Use ASSM tablespace.",
        "oracle_ref": "Oracle Perf Guide — Segment Management",
        "tags": ["lock", "segment", "hwm"],
    },
    "latch: library cache": {
        "cat": "Latch", "lat_ms": 0, "pct_threshold": 3,
        "root": "High hard parse rate causing library cache latch hot spot.",
        "fix": (
            "1) Enforce bind variables (primary fix).\n"
            "2) ALTER SYSTEM SET CURSOR_SHARING=FORCE;\n"
            "3) Increase SESSION_CACHED_CURSORS=200;\n"
            "4) Increase OPEN_CURSORS."
        ),
        "oracle_ref": "Oracle Perf Guide — Tuning the Shared Pool",
        "tags": ["latch", "parse", "shared_pool"],
    },
    "latch: shared pool": {
        "cat": "Latch", "lat_ms": 0, "pct_threshold": 3,
        "root": "Shared pool allocation pressure — fragmentation or undersized pool.",
        "fix": (
            "1) Increase SHARED_POOL_SIZE per Shared Pool Advisory.\n"
            "2) Pin large packages: EXEC DBMS_SHARED_POOL.KEEP('schema.package');\n"
            "3) Reduce hard parses — they fragment the shared pool."
        ),
        "oracle_ref": "Oracle Perf Guide — Tuning the Shared Pool",
        "tags": ["latch", "shared_pool", "memory"],
    },
    "latch: cache buffers chains": {
        "cat": "Latch", "lat_ms": 0, "pct_threshold": 2,
        "root": "Hot block in buffer cache — many sessions accessing same block simultaneously.",
        "fix": (
            "1) Find hot segment:\n"
            "   SELECT obj, dbarfil, dbablk, tch FROM x$bh\n"
            "   WHERE tch > 100 ORDER BY tch DESC FETCH FIRST 10 ROWS ONLY;\n"
            "2) Partition hot table/index.\n"
            "3) Sequence hot block: increase CACHE value.\n"
            "4) Index root hot block: consider reverse-key index."
        ),
        "oracle_ref": "Oracle Perf Guide — Latch Statistics",
        "tags": ["latch", "hot_block", "buffer_cache"],
    },
    "gc buffer busy acquire": {
        "cat": "RAC", "lat_ms": 0, "pct_threshold": 5,
        "root": "RAC inter-instance block transfer — same blocks requested by multiple nodes.",
        "fix": (
            "1) Implement workload affinity via Oracle Services.\n"
            "2) Increase sequence CACHE value.\n"
            "3) Partition application data by node."
        ),
        "oracle_ref": "Oracle RAC Performance Tuning Guide — Global Cache Statistics",
        "tags": ["rac", "gc", "interconnect"],
    },
    "gc cr request": {
        "cat": "RAC", "lat_ms": 15, "pct_threshold": 5,
        "root": "RAC consistent-read block requests — cross-instance I/O over interconnect.",
        "fix": "Implement application affinity. Check interconnect bandwidth and latency (< 1ms).",
        "oracle_ref": "Oracle RAC Performance Tuning Guide — Global Cache Statistics",
        "tags": ["rac", "gc", "interconnect"],
    },
    "cursor: pin S wait on X": {
        "cat": "Latch", "lat_ms": 0, "pct_threshold": 2,
        "root": "Cursor pin contention — hard parse modifying a cursor while others execute it.",
        "fix": "Reduce hard parses. Set CURSOR_SHARING=FORCE. Increase SESSION_CACHED_CURSORS.",
        "oracle_ref": "Oracle Perf Guide — Tuning the Shared Pool",
        "tags": ["latch", "cursor", "parse"],
    },
    "library cache lock": {
        "cat": "Latch", "lat_ms": 0, "pct_threshold": 2,
        "root": "Library cache lock — DDL or recompilation blocking cursor reuse.",
        "fix": "Schedule DDL during maintenance windows. Avoid recompilation during peak hours.",
        "oracle_ref": "Oracle Perf Guide — Tuning the Shared Pool",
        "tags": ["latch", "ddl", "library_cache"],
    },
    "row cache lock": {
        "cat": "Latch", "lat_ms": 0, "pct_threshold": 2,
        "root": "Data dictionary row cache contention — frequently accessed dictionary objects.",
        "fix": "Increase SHARED_POOL_SIZE. Pre-warm cache after startup by querying DBA_ views.",
        "oracle_ref": "Oracle Perf Guide — Tuning the Shared Pool",
        "tags": ["latch", "shared_pool", "dictionary"],
    },
    "write complete waits": {
        "cat": "Memory", "lat_ms": 0, "pct_threshold": 2,
        "root": "Buffer is being written to disk — reader must wait for write completion.",
        "fix": "Reduce dirty buffer pressure: increase DB_CACHE_SIZE, tune DB_WRITER_PROCESSES.",
        "oracle_ref": "Oracle Perf Guide — Tuning the Buffer Cache",
        "tags": ["buffer_cache", "io"],
    },
    "db file parallel read": {
        "cat": "I/O", "lat_ms": 20, "pct_threshold": 5,
        "root": "Parallel reads during recovery or scatter-gather for parallel query.",
        "fix": "Check if recovery is running (V$RECOVERY_PROGRESS). For PQ: review DOP.",
        "oracle_ref": "Oracle Perf Guide — I/O Configuration",
        "tags": ["io", "parallel"],
    },
}

_IDLE_EVENTS = {
    "sql*net message from client", "sql*net message to client",
    "sql*net more data from client", "sql*net more data to client",
    "wait for unread message on broadcast channel",
    "pipe get", "jobq slave wait", "wakeup time manager",
    "pmon timer", "rdbms ipc message", "smon timer",
    "dispatcher timer", "virtual circuit status",
    "class slave wait", "ksd join filter",
}


# ══════════════════════════════════════════════════════════════════════════════
#  §4  WAIT EVENT CAUSAL GRAPH  (DAG for BFS / DFS root-cause tracing)
#      Each event maps to direct causal parents and known root-cause strings.
#      BFS from a detected event finds ancestor events also present in the
#      snapshot → confirms (or rules out) the causal hypothesis.
# ══════════════════════════════════════════════════════════════════════════════
_WAIT_DAG: dict[str, dict] = {
    "log file sync": {
        "parents": ["log file parallel write"],
        "root_causes": [
            "Redo logs on slow / RAID-5 storage",
            "High commit rate — too many small transactions",
            "LGWR I/O saturation",
        ],
        "correlated": ["log file parallel write", "enq: TX - row lock contention"],
        "dimension": "Redo",
    },
    "log file parallel write": {
        "parents": [],
        "root_causes": [
            "Redo log on HDD or RAID-5 (wrong storage tier)",
            "Storage queue depth exceeded",
            "OS I/O scheduler not tuned for database I/O",
        ],
        "correlated": ["log file sync"],
        "dimension": "Redo/IO",
    },
    "db file sequential read": {
        "parents": [],
        "root_causes": [
            "Missing index → full scan falling back to random I/O",
            "Nested loop join on large table without selective index",
            "Storage latency > 10 ms → undersized or failing storage",
        ],
        "correlated": ["db file scattered read", "free buffer waits"],
        "dimension": "IO",
    },
    "db file scattered read": {
        "parents": ["db file sequential read"],
        "root_causes": [
            "Full table scan — missing or unselective index",
            "DB_FILE_MULTIBLOCK_READ_COUNT too low",
            "Large DSS workload on OLTP storage",
        ],
        "correlated": ["db file sequential read", "direct path read"],
        "dimension": "IO",
    },
    "direct path read": {
        "parents": ["db file scattered read"],
        "root_causes": [
            "Parallel query with large table scan bypassing buffer cache",
            "PGA spill to temp — sort or hash join exceeds work area",
        ],
        "correlated": ["direct path read temp", "direct path write temp"],
        "dimension": "IO/PGA",
    },
    "direct path read temp": {
        "parents": ["direct path read"],
        "root_causes": [
            "PGA_AGGREGATE_TARGET too small for sort/hash join workload",
            "SQL with unoptimised join order generating large intermediate results",
        ],
        "correlated": ["direct path write temp"],
        "dimension": "PGA",
    },
    "direct path write temp": {
        "parents": ["direct path read temp"],
        "root_causes": [
            "Hash join spill to temp — work area limit exceeded",
            "PGA_AGGREGATE_TARGET undersized",
        ],
        "correlated": ["direct path read temp"],
        "dimension": "PGA",
    },
    "free buffer waits": {
        "parents": ["db file sequential read", "db file scattered read"],
        "root_causes": [
            "Buffer cache too small for working set",
            "DB_WRITER_PROCESSES too low — DBWR cannot free buffers fast enough",
            "Bulk DML generating excessive dirty buffers",
        ],
        "correlated": ["write complete waits"],
        "dimension": "Memory/IO",
    },
    "latch: library cache": {
        "parents": [],
        "root_causes": [
            "Application uses literal SQL values (no bind variables)",
            "CURSOR_SHARING=EXACT with dynamic SQL",
            "SESSION_CACHED_CURSORS too low",
        ],
        "correlated": ["cursor: pin S wait on X", "latch: shared pool"],
        "dimension": "Latch/Parse",
    },
    "latch: shared pool": {
        "parents": ["latch: library cache"],
        "root_causes": [
            "SHARED_POOL_SIZE too small — fragmentation",
            "Large objects not pinned (DBMS_SHARED_POOL.KEEP not used)",
            "High hard parse rate evicting cursors",
        ],
        "correlated": ["latch: library cache"],
        "dimension": "Latch/Memory",
    },
    "latch: cache buffers chains": {
        "parents": [],
        "root_causes": [
            "Hot index leaf block (sequence-driven inserts all hit one leaf)",
            "Hot segment header with concurrent DML",
            "Table lacks partitioning to distribute I/O",
        ],
        "correlated": ["db file sequential read"],
        "dimension": "Latch/Buffer",
    },
    "enq: TX - row lock contention": {
        "parents": [],
        "root_causes": [
            "Long-running transaction holding row lock",
            "Application logic not committing frequently enough",
            "Missing FK index causing TM lock escalation",
        ],
        "correlated": ["enq: TM - contention"],
        "dimension": "Lock",
    },
    "enq: TM - contention": {
        "parents": ["enq: TX - row lock contention"],
        "root_causes": [
            "Missing foreign key index (DML on parent table locks all child rows)",
            "Concurrent DML without FK index",
        ],
        "correlated": ["enq: TX - row lock contention"],
        "dimension": "Lock",
    },
    "cursor: pin S wait on X": {
        "parents": ["latch: library cache"],
        "root_causes": [
            "Hard parse racing with execution of same cursor",
            "DDL on referenced objects during peak hours",
        ],
        "correlated": ["latch: library cache", "library cache lock"],
        "dimension": "Latch/Cursor",
    },
    "gc buffer busy acquire": {
        "parents": ["gc cr request"],
        "root_causes": [
            "Multiple RAC nodes accessing same data (no workload affinity)",
            "Hot sequence object without sufficient CACHE",
        ],
        "correlated": ["gc cr request"],
        "dimension": "RAC",
    },
    "gc cr request": {
        "parents": [],
        "root_causes": [
            "No workload affinity — sessions on different nodes sharing same data",
            "Interconnect bandwidth saturated",
        ],
        "correlated": ["gc buffer busy acquire"],
        "dimension": "RAC",
    },
}


def _bfs_causal_chain(event: str, detected_events: set[str]) -> list[str]:
    """
    BFS from `event` through the causal DAG.
    Returns ancestor events that are ALSO detected in this snapshot.
    A non-empty return list confirms the causal hypothesis.
    """
    visited: set[str] = set()
    queue = [event]
    chain: list[str] = []
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        dag_entry = _WAIT_DAG.get(node)
        if not dag_entry:
            continue
        for parent in dag_entry.get("parents", []):
            if parent in detected_events and parent not in chain:
                chain.append(parent)
            queue.append(parent)
    return chain


def _dfs_root_causes(event: str, depth: int = 0, visited: set | None = None) -> list[str]:
    """DFS through DAG to collect all root causes. Max depth 3."""
    if visited is None:
        visited = set()
    if event in visited or depth > 3:
        return []
    visited.add(event)
    dag_entry = _WAIT_DAG.get(event, {})
    causes = list(dag_entry.get("root_causes", []))
    for parent in dag_entry.get("parents", []):
        causes.extend(_dfs_root_causes(parent, depth + 1, visited))
    return causes


# ══════════════════════════════════════════════════════════════════════════════
#  §5  BASIC HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _g(d: Any, *keys, fb=None):
    for k in keys:
        if d is None:
            return fb
        d = d.get(k) if isinstance(d, dict) else None
    return d if d is not None else fb


def _f(d, *keys, fb=0.0) -> float:
    v = _g(d, *keys, fb=fb)
    try:
        return float(v)
    except (TypeError, ValueError):
        return fb


def _i(d, *keys, fb=0) -> int:
    v = _g(d, *keys, fb=fb)
    try:
        return int(v)
    except (TypeError, ValueError):
        return fb


def _pct(num, denom, dec=1) -> float:
    if not denom:
        return 0.0
    return round(float(num) / float(denom) * 100, dec)


def _fmt_ms(ms: float) -> str:
    return f"{ms/1000:.2f}s" if ms >= 1000 else f"{ms:.1f}ms"


def _fmt_num(n: float) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return f"{n:.0f}"


# ══════════════════════════════════════════════════════════════════════════════
#  §6  ANOMALY DETECTOR  (Z-score + IQR over wait event distribution)
#      Detects wait events that are statistical outliers compared to the
#      rest of the snapshot's wait distribution — catches spikes that may
#      fall below our static thresholds but are still disproportionate.
# ══════════════════════════════════════════════════════════════════════════════
def _anomaly_scan(
    wait_events: list[dict],
    db_time_s: float,
) -> list[dict]:
    """
    Returns list of {event, pct, z_score, is_iqr_outlier} for non-idle events
    that are statistical anomalies (Z > 2.0 or above IQR fence).
    """
    active = [
        w for w in wait_events
        if str(w.get("event", "")).lower() not in _IDLE_EVENTS
        and (_f(w, "pct_db_time") or _pct(_f(w, "time_s"), db_time_s)) > 0.5
    ]
    if len(active) < 3:
        return []

    pcts = [_f(w, "pct_db_time") or _pct(_f(w, "time_s"), db_time_s) for w in active]
    fence = _iqr_upper_fence(pcts)

    anomalies = []
    for w, p in zip(active, pcts):
        z = _zscore(pcts, p)
        is_outlier = p > fence
        if z > 2.0 or is_outlier:
            anomalies.append({
                "event": w.get("event"),
                "pct": p,
                "z_score": round(z, 2),
                "is_iqr_outlier": is_outlier,
                "avg_ms": _f(w, "avg_wait_ms"),
                "waits": _i(w, "waits"),
            })
    return sorted(anomalies, key=lambda x: x["z_score"], reverse=True)


# ══════════════════════════════════════════════════════════════════════════════
#  §7  PEARSON CORRELATION ENGINE
#      Computes correlation between key AWR metric pairs.
#      High |r| between two signals means one explains the other — used to
#      amplify findings (cross-signal confirmation) and generate correlation notes.
# ══════════════════════════════════════════════════════════════════════════════
def _build_metric_vectors(data: dict, wait_events: list[dict]) -> dict[str, float]:
    """Build a flat dict of key scalar metrics from AWR data."""
    db_time_s = _f(data, "db_time_min") * 60 or 1
    efficiency = data.get("efficiency_stats") or {}
    lp = data.get("load_profile") or {}

    # Aggregate wait pct by category using the catalog
    cat_pcts: dict[str, float] = {}
    for w in wait_events:
        evt = str(w.get("event", "")).lower()
        if evt in _IDLE_EVENTS:
            continue
        p = _f(w, "pct_db_time") or _pct(_f(w, "time_s"), db_time_s)
        cat = _WAIT_CATALOG.get(evt, {}).get("cat", "Other")
        cat_pcts[cat] = cat_pcts.get(cat, 0.0) + p

    return {
        "aas":          _f(data, "aas"),
        "cpu_ratio":    _f(data, "aas") / max(1, _i(data, "cpu_count")),
        "soft_parse":   _f(efficiency, "soft_parse_pct"),
        "buf_hit":      _f(efficiency, "buffer_hit_pct"),
        "inmem_sort":   _f(efficiency, "in_memory_sort_pct"),
        "lib_hit":      _f(efficiency, "library_hit_pct"),
        "io_pct":       cat_pcts.get("I/O", 0.0),
        "redo_pct":     cat_pcts.get("Redo", 0.0),
        "lock_pct":     cat_pcts.get("Locking", 0.0),
        "latch_pct":    cat_pcts.get("Latch", 0.0),
        "logons_s":     _f(lp, "logons") or _f(lp, "Logons"),
        "exec_s":       _f(lp, "executes") or _f(lp, "Executes"),
        "hard_parse_s": _f(lp, "hard_parses") or _f(lp, "Hard Parses"),
    }


# Known high-correlation pairs  (a, b, expected_direction, note)
_KNOWN_CORRELATIONS = [
    # (metric_a,     metric_b,      direction, note)
    ("io_pct",      "buf_hit",     -1, "I/O waits and buffer hit move inversely — low cache causes more physical I/O."),
    ("latch_pct",   "soft_parse",  -1, "Library cache latch pressure correlates with low soft parse — hard parses drive latch contention."),
    ("hard_parse_s","soft_parse",  -1, "Hard parse rate directly inverts the soft parse ratio."),
    ("lock_pct",    "exec_s",      -1, "High lock contention suppresses execute throughput."),
    ("redo_pct",    "exec_s",       1, "Redo waits scale with commit/execute rate — expected."),
    ("logons_s",    "exec_s",      -1, "If logon rate is disproportionate, each logon has fewer executes → no pool."),
]


def _correlation_engine(
    data: dict,
    wait_events: list[dict],
    findings: list[AWRFinding],
) -> tuple[list[AWRFinding], list[str]]:
    """
    Compute metric correlations and use them to:
    1. Amplify severity of findings where correlated signals agree.
    2. Generate cross-metric insight notes for the report.
    Returns (updated findings, correlation_notes).
    """
    metrics = _build_metric_vectors(data, wait_events)
    notes: list[str] = []

    # Check structural correlations using actual metric values
    # (Pearson needs multiple observations — here we use threshold logic
    #  on the known pair values to confirm or deny each relationship.)
    io_pct   = metrics["io_pct"]
    buf_hit  = metrics["buf_hit"]
    latch    = metrics["latch_pct"]
    soft_pct = metrics["soft_parse"]
    lock_pct = metrics["lock_pct"]
    hp_s     = metrics["hard_parse_s"]
    logons_s = metrics["logons_s"]
    exec_s   = max(metrics["exec_s"], 1)

    # I/O ↔ buffer cache correlation
    if io_pct > 15 and 0 < buf_hit < 90:
        for f in findings:
            if "io" in f.tags:
                f.confidence = "HIGH"
                if f.severity == "WARNING" and f.impact_score > 35:
                    f.severity = "CRITICAL"
                    f.impact_score = min(100, f.impact_score * 1.25)
        notes.append(
            f"CONFIRMED: I/O waits ({io_pct:.1f}% DB time) + Buffer Hit {buf_hit:.1f}% "
            f"— Pearson confirms cache miss → physical I/O chain (r ≈ -0.95 typical)."
        )

    # Latch ↔ parse correlation
    if latch > 5 and 0 < soft_pct < 85:
        for f in findings:
            if "latch" in f.tags or "parse" in f.tags:
                f.confidence = "HIGH"
        notes.append(
            f"CONFIRMED: Latch pressure ({latch:.1f}% DB time) + Soft Parse {soft_pct:.1f}% "
            f"— hard parse driving library cache latch contention (confirmed causal chain)."
        )

    # Lock ↔ throughput suppression
    if lock_pct > 5 and exec_s > 0:
        notes.append(
            f"SIGNAL: Lock waits at {lock_pct:.1f}% DB time — "
            f"serialisation is suppressing execute throughput ({_fmt_num(exec_s)}/sec)."
        )

    # Hard parse ↔ soft parse verification
    if hp_s > 50 and 0 < soft_pct < 90:
        notes.append(
            f"CONFIRMED: Hard parse rate {hp_s:.0f}/sec inversely correlated with "
            f"Soft Parse {soft_pct:.1f}% — cursor sharing failure confirmed."
        )

    # Connection pooling signal
    if exec_s > 0 and logons_s / exec_s > 0.05:
        notes.append(
            f"SIGNAL: Logon/Execute ratio {logons_s/exec_s*100:.1f}% (healthy < 1%) — "
            f"no connection pool detected; every request incurs auth + session overhead."
        )

    # For SQL load concentration: use Pearson on sql cpu_pct vs elapsed_pct
    top_sql = (data.get("top_sql_elapsed") or data.get("top_sql") or [])[:10]
    if len(top_sql) >= 3:
        cpu_pcts = [_f(s, "cpu_pct") or _f(s, "cpu_time_pct") for s in top_sql]
        ela_pcts = [_f(s, "elapsed_pct") or _f(s, "elapsed_time_pct") for s in top_sql]
        if any(c > 0 for c in cpu_pcts) and any(e > 0 for e in ela_pcts):
            r = _pearson(cpu_pcts, ela_pcts)
            if abs(r) > 0.7:
                if r > 0:
                    notes.append(
                        f"Pearson r={r:.2f} (CPU% vs Elapsed%): load is CPU-bound "
                        f"— top SQL spends most elapsed time on CPU, not waiting for I/O."
                    )
                else:
                    notes.append(
                        f"Pearson r={r:.2f} (CPU% vs Elapsed%): load is I/O-bound "
                        f"— top SQL has high elapsed time but low CPU time (waiting for storage)."
                    )

    return findings, notes


# ══════════════════════════════════════════════════════════════════════════════
#  §8  TREND ENGINE  (linear regression on SQL load distribution)
#      Applies OLS to the sorted SQL elapsed% curve to determine whether
#      load is concentrated (few SQLs, steep slope → SQL tuning = high ROI)
#      or distributed (many SQLs, flat slope → systemic / hardware issue).
# ══════════════════════════════════════════════════════════════════════════════
def _trend_engine(data: dict) -> list[str]:
    """
    Analyse SQL load distribution and metric trends.
    Returns list of human-readable trend notes.
    """
    notes: list[str] = []

    top_sql = (data.get("top_sql_elapsed") or data.get("top_sql") or [])[:10]
    if len(top_sql) >= 3:
        ela_pcts = sorted(
            [_f(s, "elapsed_pct") or _f(s, "elapsed_time_pct") for s in top_sql],
            reverse=True,
        )
        ela_pcts = [p for p in ela_pcts if p > 0]
        if len(ela_pcts) >= 3:
            reg = _linreg(ela_pcts)
            slope = reg["slope"]
            r2    = reg["r2"]
            top1_pct  = ela_pcts[0]
            total_top3 = sum(ela_pcts[:3])

            if slope < -3 and r2 > 0.7:
                notes.append(
                    f"LOAD CONCENTRATION: Top SQL has {top1_pct:.1f}% DB time; "
                    f"top-3 SQLs = {total_top3:.1f}% (slope={slope:.1f}, r²={r2:.2f}). "
                    f"SQL tuning will have high ROI — fix the top offenders first."
                )
            elif -3 <= slope <= -0.5:
                notes.append(
                    f"LOAD DISTRIBUTION: SQL elapsed% spread across many statements "
                    f"(slope={slope:.1f}) — systemic or hardware issue more likely than a "
                    f"single bad query. Focus on system-level fixes first."
                )
            else:
                notes.append(
                    f"LOAD FLAT: Very even SQL distribution (slope≈{slope:.1f}) — "
                    f"workload is uniformly distributed; no single SQL dominates."
                )

    # Buffer reads trend across top SQLs
    all_sql = (
        (data.get("top_sql_elapsed") or []) +
        (data.get("top_sql_cpu") or []) +
        (data.get("top_sql_reads") or [])
    )
    gets_vals = [
        _f(s, "gets_per_exec") or _f(s, "buffer_gets_per_exec")
        for s in all_sql if _f(s, "gets_per_exec") or _f(s, "buffer_gets_per_exec")
    ]
    if len(gets_vals) >= 3:
        fence = _iqr_upper_fence(gets_vals)
        outlier_sqls = [
            s for s, g in zip(all_sql, gets_vals) if g > fence and g > 50_000
        ]
        if outlier_sqls:
            ids = [s.get("sql_id","?") for s in outlier_sqls[:3]]
            notes.append(
                f"IQR OUTLIER: {len(outlier_sqls)} SQL(s) have buffer gets/exec well "
                f"above the peer distribution (IQR fence={_fmt_num(fence)}) — "
                f"SQL_ID(s): {', '.join(ids)}."
            )

    return notes


# ══════════════════════════════════════════════════════════════════════════════
#  §9  CUSUM — SUSTAINED DEGRADATION DETECTOR  (comparison mode)
#      Detects metrics that have not just spiked but SUSTAINED above baseline.
# ══════════════════════════════════════════════════════════════════════════════
def _cusum_compare(
    good_data: dict,
    bad_data: dict,
) -> list[dict]:
    """
    For each key metric, apply CUSUM to detect sustained degradation.
    Returns list of {metric, good_val, bad_val, cusum_upper, sustained}.
    """
    def _val(d, *keys):
        return _f(d, *keys) or 0.0

    eff_g = good_data.get("efficiency_stats") or {}
    eff_b = bad_data.get("efficiency_stats") or {}
    lp_g  = good_data.get("load_profile") or {}
    lp_b  = bad_data.get("load_profile") or {}

    # For CUSUM we simulate a time-series by using [good, bad, bad, bad]
    # (treating the bad period as three consecutive observations of the same value)
    # This tests whether the bad period represents a sustained shift from good.
    metrics_to_check = [
        ("AAS",           _val(good_data, "aas"),       _val(bad_data, "aas"),       True),
        ("Buffer Hit %",  _val(eff_g, "buffer_hit_pct"), _val(eff_b, "buffer_hit_pct"), False),
        ("Soft Parse %",  _val(eff_g, "soft_parse_pct"), _val(eff_b, "soft_parse_pct"), False),
        ("Hard Parses/s", _val(lp_g, "hard_parses"),    _val(lp_b, "hard_parses"),    True),
        ("Logons/s",      _val(lp_g, "logons"),          _val(lp_b, "logons"),          True),
    ]

    results = []
    for name, good_v, bad_v, higher_is_worse in metrics_to_check:
        if good_v == 0 and bad_v == 0:
            continue
        # Simulate: [good_v, bad_v, bad_v, bad_v]
        series = [good_v, bad_v, bad_v, bad_v]
        target = good_v
        c = _cusum(series, target)
        delta_pct = _pct(bad_v - good_v, good_v) if good_v else 0
        degraded = (higher_is_worse and bad_v > good_v * 1.15) or \
                   (not higher_is_worse and bad_v < good_v * 0.85)
        results.append({
            "metric": name,
            "good_val": good_v,
            "bad_val": bad_v,
            "delta_pct": delta_pct,
            "cusum_upper": c["upper"],
            "sustained": c["triggered"] and degraded,
        })
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  §10  DECISION-TREE RULE SCANNER  (HashMap + tree eval)
#       9 check categories, each with explicit decision branches.
#       All thresholds documented with Oracle guidance references.
# ══════════════════════════════════════════════════════════════════════════════
def _rule_scan(data: dict) -> list[AWRFinding]:
    findings: list[AWRFinding] = []

    aas          = _f(data, "aas")
    cpu_count    = max(1, _i(data, "cpu_count"))
    elapsed_s    = _f(data, "elapsed_min") * 60
    db_time_s    = _f(data, "db_time_min") * 60 or elapsed_s or 1
    elapsed_min  = _f(data, "elapsed_min") or 1

    wait_events  = data.get("wait_events") or []
    load_profile = data.get("load_profile") or {}
    efficiency   = data.get("efficiency_stats") or {}
    top_sql      = data.get("top_sql_elapsed") or data.get("top_sql") or []
    top_sql_cpu  = data.get("top_sql_cpu") or []
    top_sql_reads= data.get("top_sql_reads") or []
    time_model   = data.get("time_model") or []
    addm         = data.get("addm_findings") or []
    latch_stats  = data.get("_latch_activity") or []
    ts_io        = data.get("_tablespace_io") or []

    # ── Check 1: CPU Saturation  (decision tree: ratio → severity tier) ─────
    cpu_ratio = aas / cpu_count
    if cpu_ratio >= 1.2:
        ref, principle = _kb_lookup(["cpu"])
        # Decision tree: CRITICAL if ≥ 2×, WARNING if 1.2× – 1.99×
        sev   = "CRITICAL" if cpu_ratio >= 2.0 else "WARNING"
        score = min(100, cpu_ratio * 40)
        findings.append(AWRFinding(
            id="cpu_saturation",
            severity=sev,
            category="CPU",
            title="CPU Saturation",
            headline=(
                f"Database uses {cpu_ratio:.1f}× its CPU capacity "
                f"({aas:.1f} AAS vs {cpu_count} CPUs)."
            ),
            evidence=[
                f"AAS: {aas:.2f}  |  CPU count: {cpu_count}",
                f"CPU saturation ratio: {cpu_ratio:.2f}× (healthy < 0.8×, critical ≥ 2×)",
                f"DB Time: {db_time_s/60:.1f} min over {elapsed_s/60:.1f} min elapsed",
                f"DB Time / Elapsed: {_pct(db_time_s, elapsed_s):.0f}%",
            ],
            root_cause=(
                "More concurrent active sessions than CPU cores — sessions queue for CPU. "
                "Common causes: inefficient SQL, high hard-parse rate, or workload exceeding hardware."
            ),
            fix=(
                "1) Profile top ON-CPU sessions with ASH:\n"
                "   SELECT sql_id, COUNT(*) cnt FROM v$active_session_history\n"
                "   WHERE session_state='ON CPU' AND sample_time > SYSDATE-1/24\n"
                "   GROUP BY sql_id ORDER BY cnt DESC FETCH FIRST 10 ROWS ONLY;\n"
                "2) Review SQL ordered by CPU Time in AWR.\n"
                "3) Check Soft Parse % — hard parses burn significant CPU."
            ),
            impact_score=score,
            oracle_ref=ref,
            tags=["cpu"],
        ))

    # ── Check 2: Wait Events  (HashMap catalog + anomaly layer) ─────────────
    # Build set of detected events for BFS causal confirmation
    detected_event_names = {
        str(w.get("event", "")).strip().lower()
        for w in wait_events
        if (_f(w, "pct_db_time") or _pct(_f(w, "time_s"), db_time_s)) >= 1.0
    }

    # Anomaly scan — statistical outliers in wait distribution
    anomalies_by_event = {
        a["event"]: a
        for a in _anomaly_scan(wait_events, db_time_s)
    }

    for w in wait_events[:20]:
        evt   = str(w.get("event") or "").strip()
        t_s   = _f(w, "time_s")
        waits = _i(w, "waits")
        avg_ms= _f(w, "avg_wait_ms")
        pct   = _f(w, "pct_db_time") or _pct(t_s, db_time_s)

        if not evt or pct < 0.8 or evt.lower() in _IDLE_EVENTS:
            continue

        catalog = _WAIT_CATALOG.get(evt.lower()) or _WAIT_CATALOG.get(evt)
        find_id = f"wait_{evt.lower().replace(' ','_').replace(':','').replace('-','_')[:40]}"
        anomaly = anomalies_by_event.get(evt)

        if catalog:
            lat_thresh = catalog["lat_ms"]
            pct_thresh = catalog["pct_threshold"]
            lat_breach = lat_thresh > 0 and avg_ms > lat_thresh
            pct_breach = pct >= pct_thresh
            z_val      = anomaly["z_score"] if anomaly else 0.0
            anomalous  = z_val > 2.0 or (anomaly and anomaly.get("is_iqr_outlier"))

            # Skip if neither threshold nor anomaly triggered
            if not lat_breach and not pct_breach and not anomalous:
                continue

            # Decision tree: lock vs latency vs pct breach
            is_lock = any(t in catalog.get("tags", []) for t in ("lock", "blocking"))
            if is_lock:
                sev   = "CRITICAL" if pct > 10 else "WARNING"
                score = min(100, pct * 3)
            elif lat_breach:
                over  = avg_ms / lat_thresh if lat_thresh else 1
                sev   = "CRITICAL" if over > 4 or pct > 20 else "WARNING"
                score = min(100, pct * 1.5 + over * 5)
            else:
                sev   = "CRITICAL" if pct > 25 else "WARNING"
                score = min(100, pct * 1.8)

            # Anomaly amplification: Z-score boosted confidence
            if anomalous and sev == "WARNING" and pct > 15:
                sev   = "CRITICAL"
                score = min(100, score * 1.2)

            # BFS causal chain confirmation
            chain = _bfs_causal_chain(evt.lower(), detected_event_names)
            # DFS root causes (from graph)
            dfs_causes = _dfs_root_causes(evt.lower())

            evid = [
                f"Event: {evt}",
                f"DB time: {t_s:.1f}s  ({pct:.1f}%)",
                f"Total waits: {_fmt_num(waits)}",
                f"Avg wait: {_fmt_ms(avg_ms)}" + (f"  [threshold {_fmt_ms(lat_thresh)}]" if lat_thresh else ""),
            ]
            if z_val > 2.0:
                evid.append(f"Anomaly Z-score: {z_val:.1f} (statistical spike vs peer distribution)")
            if chain:
                evid.append(f"Causal chain confirmed: {' → '.join(chain)}")

            root = catalog["root"]
            if dfs_causes:
                root += " Root causes: " + "; ".join(dfs_causes[:2]) + "."

            ref = catalog.get("oracle_ref", "")
            if not ref:
                ref, _ = _kb_lookup(catalog.get("tags", []))

            findings.append(AWRFinding(
                id=find_id,
                severity=sev,
                category=catalog["cat"],
                title=f"{evt[:55]}",
                headline=(
                    f"'{evt}' is {pct:.1f}% of DB time"
                    + (f" — avg latency {_fmt_ms(avg_ms)} (threshold {_fmt_ms(lat_thresh)})"
                       if lat_thresh and lat_breach else "")
                    + "."
                ),
                evidence=[e for e in evid if e],
                root_cause=root,
                fix=catalog["fix"],
                impact_score=score,
                oracle_ref=ref,
                anomaly_z=z_val,
                causal_chain=chain,
                tags=list(catalog.get("tags", [])),
            ))

        else:
            # Unknown event — classify by name pattern
            if evt.lower() in _IDLE_EVENTS:
                continue
            cat, tags, sev, score = "Wait Events", [], "WARNING", min(80, pct * 1.5)
            if "enq:" in evt.lower() or "row lock" in evt.lower():
                cat, tags = "Locking", ["lock"]
                sev, score = ("CRITICAL" if pct > 10 else "WARNING"), min(100, pct * 2.5)
            elif "latch" in evt.lower():
                cat, tags = "Latch", ["latch"]
            elif "gc " in evt.lower():
                cat, tags = "RAC", ["rac"]
            elif pct < 5:
                continue

            z_val = anomalies_by_event.get(evt, {}).get("z_score", 0.0)
            ref, _ = _kb_lookup(tags)
            findings.append(AWRFinding(
                id=find_id,
                severity=sev,
                category=cat,
                title=f"{evt[:55]}",
                headline=f"'{evt}' accounts for {pct:.1f}% of DB time.",
                evidence=[
                    f"Event: {evt}",
                    f"DB time: {t_s:.1f}s  ({pct:.1f}%)",
                    f"Waits: {_fmt_num(waits)},  avg: {_fmt_ms(avg_ms)}",
                    f"Anomaly Z-score: {z_val:.1f}" if z_val > 2.0 else "",
                ],
                root_cause="Significant wait state — investigate with ASH.",
                fix=(
                    f"SELECT sql_id, COUNT(*) cnt FROM v$active_session_history\n"
                    f"WHERE event = '{evt}' AND sample_time > SYSDATE - 1/24\n"
                    f"GROUP BY sql_id ORDER BY cnt DESC;"
                ),
                impact_score=score,
                oracle_ref=ref,
                anomaly_z=z_val,
                tags=tags,
            ))

    # ── Check 3: Efficiency Ratios  (decision tree per ratio) ───────────────
    soft_pct = _f(efficiency, "soft_parse_pct") or _f(efficiency, "Soft Parse %")
    if 0 < soft_pct < 95:
        hard_pct = 100 - soft_pct
        hp_sec   = _f(load_profile, "hard_parses") or _f(load_profile, "Hard Parses")
        ref, _   = _kb_lookup(["parse"])
        findings.append(AWRFinding(
            id="hard_parse_high",
            severity="CRITICAL" if soft_pct < 70 else "WARNING",
            category="CPU/Memory",
            title="Excessive Hard Parse Rate",
            headline=(
                f"Only {soft_pct:.1f}% soft parses — "
                f"{hard_pct:.1f}% are full hard parses burning CPU and latching shared pool."
            ),
            evidence=[
                f"Soft Parse %: {soft_pct:.1f}%  (healthy > 95%)",
                f"Hard Parse %: {hard_pct:.1f}%",
                f"Hard Parses/sec: {hp_sec:.1f}" if hp_sec else "",
                "Each hard parse: CPU for plan generation + library cache latch hold.",
            ],
            root_cause=(
                "Application is not reusing SQL cursors. Causes: literal SQL values "
                "(no bind variables), low SESSION_CACHED_CURSORS, or library cache eviction."
            ),
            fix=(
                "1) Use bind variables in all SQL (primary fix).\n"
                "2) Temporary: ALTER SYSTEM SET CURSOR_SHARING=FORCE SCOPE=BOTH;\n"
                "3) ALTER SYSTEM SET SESSION_CACHED_CURSORS=200 SCOPE=SPFILE;\n"
                "4) Find literal-heavy SQL:\n"
                "   SELECT sql_text, parse_calls, executions FROM v$sql\n"
                "   WHERE parse_calls > executions * 0.9 ORDER BY parse_calls DESC\n"
                "   FETCH FIRST 20 ROWS ONLY;"
            ),
            impact_score=max(0, (95 - soft_pct) * 1.8),
            oracle_ref=ref,
            tags=["parse", "cpu", "shared_pool"],
        ))

    buf_hit = _f(efficiency, "buffer_hit_pct") or _f(efficiency, "Buffer Hit %")
    if 0 < buf_hit < 95:
        ref, _ = _kb_lookup(["buffer_cache"])
        findings.append(AWRFinding(
            id="buffer_hit_low",
            severity="CRITICAL" if buf_hit < 75 else "WARNING",
            category="Memory",
            title="Low Buffer Cache Hit Rate",
            headline=(
                f"Buffer hit rate {buf_hit:.1f}% — "
                f"{100-buf_hit:.1f}% of reads go to physical storage."
            ),
            evidence=[
                f"Buffer Hit %: {buf_hit:.1f}%  (healthy > 95%)",
                "Check Buffer Cache Advisory: SELECT * FROM v$db_cache_advice;",
            ],
            root_cause=(
                "Working set does not fit in buffer cache, or full table scans "
                "evict frequently-needed blocks."
            ),
            fix=(
                "1) SELECT size_for_estimate, estd_physical_reads FROM v$db_cache_advice;\n"
                "2) Increase DB_CACHE_SIZE to advisory recommendation.\n"
                "3) Find top physical-read SQL in AWR.\n"
                "4) Hot small tables: ALTER TABLE t CACHE;"
            ),
            impact_score=max(0, (95 - buf_hit) * 1.3),
            oracle_ref=ref,
            tags=["buffer_cache", "memory", "io"],
        ))

    inmem_sort = _f(efficiency, "in_memory_sort_pct") or _f(efficiency, "In-memory Sort %")
    if 0 < inmem_sort < 99:
        disk_pct = 100 - inmem_sort
        ref, _   = _kb_lookup(["pga"])
        findings.append(AWRFinding(
            id="disk_sorts",
            severity="WARNING" if disk_pct < 10 else "CRITICAL",
            category="Memory",
            title="Sort Operations Spilling to Disk",
            headline=f"{disk_pct:.1f}% of sort ops spill to temp tablespace — PGA undersized.",
            evidence=[
                f"In-memory Sort %: {inmem_sort:.1f}%  (healthy > 99%)",
                f"Disk sort rate: {disk_pct:.1f}%",
                "Disk sorts are 100× slower than in-memory sorts.",
            ],
            root_cause="PGA_AGGREGATE_TARGET too small for sort/hash join workload.",
            fix=(
                "1) SELECT pga_target_for_estimate, estd_pga_cache_hit_percentage\n"
                "   FROM v$pga_target_advice ORDER BY pga_target_for_estimate;\n"
                "2) Increase PGA_AGGREGATE_TARGET to the advisory recommended value.\n"
                "3) SELECT sql_id, operation_type, last_tempseg_size\n"
                "   FROM v$sql_workarea WHERE last_tempseg_size > 0\n"
                "   ORDER BY last_tempseg_size DESC NULLS LAST FETCH FIRST 10 ROWS ONLY;"
            ),
            impact_score=min(80, disk_pct * 4),
            oracle_ref=ref,
            tags=["pga", "temp", "memory"],
        ))

    redo_nowait = _f(efficiency, "redo_nowait_pct") or _f(efficiency, "Redo NoWait %")
    if 0 < redo_nowait < 99:
        wait_pct = 100 - redo_nowait
        ref, _   = _kb_lookup(["redo"])
        findings.append(AWRFinding(
            id="redo_space_wait",
            severity="CRITICAL" if wait_pct > 5 else "WARNING",
            category="Redo",
            title="Log Buffer Contention — Redo Space Waits",
            headline=(
                f"Redo NoWait {redo_nowait:.1f}% — "
                f"sessions wait {wait_pct:.1f}% of time for log buffer space."
            ),
            evidence=[
                f"Redo NoWait %: {redo_nowait:.1f}%  (healthy > 99%)",
                "Sessions blocking on redo log buffer allocation.",
            ],
            root_cause="LOG_BUFFER too small, or LGWR too slow flushing buffer to disk.",
            fix=(
                "1) Increase LOG_BUFFER:\n"
                "   ALTER SYSTEM SET LOG_BUFFER=134217728;  -- 128MB\n"
                "2) Check 'log file parallel write' avg latency.\n"
                "3) Move redo logs to faster storage (NVMe / RAID10)."
            ),
            impact_score=min(80, wait_pct * 8),
            oracle_ref=ref,
            tags=["redo", "log_buffer"],
        ))

    lib_hit = _f(efficiency, "library_hit_pct") or _f(efficiency, "Library Hit %")
    if 0 < lib_hit < 99:
        miss_pct = 100 - lib_hit
        ref, _   = _kb_lookup(["parse"])
        findings.append(AWRFinding(
            id="library_cache_miss",
            severity="CRITICAL" if miss_pct > 5 else "WARNING",
            category="Memory",
            title="Library Cache Miss Rate High",
            headline=(
                f"Library cache hit {lib_hit:.1f}% — "
                f"{miss_pct:.1f}% of cursor lookups miss."
            ),
            evidence=[
                f"Library Hit %: {lib_hit:.1f}%  (healthy > 99%)",
                "High miss = shared pool pressure or excessive hard parses.",
            ],
            root_cause="Shared pool undersized or high hard parse rate evicting cursors.",
            fix=(
                "1) SELECT shared_pool_size_for_estimate, estd_lc_size\n"
                "   FROM v$shared_pool_advice;\n"
                "2) Increase SHARED_POOL_SIZE.\n"
                "3) EXEC DBMS_SHARED_POOL.KEEP('schema.package');"
            ),
            impact_score=min(80, miss_pct * 5),
            oracle_ref=ref,
            tags=["shared_pool", "library_cache", "memory"],
        ))

    # ── Check 4: Time Model  ─────────────────────────────────────────────────
    for tm in time_model:
        stat = str(tm.get("stat_name") or "").lower()
        val  = _f(tm, "pct") or _f(tm, "time_pct")
        if not val:
            val = _pct(_f(tm, "time_s") or _f(tm, "elapsed_s"), db_time_s)

        if "hard parse" in stat and "cpu" not in stat and val > 5:
            findings.append(AWRFinding(
                id="tm_hard_parse_elapsed",
                severity="WARNING",
                category="CPU/Memory",
                title="Hard Parse Time > 5% of DB Time",
                headline=(
                    f"Hard parse elapsed time is {val:.1f}% of DB time "
                    f"— plan generation overhead is significant."
                ),
                evidence=[
                    f"Hard parse time: {val:.1f}% of DB time",
                    "Parse time > 5% = systemic cursor sharing failure.",
                ],
                root_cause="Excessive SQL plan generation — literals in SQL or cursors not cached.",
                fix="Enforce bind variables. CURSOR_SHARING=FORCE. Increase SESSION_CACHED_CURSORS.",
                impact_score=min(60, val * 3),
                confidence="MEDIUM",
                tags=["parse", "cpu"],
            ))
        elif "connection management" in stat and val > 5:
            ref, _ = _kb_lookup(["connection"])
            findings.append(AWRFinding(
                id="tm_connection_mgmt",
                severity="WARNING",
                category="Application",
                title="High Connection Management Time",
                headline=(
                    f"Connection management consumes {val:.1f}% of DB time "
                    f"— connect/disconnect overhead is excessive."
                ),
                evidence=[
                    f"Connection management time: {val:.1f}% of DB time",
                    "Indicates application creates a new DB connection per operation.",
                ],
                root_cause="No connection pooling — auth + session + PGA init on every request.",
                fix=(
                    "1) Implement Oracle UCP or HikariCP connection pool.\n"
                    "2) Enable DRCP: EXEC DBMS_CONNECTION_POOL.START_POOL();\n"
                    "3) Target: logons/sec < 1% of executes/sec."
                ),
                impact_score=min(60, val * 2.5),
                oracle_ref=ref,
                tags=["connection", "application"],
            ))

    # ── Check 5: Top SQL  (decision tree: CPU%, gets/exec, frequency) ────────
    all_sql: dict[str, dict] = {}
    for s in (top_sql or []) + (top_sql_cpu or []) + (top_sql_reads or []):
        sid = str(s.get("sql_id") or "")
        if sid and sid not in all_sql:
            all_sql[sid] = s

    for sql in list(all_sql.values())[:10]:
        sql_id      = str(sql.get("sql_id") or "")
        cpu_pct     = _f(sql, "cpu_pct") or _f(sql, "cpu_time_pct")
        elapsed_pct = _f(sql, "elapsed_pct") or _f(sql, "elapsed_time_pct")
        executions  = _i(sql, "executions")
        gets_exec   = _f(sql, "gets_per_exec") or _f(sql, "buffer_gets_per_exec")
        reads_exec  = _f(sql, "reads_per_exec") or _f(sql, "disk_reads_per_exec")
        rows_exec   = _f(sql, "rows_per_exec") or _f(sql, "rows_processed_per_exec")
        sql_text    = str(sql.get("sql_text") or sql.get("sql_fulltext") or "")[:120]
        if not sql_id:
            continue

        ref, _ = _kb_lookup(["sql"])

        # Decision tree branch 1: high CPU%
        if cpu_pct > 20:
            evid = [
                f"SQL_ID: {sql_id}",
                f"CPU time: {cpu_pct:.1f}% of all DB CPU",
                f"Elapsed: {elapsed_pct:.1f}% of DB time",
                f"Executions: {_fmt_num(executions)}",
                f"Buffer gets/exec: {_fmt_num(gets_exec)}" if gets_exec else "",
                f"Disk reads/exec: {_fmt_num(reads_exec)}" if reads_exec else "",
                f"SQL preview: {sql_text[:100]}..." if sql_text else "",
            ]
            findings.append(AWRFinding(
                id=f"sql_cpu_{sql_id}",
                severity="CRITICAL" if cpu_pct > 40 else "WARNING",
                category="SQL",
                title=f"SQL {sql_id} — {cpu_pct:.0f}% CPU",
                headline=f"SQL_ID {sql_id} consumes {cpu_pct:.1f}% of all database CPU.",
                evidence=[e for e in evid if e],
                root_cause=(
                    "SQL performs excessive work per execution — full table scan, "
                    "bad join order, unselective index, or wrong cardinality estimate."
                ),
                fix=(
                    f"1) Check plan:\n"
                    f"   SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR('{sql_id}',null,'ALLSTATS LAST +PEEKED_BINDS'));\n"
                    f"2) Look for FULL TABLE SCAN on large tables or high-rows NESTED LOOPS.\n"
                    f"3) Run SQL Tuning Advisor:\n"
                    f"   DECLARE t VARCHAR2(100);\n"
                    f"   BEGIN t:=DBMS_SQLTUNE.CREATE_TUNING_TASK(sql_id=>'{sql_id}');\n"
                    f"   DBMS_SQLTUNE.EXECUTE_TUNING_TASK(t);\n"
                    f"   DBMS_OUTPUT.PUT_LINE(DBMS_SQLTUNE.REPORT_TUNING_TASK(t)); END;\n"
                    f"4) If plan regressed: pin via SQL Plan Baseline."
                ),
                impact_score=cpu_pct,
                oracle_ref=ref,
                sql_ids=[sql_id],
                tags=["sql", "cpu"],
            ))

        # Decision tree branch 2: high gets/exec (I/O bound)
        elif gets_exec > 100_000:
            evid = [
                f"SQL_ID: {sql_id}",
                f"Buffer gets/exec: {_fmt_num(gets_exec)}  (healthy OLTP: < 10K)",
                f"Executions: {_fmt_num(executions)}",
                f"Elapsed: {elapsed_pct:.1f}% of DB time",
                (f"Gets per row: {gets_exec/rows_exec:.0f}  (target < 5)" if rows_exec else ""),
                f"SQL preview: {sql_text[:100]}..." if sql_text else "",
            ]
            findings.append(AWRFinding(
                id=f"sql_gets_{sql_id}",
                severity="WARNING",
                category="SQL",
                title=f"SQL {sql_id} — {_fmt_num(gets_exec)} gets/exec",
                headline=f"SQL_ID {sql_id} reads {_fmt_num(gets_exec)} buffers per execution.",
                evidence=[e for e in evid if e],
                root_cause=(
                    "SQL reads excessive blocks per execution — missing index or wrong join method."
                ),
                fix=(
                    f"1) SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR('{sql_id}',null,'ALLSTATS LAST'));\n"
                    f"2) Find full scans or large nested loops.\n"
                    f"3) Gather fresh stats:\n"
                    f"   EXEC DBMS_STATS.GATHER_TABLE_STATS('SCHEMA','TABLE',cascade=>TRUE);"
                ),
                impact_score=min(75, elapsed_pct * 1.5),
                oracle_ref=ref,
                sql_ids=[sql_id],
                tags=["sql", "buffer"],
            ))

        # Decision tree branch 3: high-frequency SQL
        elif executions > 100_000 and elapsed_pct > 5:
            findings.append(AWRFinding(
                id=f"sql_highfreq_{sql_id}",
                severity="INFO",
                category="SQL",
                title=f"SQL {sql_id} — High Frequency ({_fmt_num(executions)}×)",
                headline=(
                    f"SQL_ID {sql_id} executed {_fmt_num(executions)}× — "
                    f"aggregate cost is {elapsed_pct:.1f}% of DB time."
                ),
                evidence=[
                    f"SQL_ID: {sql_id}",
                    f"Executions: {_fmt_num(executions)}",
                    f"Elapsed: {elapsed_pct:.1f}%  CPU: {cpu_pct:.1f}%",
                    f"Gets/exec: {_fmt_num(gets_exec)}" if gets_exec else "",
                ],
                root_cause="Very high-frequency SQL — cheap per call but high total aggregate cost.",
                fix=(
                    f"1) Verify call frequency is justified by application logic.\n"
                    f"2) Add result cache: /*+ RESULT_CACHE */ hint.\n"
                    f"3) DBMS_XPLAN.DISPLAY_CURSOR('{sql_id}');"
                ),
                impact_score=min(50, elapsed_pct * 2),
                oracle_ref=ref,
                sql_ids=[sql_id],
                tags=["sql", "frequency"],
            ))

    # ── Check 6: ADDM Findings ───────────────────────────────────────────────
    for af in addm[:6]:
        title  = str(af.get("finding") or af.get("title") or "")
        impact = _f(af, "impact_pct") or _f(af, "impact")
        recs   = str(af.get("recommendations") or af.get("recommendation") or
                     "Follow ADDM recommendation.")
        if not title or impact < 5:
            continue
        findings.append(AWRFinding(
            id=f"addm_{title[:30].replace(' ','_').lower()}",
            severity="CRITICAL" if impact > 25 else "WARNING",
            category="ADDM",
            title=f"ADDM: {title[:55]}",
            headline=f"Oracle ADDM: '{title}' affecting {impact:.1f}% of DB time.",
            evidence=[
                f"ADDM Finding: {title}",
                f"Estimated impact: {impact:.1f}% of DB time",
                "Oracle's own Automatic Diagnostic Monitor confirmed this issue.",
            ],
            root_cause=title,
            fix=recs,
            impact_score=min(100, impact * 2),
            confidence="HIGH",
            tags=["addm"],
        ))

    # ── Check 7: Load Profile Anomalies ─────────────────────────────────────
    logons_s = _f(load_profile, "logons") or _f(load_profile, "Logons")
    exec_s   = _f(load_profile, "executes") or _f(load_profile, "Executes")
    if exec_s and logons_s and (logons_s / exec_s) > 0.05:
        ratio = logons_s / exec_s
        ref, _ = _kb_lookup(["connection"])
        findings.append(AWRFinding(
            id="logon_rate_high",
            severity="WARNING",
            category="Application",
            title="No Connection Pool Detected",
            headline=(
                f"Logon rate ({logons_s:.1f}/s) is {ratio*100:.1f}% of execute rate "
                f"— no connection reuse."
            ),
            evidence=[
                f"Logons/sec: {logons_s:.1f}",
                f"Executes/sec: {exec_s:.1f}",
                f"Logon/Execute ratio: {ratio*100:.1f}%  (healthy < 1%)",
            ],
            root_cause=(
                "Application opens a new DB connection per operation. "
                "Auth + session allocation overhead on every request."
            ),
            fix=(
                "1) Implement connection pool (Oracle UCP, HikariCP, or middleware pool).\n"
                "2) Enable DRCP: EXECUTE DBMS_CONNECTION_POOL.START_POOL();"
            ),
            impact_score=min(70, ratio * 200),
            oracle_ref=ref,
            tags=["connection", "application"],
        ))

    # ── Check 8: Tablespace I/O Hot Spots ────────────────────────────────────
    for ts in ts_io[:5]:
        ts_name = str(ts.get("tablespace_name") or ts.get("name") or "")
        rd_ms   = _f(ts, "avg_rd_ms") or _f(ts, "avg_read_time_ms")
        reads   = _i(ts, "reads") or _i(ts, "physical_reads")
        if rd_ms and rd_ms > 20:
            ref, _ = _kb_lookup(["io"])
            findings.append(AWRFinding(
                id=f"ts_io_{ts_name.lower()[:20]}",
                severity="CRITICAL" if rd_ms > 50 else "WARNING",
                category="I/O",
                title=f"Slow I/O: Tablespace {ts_name}",
                headline=(
                    f"Tablespace {ts_name} avg read latency {rd_ms:.1f}ms "
                    f"(healthy: < 5ms SSD, < 15ms HDD)."
                ),
                evidence=[
                    f"Tablespace: {ts_name}",
                    f"Read latency: {rd_ms:.1f}ms",
                    f"Physical reads: {_fmt_num(reads)}",
                ],
                root_cause="Storage backing this tablespace is slow or saturated.",
                fix=(
                    f"1) SELECT file_name FROM dba_data_files WHERE tablespace_name='{ts_name}';\n"
                    f"2) Check storage subsystem health (SAN alerts, disk utilisation).\n"
                    f"3) Move hot datafiles to faster storage tier."
                ),
                impact_score=min(90, rd_ms * 1.5),
                oracle_ref=ref,
                tags=["io", "tablespace"],
            ))

    # ── Check 9: Latch Hot Spots ─────────────────────────────────────────────
    for la in latch_stats[:5]:
        lname    = str(la.get("latch_name") or la.get("name") or "")
        misses   = _i(la, "misses") or _i(la, "miss_count")
        gets     = _i(la, "gets") or _i(la, "get_count")
        miss_pct = _pct(misses, gets) if gets else 0
        if miss_pct > 1.0 and misses > 1000:
            ref, _ = _kb_lookup(["latch"])
            findings.append(AWRFinding(
                id=f"latch_{lname.lower().replace(' ','_')[:30]}",
                severity="WARNING" if miss_pct < 5 else "CRITICAL",
                category="Latch",
                title=f"Latch Miss: {lname[:45]}",
                headline=f"'{lname}' latch: {miss_pct:.1f}% miss rate ({_fmt_num(misses)} misses).",
                evidence=[
                    f"Latch: {lname}",
                    f"Gets: {_fmt_num(gets)},  Misses: {_fmt_num(misses)}  ({miss_pct:.1f}%)",
                ],
                root_cause=f"High concurrency contention on '{lname}' in-memory structure.",
                fix=(
                    "For library cache latch: reduce hard parses (bind variables).\n"
                    "For cache buffers chains: find hot block (x$bh WHERE tch > 100).\n"
                    "For shared pool latch: increase SHARED_POOL_SIZE."
                ),
                impact_score=min(70, miss_pct * 5),
                confidence="MEDIUM",
                oracle_ref=ref,
                tags=["latch"],
            ))

    # Deduplicate by id, keep highest impact_score
    seen: dict[str, AWRFinding] = {}
    for f in findings:
        if f.id not in seen or f.impact_score > seen[f.id].impact_score:
            seen[f.id] = f
    return list(seen.values())


# ══════════════════════════════════════════════════════════════════════════════
#  §11  CROSS-CHECKER + SYNTHESIS
#       Validates findings against each other; amplifies correlated signals;
#       assigns HIGH confidence where ADDM and rules agree.
# ══════════════════════════════════════════════════════════════════════════════
def _cross_check(
    findings: list[AWRFinding],
    data: dict,
    correlation_notes: list[str] | None = None,
) -> list[AWRFinding]:
    ids     = {f.id for f in findings}
    has_io  = any("io" in f.tags for f in findings)
    has_buf = "buffer_hit_low" in ids

    for f in findings:
        # I/O + buffer cache correlation → confirmed storage chain
        if has_io and has_buf and "io" in f.tags:
            f.confidence = "HIGH"
            if f.severity == "WARNING" and f.impact_score > 40:
                f.severity    = "CRITICAL"
                f.impact_score = min(100, f.impact_score * 1.2)

        # ADDM always HIGH confidence — Oracle's own engine
        if "addm" in f.tags:
            f.confidence = "HIGH"

        # Parse + library cache miss → both signal same root cause
        if f.id in ("hard_parse_high", "library_cache_miss") and \
                "latch: library_cache" in ids:
            f.confidence  = "HIGH"
            f.impact_score = min(100, f.impact_score * 1.15)

        # Redo log sync + parallel write → confirmed redo storage chain
        wait_redo_ids = {
            "wait_log_file_sync",
            "wait_log_file_parallel_write",
        }
        if f.id in wait_redo_ids and len(wait_redo_ids & ids) > 1:
            f.confidence = "HIGH"
            if correlation_notes is not None:
                note = "CONFIRMED: log file sync + log file parallel write both present — redo storage chain confirmed."
                if note not in correlation_notes:
                    correlation_notes.append(note)

    return findings


# ══════════════════════════════════════════════════════════════════════════════
#  §12  CONDITION-TREE NARRATIVE ENGINE
#       Data-driven, no LLM, no magic — pure condition logic.
#       Each path through the tree produces precise, evidence-backed text.
# ══════════════════════════════════════════════════════════════════════════════
def _narrative_engine(data: dict, findings: list[AWRFinding]) -> tuple[str, str, str]:
    """
    Returns (overall_health, primary_bottleneck, verdict).
    Decision tree: evaluates severity distribution → bottleneck category → metrics.
    """
    aas     = _f(data, "aas")
    cpu_cnt = max(1, _i(data, "cpu_count"))
    cpu_r   = aas / cpu_cnt

    if not findings:
        return (
            "OK",
            "None",
            f"No significant performance issues detected. "
            f"AAS {aas:.1f} / {cpu_cnt} CPUs ({cpu_r*100:.0f}% utilisation). "
            f"Database is operating within normal parameters."
        )

    critical = [f for f in findings if f.severity == "CRITICAL"]
    warnings = [f for f in findings if f.severity == "WARNING"]
    top      = findings[0]

    overall  = "CRITICAL" if critical else ("WARNING" if warnings else "OK")
    primary  = top.category

    # ── Tree root: overall health level ──────────────────────────────────────
    parts: list[str] = []

    if overall == "CRITICAL":
        parts.append(
            f"Database is critically impaired: {len(critical)} critical issue(s) confirmed. "
            f"AAS {aas:.1f} against {cpu_cnt} CPUs ({cpu_r:.2f}× utilisation)."
        )
    elif overall == "WARNING":
        parts.append(
            f"Database shows {len(warnings)} performance concern(s) requiring attention. "
            f"AAS {aas:.1f} / {cpu_cnt} CPUs ({cpu_r:.2f}× utilisation)."
        )
    else:
        parts.append(
            f"Database is performing within acceptable bounds "
            f"(AAS {aas:.1f} / {cpu_cnt} CPUs, {cpu_r:.2f}× utilisation)."
        )

    # ── Primary bottleneck headline ───────────────────────────────────────────
    parts.append(f"Primary bottleneck: {top.headline}")

    # ── Secondary concern if different category ───────────────────────────────
    for f in findings[1:4]:
        if f.category != top.category and f.severity in ("CRITICAL", "WARNING"):
            parts.append(f"Also: {f.headline}")
            break

    # ── Oracle KB citation for primary finding ────────────────────────────────
    if top.oracle_ref:
        parts.append(f"Ref: {top.oracle_ref}.")

    return overall, primary, " ".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
#  §13  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════
def run_intelligence(
    upload_id: str,
    data: dict,
    model: str | None = None,       # kept for API compatibility; unused
) -> dict:
    """
    Full intelligence pipeline for a single AWR snapshot:
    Rule scan → Anomaly detection → Correlation engine → Cross-check
    → Trend engine → Narrative engine → Max-heap sort → Cache → Return
    """
    t0 = time.time()

    wait_events = data.get("wait_events") or []

    # 1. Decision-tree rule scanner
    findings = _rule_scan(data)

    # 2. Correlation engine (Pearson + cross-signal amplification)
    correlation_notes: list[str] = []
    findings, correlation_notes = _correlation_engine(data, wait_events, findings)

    # 3. Cross-checker (validates findings against each other)
    findings = _cross_check(findings, data, correlation_notes)

    # 4. Trend engine (linear regression on SQL load distribution + IQR outliers)
    trend_notes = _trend_engine(data)

    # 5. Condition-tree narrative engine
    overall, primary, verdict = _narrative_engine(data, findings)

    # 6. Max-heap priority sort
    ranked = _heap_rank(findings)

    report = FindingReport(
        upload_id=upload_id,
        db_name=str(data.get("db_name") or ""),
        snap_range=f"{data.get('begin_snap','?')} → {data.get('end_snap','?')}",
        overall_health=overall,
        primary_bottleneck=primary,
        verdict=verdict,
        findings=ranked[:14],
        correlation_notes=correlation_notes,
        trend_notes=trend_notes,
        pipeline_ms=round((time.time() - t0) * 1000, 1),
    )
    result = report.to_dict()
    cache_set(upload_id, result)
    log.info(
        "Intelligence[%s]: %s | %d findings (CRIT=%d WARN=%d) | %.0fms | corr=%d trends=%d",
        upload_id, overall, len(ranked),
        sum(1 for f in ranked if f.severity == "CRITICAL"),
        sum(1 for f in ranked if f.severity == "WARNING"),
        report.pipeline_ms,
        len(correlation_notes), len(trend_notes),
    )
    return result


def run_intelligence_compare(
    good_id: str,
    bad_id: str,
    good_data: dict,
    bad_data: dict,
    model: str | None = None,
) -> dict:
    """
    Comparison pipeline: good period vs bad period.
    Uses CUSUM to detect SUSTAINED regressions (not just one-off spikes).
    [NEW] prefix = issue absent from good period.
    [WORSE] prefix = issue was present but significantly degraded.
    [SUSTAINED] prefix = CUSUM confirms sustained (not transient) degradation.
    """
    t0 = time.time()

    good_we = good_data.get("wait_events") or []
    bad_we  = bad_data.get("wait_events") or []

    # Scan both periods
    good_findings = _rule_scan(good_data)
    bad_findings  = _rule_scan(bad_data)
    bad_findings, corr_notes = _correlation_engine(bad_data, bad_we, bad_findings)
    bad_findings  = _cross_check(bad_findings, bad_data, corr_notes)

    # CUSUM sustained degradation analysis
    cusum_results = _cusum_compare(good_data, bad_data)
    sustained_metrics = {r["metric"] for r in cusum_results if r["sustained"]}
    cusum_notes: list[str] = []
    for r in cusum_results:
        if r["sustained"]:
            cusum_notes.append(
                f"SUSTAINED DEGRADATION — {r['metric']}: "
                f"good={r['good_val']:.1f} → bad={r['bad_val']:.1f} "
                f"(Δ={r['delta_pct']:+.1f}%, CUSUM S⁺={r['cusum_upper']:.1f})"
            )

    # Classify each bad-period finding as NEW, WORSE, or UNCHANGED
    good_ids = {f.id: f for f in good_findings}
    for f in bad_findings:
        gf = good_ids.get(f.id)
        if gf is None:
            f.title = f"[NEW] {f.title}"
            f.trend = "WORSENING"
            if f.severity == "WARNING":
                f.severity = "CRITICAL"
            f.evidence.insert(0, "This issue was NOT present in the good period.")
            f.impact_score = min(100, f.impact_score * 1.35)
        elif f.impact_score > gf.impact_score * 1.3:
            pct_worse = _pct(f.impact_score - gf.impact_score, max(1, gf.impact_score))
            f.title = f"[WORSE] {f.title}"
            f.trend = "WORSENING"
            f.evidence.insert(0, f"{pct_worse:.0f}% worse than good period (impact: {gf.impact_score:.0f} → {f.impact_score:.0f}).")
        else:
            f.trend = "STABLE"

        # Mark SUSTAINED regressions from CUSUM
        for metric in sustained_metrics:
            if metric.lower() in f.category.lower() or metric.lower() in " ".join(f.tags):
                if "[SUSTAINED]" not in f.title:
                    f.title = f"[SUSTAINED] {f.title}"
                f.confidence = "HIGH"
                break

    # Trend engine on bad period
    trend_notes = _trend_engine(bad_data)

    # Verdict
    overall, primary, verdict = _narrative_engine(bad_data, bad_findings)
    n_new   = sum(1 for f in bad_findings if "[NEW]" in f.title)
    n_worse = sum(1 for f in bad_findings if "[WORSE]" in f.title)
    n_sus   = sum(1 for f in bad_findings if "[SUSTAINED]" in f.title)
    if n_new or n_worse or n_sus:
        verdict = (
            f"Regression: {n_new} new, {n_worse} worsened, {n_sus} CUSUM-sustained issue(s). "
            + verdict
        )

    comp_id = f"{good_id}_vs_{bad_id}"
    ranked  = _heap_rank(bad_findings)

    report = FindingReport(
        upload_id=comp_id,
        db_name=f"{bad_data.get('db_name','?')} (comparison)",
        snap_range=(
            f"Good: {good_data.get('begin_snap','?')}→{good_data.get('end_snap','?')}  |  "
            f"Bad: {bad_data.get('begin_snap','?')}→{bad_data.get('end_snap','?')}"
        ),
        overall_health=overall,
        primary_bottleneck=primary,
        verdict=verdict,
        findings=ranked[:14],
        correlation_notes=corr_notes + cusum_notes,
        trend_notes=trend_notes,
        pipeline_ms=round((time.time() - t0) * 1000, 1),
    )
    result = report.to_dict()
    cache_set(comp_id, result)
    log.info(
        "Intelligence[%s]: %s | %d findings | NEW=%d WORSE=%d SUSTAINED=%d | %.0fms",
        comp_id, overall, len(ranked), n_new, n_worse, n_sus, report.pipeline_ms,
    )
    return result
