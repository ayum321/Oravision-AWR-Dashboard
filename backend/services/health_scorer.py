"""Health scoring engine for Oracle AWR data.

Evaluates AWR metrics against Oracle best-practice thresholds and produces
an overall health score (0-100), letter grade, severity, per-metric alerts,
and a detailed checklist of health checks with remediation advice.
"""
from __future__ import annotations

from typing import Any

from models.snapshot import AWRData, InstanceEfficiency, WaitEvent


# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------

_METRIC_THRESHOLDS: dict[str, dict[str, Any]] = {
    "buffer_cache_hit_pct": {
        "metric": "Buffer Cache Hit Ratio",
        "critical_threshold": 90.0,
        "warning_threshold": 95.0,
        "good_threshold": 99.0,
        "higher_is_worse": False,
    },
    "hard_parse_pct": {
        "metric": "Hard Parse %",
        "critical_threshold": 30.0,
        "warning_threshold": 10.0,
        "good_threshold": 5.0,
        "higher_is_worse": True,
    },
    "top_wait_pct_db_time": {
        "metric": "Top Wait Event % of DB Time",
        "critical_threshold": 50.0,
        "warning_threshold": 30.0,
        "good_threshold": 10.0,
        "higher_is_worse": True,
    },
    "latch_hit_pct": {
        "metric": "Latch Hit %",
        "critical_threshold": 98.0,
        "warning_threshold": 99.0,
        "good_threshold": 99.9,
        "higher_is_worse": False,
    },
    "avg_sql_elapsed_secs": {
        "metric": "Average SQL Elapsed Time (secs)",
        "critical_threshold": 5.0,
        "warning_threshold": 2.0,
        "good_threshold": 0.5,
        "higher_is_worse": True,
    },
    "phys_reads_per_sec": {
        "metric": "Physical Reads / sec",
        "critical_threshold": 10000.0,
        "warning_threshold": 5000.0,
        "good_threshold": 1000.0,
        "higher_is_worse": True,
    },
    "cpu_busy_pct": {
        "metric": "CPU Usage %",
        "critical_threshold": 95.0,
        "warning_threshold": 85.0,
        "good_threshold": 50.0,
        "higher_is_worse": True,
    },
    "disk_io_wait_pct": {
        "metric": "Disk I/O Wait % of DB Time",
        "critical_threshold": 50.0,
        "warning_threshold": 30.0,
        "good_threshold": 10.0,
        "higher_is_worse": True,
    },
    "log_file_sync_ms": {
        "metric": "Log File Sync Avg Wait (ms)",
        "critical_threshold": 50.0,
        "warning_threshold": 20.0,
        "good_threshold": 5.0,
        "higher_is_worse": True,
    },
    "soft_parse_pct": {
        "metric": "Soft Parse %",
        "critical_threshold": 70.0,
        "warning_threshold": 85.0,
        "good_threshold": 95.0,
        "higher_is_worse": False,
    },
    "db_cpu_pct_db_time": {
        "metric": "DB CPU % of DB Time",
        "critical_threshold": 95.0,
        "warning_threshold": 80.0,
        "good_threshold": 50.0,
        "higher_is_worse": True,
    },
}


def get_metric_thresholds() -> dict[str, dict[str, Any]]:
    """Return the full threshold configuration for every tracked metric."""
    return {k: dict(v) for k, v in _METRIC_THRESHOLDS.items()}


# ---------------------------------------------------------------------------
# Helpers – extract derived values from the raw AWR dict
# ---------------------------------------------------------------------------

def _safe_get(d: dict, *keys: str, default: Any = 0.0) -> Any:
    """Drill into nested dicts safely."""
    current = d
    for k in keys:
        if isinstance(current, dict):
            current = current.get(k, default)
        else:
            return default
    return current


def _extract_metrics(data: dict) -> dict[str, float | None]:
    """Derive all scorable metrics from the raw AWR data dict.

    Returns ``None`` for metrics whose source data is absent — callers MUST
    skip scoring for ``None`` values (missing ≠ zero).
    """
    efficiency = data.get("efficiency", {})
    os_stats = data.get("os_stats", {})
    wait_events: list[dict] = data.get("wait_events", [])
    load_profile: list[dict] = data.get("load_profile", [])
    sql_stats: list[dict] = data.get("sql_stats", [])
    declared_efficiency_available = data.get("efficiency_available")
    efficiency_available = (
        set(declared_efficiency_available)
        if isinstance(declared_efficiency_available, list)
        else None
    )

    def _efficiency_value(metric: str) -> float | None:
        if efficiency_available is not None and metric not in efficiency_available:
            return None
        if efficiency and metric in efficiency:
            return float(efficiency[metric])
        return None

    # Buffer cache — None if efficiency section absent
    buffer_cache = _efficiency_value("buffer_cache_hit_pct")

    # Parse ratios — None if absent
    soft_parse_pct = _efficiency_value("soft_parse_pct")
    hard_parse_pct: float | None = None
    if soft_parse_pct is not None:
        hard_parse_pct = max(0.0, 100.0 - soft_parse_pct)

    # Latch — None if absent
    latch_hit_pct = _efficiency_value("latch_hit_pct")

    # Top wait event — None if no wait events parsed
    top_wait_pct: float | None = None
    if wait_events:
        non_cpu_events = [
            float(w.get("pct_db_time", 0.0))
            for w in wait_events
            if w.get("event_name", "").lower() not in ("db cpu", "cpu")
                and w.get("wait_class", "").lower() != "cpu"
        ]
        if non_cpu_events:
            top_wait_pct = max(non_cpu_events)

    # Average SQL elapsed time — None if no SQL stats parsed
    avg_sql_elapsed: float | None = None
    if sql_stats:
        total_elapsed = sum(float(s.get("elapsed_time_secs", 0.0)) for s in sql_stats)
        total_execs = sum(int(s.get("executions", 0)) for s in sql_stats)
        if total_execs > 0:
            avg_sql_elapsed = total_elapsed / total_execs

    # Physical reads / sec from load profile — None if not found
    phys_reads_per_sec: float | None = None
    for lp in load_profile:
        if "physical read" in lp.get("stat_name", "").lower():
            phys_reads_per_sec = float(lp.get("per_sec", 0.0))
            break

    # CPU — None if os_stats absent
    cpu_busy_pct: float | None = None
    if os_stats and "cpu_busy_pct" in os_stats:
        cpu_busy_pct = float(os_stats["cpu_busy_pct"])

    # Disk I/O wait % — None if no wait events
    disk_io_pct: float | None = None
    if wait_events:
        disk_io_pct = sum(
            float(w.get("pct_db_time", 0.0))
            for w in wait_events
            if w.get("wait_class", "").lower() in ("user i/o", "system i/o")
        )

    # Log file sync avg wait — None if event not present
    log_file_sync_ms: float | None = None
    for w in wait_events:
        if "log file sync" in w.get("event_name", "").lower():
            log_file_sync_ms = float(w.get("avg_wait_ms", 0.0))
            break

    # DB CPU % of DB time — None if time model absent
    db_cpu_pct: float | None = None
    time_model: list[dict] = data.get("time_model", [])
    for tm in time_model:
        if tm.get("stat_name", "").lower() in ("db cpu", "db cpu time"):
            db_cpu_pct = float(tm.get("pct_db_time", 0.0))
            break

    # Wait event count (distinct events with nonzero waits)
    wait_event_count = sum(1 for w in wait_events if int(w.get("total_waits", 0)) > 0)

    return {
        "buffer_cache_hit_pct": buffer_cache,
        "hard_parse_pct": hard_parse_pct,
        "soft_parse_pct": soft_parse_pct,
        "top_wait_pct_db_time": top_wait_pct,
        "latch_hit_pct": latch_hit_pct,
        "avg_sql_elapsed_secs": avg_sql_elapsed,
        "phys_reads_per_sec": phys_reads_per_sec,
        "cpu_busy_pct": cpu_busy_pct,
        "disk_io_wait_pct": disk_io_pct,
        "log_file_sync_ms": log_file_sync_ms,
        "db_cpu_pct_db_time": db_cpu_pct,
        "wait_event_count": wait_event_count,
    }


# ---------------------------------------------------------------------------
# Single-metric evaluator
# ---------------------------------------------------------------------------

def evaluate_metric(metric_name: str, value: float) -> dict[str, Any]:
    """Evaluate a single metric against its thresholds.

    Returns ``{"severity": str, "message": str, "score_impact": int}``.
    """
    cfg = _METRIC_THRESHOLDS.get(metric_name)
    if cfg is None:
        return {"severity": "unknown", "message": f"No thresholds defined for {metric_name}", "score_impact": 0}

    higher_is_worse = cfg["higher_is_worse"]
    critical = cfg["critical_threshold"]
    warning = cfg["warning_threshold"]
    good = cfg["good_threshold"]
    label = cfg["metric"]

    if higher_is_worse:
        if value >= critical:
            return {
                "severity": "critical",
                "message": f"{label} is {value:.2f} (critical >= {critical})",
                "score_impact": -25,
            }
        if value >= warning:
            return {
                "severity": "warning",
                "message": f"{label} is {value:.2f} (warning >= {warning})",
                "score_impact": -10,
            }
        if value <= good:
            return {
                "severity": "good",
                "message": f"{label} is {value:.2f} (good <= {good})",
                "score_impact": 5,
            }
    else:
        if value < critical:
            return {
                "severity": "critical",
                "message": f"{label} is {value:.2f}% (critical < {critical})",
                "score_impact": -25,
            }
        if value < warning:
            return {
                "severity": "warning",
                "message": f"{label} is {value:.2f}% (warning < {warning})",
                "score_impact": -10,
            }
        if value >= good:
            return {
                "severity": "good",
                "message": f"{label} is {value:.2f}% (good >= {good})",
                "score_impact": 5,
            }

    return {"severity": "ok", "message": f"{label} is {value:.2f} (within normal range)", "score_impact": 0}


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def calculate_health_score(data: dict) -> dict[str, Any]:
    """Calculate an overall health score from AWR data.

    Uses a deduction-based formula starting at 100 and subtracting points
    for each threshold breach.

    Returns::

        {
            "score": int,        # 0-100
            "grade": str,        # A/B/C/D/F
            "severity": str,     # healthy / degraded / critical
            "alerts": [{"metric": str, "severity": str, "message": str, "score_impact": int}, ...],
        }
    """
    metrics = _extract_metrics(data)
    alerts: list[dict[str, Any]] = []
    deductions: int = 0
    skipped_checks: list[str] = []  # Track metrics unavailable in this report

    # --- Buffer cache hit % ---
    buffer_cache = metrics.get("buffer_cache_hit_pct")
    if buffer_cache is None:
        skipped_checks.append("Buffer Cache Hit Ratio (data unavailable)")
    elif buffer_cache < 80:
        deductions -= 10   # was -30 — reduced: low hit ratio is a secondary signal
        alerts.append({
            "metric": "Buffer Cache Hit Ratio",
            "severity": "warning",
            "message": (
                f"Buffer Cache Hit Ratio is {buffer_cache:.2f}% — unusually low, may indicate SGA undersizing. "
                "NOTE: This metric alone is not diagnostic. A 99% ratio can coexist with a slow system. "
                "Correlate with physical read wait events and segment statistics."
            ),
            "score_impact": -10,
        })

    # --- Hard parse / sec ---
    # hard_parse_pct is derived as 100 - soft_parse_pct; approximate hard parses/sec
    # from load_profile if available, otherwise use hard_parse_pct as proxy
    load_profile: list[dict] = data.get("load_profile", [])
    hard_parses_per_sec = 0.0
    for lp in load_profile:
        if "hard parse" in lp.get("stat_name", "").lower():
            hard_parses_per_sec = float(lp.get("per_sec", 0.0))
            break
    if hard_parses_per_sec > 500:
        deductions -= 25
        alerts.append({
            "metric": "Hard Parses/sec",
            "severity": "critical",
            "message": f"Hard parses/sec is {hard_parses_per_sec:.1f} (critical > 500)",
            "score_impact": -25,
        })
    elif hard_parses_per_sec > 100:
        deductions -= 15
        alerts.append({
            "metric": "Hard Parses/sec",
            "severity": "warning",
            "message": f"Hard parses/sec is {hard_parses_per_sec:.1f} (warning > 100)",
            "score_impact": -15,
        })

    # --- Soft parse % ---
    soft_parse = metrics.get("soft_parse_pct")
    if soft_parse is None:
        skipped_checks.append("Soft Parse % (data unavailable)")
    elif soft_parse < 90:
        deductions -= 15
        alerts.append({
            "metric": "Soft Parse %",
            "severity": "warning",
            "message": f"Soft Parse % is {soft_parse:.2f}% (warning < 90%)",
            "score_impact": -15,
        })

    # --- Top wait event % of DB time ---
    top_wait = metrics.get("top_wait_pct_db_time")
    if top_wait is None:
        skipped_checks.append("Top Wait Event % (no wait events parsed)")
    else:
        top_wait_event_name = ""
        wait_events_hs: list[dict] = data.get("wait_events", [])
        best_pct = 0.0
        for w in wait_events_hs:
            wn = w.get("event_name", "").lower()
            if wn not in ("db cpu", "cpu") and w.get("wait_class", "").lower() != "cpu":
                pct = float(w.get("pct_db_time", 0.0))
                if pct > best_pct:
                    best_pct = pct
                    top_wait_event_name = wn

        _NORMAL_WAITS = {
            "log file sync", "db file sequential read", "db file scattered read",
            "direct path read", "direct path write", "direct path read temp",
            "sql*net message from client", "sql*net more data from client",
        }
        is_normal_wait = top_wait_event_name in _NORMAL_WAITS

        if top_wait > 60:
            if is_normal_wait:
                deductions -= 15
                alerts.append({
                    "metric": "Top Wait Event % of DB Time",
                    "severity": "warning",
                    "message": f"Top wait event '{top_wait_event_name}' is {top_wait:.2f}% of DB time (operational wait > 60%)",
                    "score_impact": -15,
                })
            else:
                deductions -= 30
                alerts.append({
                    "metric": "Top Wait Event % of DB Time",
                    "severity": "critical",
                    "message": f"Top wait event '{top_wait_event_name}' is {top_wait:.2f}% of DB time (critical > 60%)",
                    "score_impact": -30,
                })
        elif top_wait > 40:
            deductions -= 20
            alerts.append({
                "metric": "Top Wait Event % of DB Time",
                "severity": "warning",
                "message": f"Top wait event '{top_wait_event_name}' is {top_wait:.2f}% of DB time (warning > 40%)",
                "score_impact": -20,
            })

    # --- Latch hit % ---
    latch_hit = metrics.get("latch_hit_pct")
    if latch_hit is None:
        skipped_checks.append("Latch Hit % (data unavailable)")
    elif latch_hit < 98:
        deductions -= 20
        alerts.append({
            "metric": "Latch Hit %",
            "severity": "critical",
            "message": f"Latch Hit % is {latch_hit:.2f}% (critical < 98%)",
            "score_impact": -20,
        })
    elif latch_hit < 99:
        deductions -= 10
        alerts.append({
            "metric": "Latch Hit %",
            "severity": "warning",
            "message": f"Latch Hit % is {latch_hit:.2f}% (warning < 99%)",
            "score_impact": -10,
        })

    # --- Any SQL avg elapsed ---
    # Use only completed SQL (execs > 0) for avg elapsed scoring.
    # Running SQLs (execs=0) are long-running batch/PQ slaves where
    # avg_elapsed = total elapsed, which would unfairly inflate the metric.
    # To avoid penalizing a single long-running batch query, look at the
    # number of SQL statements exceeding the threshold — systemic issue is
    # worse than a single outlier.
    sql_stats: list[dict] = data.get("sql_stats", [])
    max_avg_elapsed = 0.0
    high_elapsed_count = 0
    for s in sql_stats:
        execs = int(s.get("executions", 0))
        if execs > 0:
            avg_e = float(s.get("avg_elapsed_secs", 0.0))
            if avg_e > max_avg_elapsed:
                max_avg_elapsed = avg_e
            if avg_e > 30:
                high_elapsed_count += 1
    if high_elapsed_count >= 3:
        # Multiple slow SQLs — systemic issue
        deductions -= 20
        alerts.append({
            "metric": "Max SQL Avg Elapsed Time",
            "severity": "critical",
            "message": f"{high_elapsed_count} SQLs with avg elapsed > 30s (worst: {max_avg_elapsed:.2f}s)",
            "score_impact": -20,
        })
    elif max_avg_elapsed > 30 and high_elapsed_count <= 1:
        # Single slow SQL — likely a batch query, moderate penalty
        deductions -= 10
        alerts.append({
            "metric": "Max SQL Avg Elapsed Time",
            "severity": "warning",
            "message": f"Single SQL avg elapsed {max_avg_elapsed:.2f}s (likely batch query, warning > 30s)",
            "score_impact": -10,
        })
    elif max_avg_elapsed > 5:
        deductions -= 10
        alerts.append({
            "metric": "Max SQL Avg Elapsed Time",
            "severity": "warning",
            "message": f"SQL avg elapsed {max_avg_elapsed:.2f}s (warning > 5s)",
            "score_impact": -10,
        })

    # --- CPU % of DB time ---
    db_cpu_pct = metrics.get("db_cpu_pct_db_time")
    if db_cpu_pct is None:
        skipped_checks.append("DB CPU % of DB Time (time model unavailable)")
    elif db_cpu_pct > 80:
        deductions -= 10
        alerts.append({
            "metric": "DB CPU % of DB Time",
            "severity": "warning",
            "message": f"CPU is {db_cpu_pct:.2f}% of DB time (warning > 80%)",
            "score_impact": -10,
        })

    # --- Critical wait events present in this snapshot ---
    wait_events: list[dict] = data.get("wait_events", [])
    critical_wait_deduction = 0
    for w in wait_events:
        event_name = w.get("event_name", "").lower()
        pct = float(w.get("pct_db_time", 0.0))
        if pct > 10.0 and event_name in (
            "enq: tx - row lock", "enq: tx - row lock contention",
            "gc buffer busy", "gc buffer busy acquire", "gc buffer busy release",
            "buffer busy waits", "free buffer waits",
            "latch: shared pool", "latch: cache buffers chains",
            "latch: redo allocation", "latch free",
            "library cache lock", "library cache pin",
            "log buffer space",
            "enq: hw - contention", "enq: sq - contention",
            "cursor: pin s wait on x", "row cache lock",
            "read by other session",
        ):
            critical_wait_deduction -= 5
            if critical_wait_deduction <= -20:
                critical_wait_deduction = -20
                break
    if critical_wait_deduction < 0:
        deductions += critical_wait_deduction
        alerts.append({
            "metric": "Critical Wait Events",
            "severity": "warning",
            "message": f"Critical wait events detected ({abs(critical_wait_deduction)} point deduction)",
            "score_impact": critical_wait_deduction,
        })

    # --- AAS / CPU ratio (Active Average Sessions vs available CPUs) ---
    # AAS >> CPUs indicates database demand exceeds CPU capacity.
    # This is database-level evidence only — OS-level run-queue or CPU
    # saturation requires host metrics (vmstat, mpstat) for confirmation.
    db_info = data.get("db_info", {})
    os_stats_data = data.get("os_stats", {})
    snapshot_data = data.get("snapshot", {})
    cpu_count = int(
        db_info.get("cpu_count", 0)
        or os_stats_data.get("num_cpus", 0)
        or snapshot_data.get("cpus", 0)
        or data.get("cpus", 0)
        or 0
    )
    aas = 0.0
    load_profile_lp: list[dict] = data.get("load_profile", [])
    for lp in load_profile_lp:
        sn = lp.get("stat_name", "").lower()
        if "db time" in sn:
            aas = float(lp.get("per_sec", 0.0))
            break
    if cpu_count > 0 and aas > 0:
        aas_cpu_ratio = aas / cpu_count
        if aas_cpu_ratio > 5:
            deductions -= 25
            alerts.append({
                "metric": "AAS/CPU Ratio",
                "severity": "critical",
                "message": (
                    f"AAS={aas:.1f} on {cpu_count} CPUs ({aas_cpu_ratio:.1f}x) — "
                    "database demand far exceeds CPU capacity. "
                    "Verify with host OS metrics (vmstat/mpstat) for run-queue confirmation."
                ),
                "score_impact": -25,
            })
        elif aas_cpu_ratio > 2:
            deductions -= 15
            alerts.append({
                "metric": "AAS/CPU Ratio",
                "severity": "warning",
                "message": (
                    f"AAS={aas:.1f} on {cpu_count} CPUs ({aas_cpu_ratio:.1f}x) — "
                    "database demand pressure elevated. Check host CPU with OS metrics."
                ),
                "score_impact": -15,
            })
        elif aas_cpu_ratio > 1.5:
            deductions -= 10
            alerts.append({
                "metric": "AAS/CPU Ratio",
                "severity": "warning",
                "message": (
                    f"AAS={aas:.1f} on {cpu_count} CPUs ({aas_cpu_ratio:.1f}x) — "
                    "approaching CPU capacity; monitor trend."
                ),
                "score_impact": -10,
            })

    # Compute final score
    score = max(0, 100 + deductions)

    # Grade mapping
    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 50:
        grade = "D"
    else:
        grade = "F"

    # Severity mapping
    if score >= 80:
        severity = "healthy"
    elif score >= 50:
        severity = "degraded"
    else:
        severity = "critical"

    # Sort alerts: critical first, then warning, by absolute impact descending
    alerts.sort(key=lambda a: (0 if a["severity"] == "critical" else 1, a["score_impact"]))

    return {
        "score": score,
        "grade": grade,
        "severity": severity,
        "alerts": alerts,
        "skipped_checks": skipped_checks,
        "deductions": [
            {
                "metric": a["metric"],
                "impact": a["score_impact"],
                "message": a["message"],
                "points": abs(a["score_impact"]),
                "reason": a["message"],
            }
            for a in alerts if a["score_impact"] < 0
        ],
    }


# ---------------------------------------------------------------------------
# Detailed health-check builder
# ---------------------------------------------------------------------------

_FIX_ADVICE: dict[str, str] = {
    "buffer_cache_hit_pct": (
        "Increase DB_CACHE_SIZE or SGA_TARGET. Identify SQL with excessive "
        "physical reads using AWR SQL Ordered by Reads and add appropriate indexes."
    ),
    "hard_parse_pct": (
        "Enable CURSOR_SHARING=FORCE as a short-term fix. Long-term, use bind "
        "variables in application SQL. Review V$SQL_SHARED_CURSOR for invalidation causes."
    ),
    "soft_parse_pct": (
        "Use bind variables and session-cached cursors (SESSION_CACHED_CURSORS). "
        "Set CURSOR_SHARING=FORCE if application cannot be changed immediately."
    ),
    "top_wait_pct_db_time": (
        "Investigate the top wait event. If it is 'db file sequential read', add "
        "indexes or increase buffer cache. If 'log file sync', tune redo log I/O. "
        "If 'enq: TX - row lock contention', review application concurrency."
    ),
    "latch_hit_pct": (
        "Identify hot latches with V$LATCH. Common culprits: shared pool latch "
        "(increase SHARED_POOL_SIZE or use bind variables), cache buffers chains "
        "(reduce hot-block contention or partition hot tables)."
    ),
    "avg_sql_elapsed_secs": (
        "Identify top SQL by elapsed time in AWR. Check execution plans for "
        "full table scans, Cartesian joins, or plan regressions. Use SQL Plan "
        "Baselines to stabilize good plans."
    ),
    "phys_reads_per_sec": (
        "Increase buffer cache size. Identify segments with highest physical reads "
        "in AWR Segments Statistics and add indexes or partition large tables. "
        "Consider using result cache for repeated queries."
    ),
    "cpu_busy_pct": (
        "Identify CPU-intensive SQL in AWR (SQL Ordered by CPU). Check for "
        "unnecessary parsing, PL/SQL loops, or missing indexes causing excessive "
        "logical reads. Consider Resource Manager to limit runaway sessions."
    ),
    "disk_io_wait_pct": (
        "Verify storage performance (latency < 5ms for SSD, < 10ms for HDD). "
        "Move datafiles to faster storage. Use ASM disk group rebalancing. "
        "Increase buffer cache to reduce physical I/O."
    ),
    "log_file_sync_ms": (
        "Move redo logs to low-latency storage (battery-backed write cache or NVMe). "
        "Reduce COMMIT frequency by batching DML. Check for redo log sizing – "
        "switch frequency should be < 3 per hour."
    ),
    "db_cpu_pct_db_time": (
        "High DB CPU % is normal for well-tuned OLTP. If response time is "
        "acceptable, no action needed. If CPU is saturated, tune top SQL or "
        "scale CPUs."
    ),
}


def build_health_checks(data: dict) -> list[dict[str, Any]]:
    """Build a comprehensive checklist of health checks with remediation advice.

    Each item::

        {
            "category": str,
            "check": str,
            "status": "PASS" | "WARN" | "FAIL",
            "value": str,
            "threshold": str,
            "detail": str,
            "fix": str,
            "priority": int,   # 1 = highest
        }
    """
    metrics = _extract_metrics(data)
    checks: list[dict[str, Any]] = []

    def _add(
        category: str,
        check: str,
        metric_key: str,
        value: float | None,
        fmt: str = ".2f",
        suffix: str = "",
    ) -> None:
        if value is None:
            checks.append({
                "category": category,
                "check": check,
                "status": "SKIP",
                "value": "N/A",
                "threshold": "",
                "detail": "Data unavailable in this AWR report",
                "fix": "",
                "priority": 4,
            })
            return
        result = evaluate_metric(metric_key, value)
        severity = result["severity"]
        if severity == "critical":
            status, priority = "FAIL", 1
        elif severity == "warning":
            status, priority = "WARN", 2
        else:
            status, priority = "PASS", 3

        cfg = _METRIC_THRESHOLDS.get(metric_key, {})
        higher_is_worse = cfg.get("higher_is_worse", True)
        if higher_is_worse:
            threshold_str = (
                f"critical >= {cfg.get('critical_threshold')}, "
                f"warning >= {cfg.get('warning_threshold')}"
            )
        else:
            threshold_str = (
                f"critical < {cfg.get('critical_threshold')}, "
                f"warning < {cfg.get('warning_threshold')}"
            )

        checks.append({
            "category": category,
            "check": check,
            "status": status,
            "value": f"{value:{fmt}}{suffix}",
            "threshold": threshold_str,
            "detail": result["message"],
            "fix": _FIX_ADVICE.get(metric_key, "Review Oracle AWR documentation for this metric."),
            "priority": priority,
        })

    # -- Memory --------------------------------------------------------
    _add("Memory", "Buffer Cache Hit Ratio", "buffer_cache_hit_pct",
         metrics["buffer_cache_hit_pct"], suffix="%")

    # -- Parse ---------------------------------------------------------
    _add("Parse", "Hard Parse Ratio", "hard_parse_pct",
         metrics["hard_parse_pct"], suffix="%")

    _add("Parse", "Soft Parse Ratio", "soft_parse_pct",
         metrics["soft_parse_pct"], suffix="%")

    # -- IO ------------------------------------------------------------
    _add("IO", "Physical Reads / sec", "phys_reads_per_sec",
         metrics["phys_reads_per_sec"], fmt=".0f")

    _add("IO", "Disk I/O Wait % of DB Time", "disk_io_wait_pct",
         metrics["disk_io_wait_pct"], suffix="%")

    # -- Concurrency ---------------------------------------------------
    _add("Concurrency", "Latch Hit Ratio", "latch_hit_pct",
         metrics["latch_hit_pct"], suffix="%")

    _add("Concurrency", "Top Wait Event % of DB Time", "top_wait_pct_db_time",
         metrics["top_wait_pct_db_time"], suffix="%")

    # -- Redo ----------------------------------------------------------
    _add("Redo", "Log File Sync Average Wait", "log_file_sync_ms",
         metrics["log_file_sync_ms"], suffix=" ms")

    # -- Capacity ------------------------------------------------------
    _add("Capacity", "Host CPU Usage", "cpu_busy_pct",
         metrics["cpu_busy_pct"], suffix="%")

    _add("Capacity", "DB CPU % of DB Time", "db_cpu_pct_db_time",
         metrics["db_cpu_pct_db_time"], suffix="%")

    # -- SQL -----------------------------------------------------------
    _add("SQL", "Average SQL Elapsed Time", "avg_sql_elapsed_secs",
         metrics["avg_sql_elapsed_secs"], suffix=" s")

    # Sort by priority (FAIL first), then category
    checks.sort(key=lambda c: (c["priority"], c["category"]))

    return checks
