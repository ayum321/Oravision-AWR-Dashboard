"""
Auto-Recommendation Engine for Oracle AWR Analysis
====================================================
Analyzes AWR data and produces prioritized, actionable recommendations
based on instance efficiency ratios, wait events, load profile metrics,
OS statistics, and (optionally) comparison deltas between good and bad periods.
"""
from __future__ import annotations

import logging
from typing import Any

from models.comparison import Recommendation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_load_metric(data: dict, name: str) -> float:
    """Return the per-second value of a load profile metric by stat_name."""
    for m in data.get("load_profile", []):
        stat = m.get("stat_name", "") if isinstance(m, dict) else getattr(m, "stat_name", "")
        if stat.lower().strip() == name.lower().strip():
            return m.get("per_sec", 0.0) if isinstance(m, dict) else getattr(m, "per_sec", 0.0)
    return 0.0


def _get_efficiency(data: dict, field: str) -> float:
    """Return an instance efficiency percentage (0-100)."""
    eff = data.get("efficiency", {})
    if isinstance(eff, dict):
        return eff.get(field, 0.0)
    return getattr(eff, field, 0.0)


def _get_os(data: dict, field: str) -> float:
    """Return an OS-level statistic."""
    os_stats = data.get("os_stats", {})
    if isinstance(os_stats, dict):
        return os_stats.get(field, 0.0)
    return getattr(os_stats, field, 0.0)


def _get_cpus(data: dict) -> int:
    cpus = data.get("cpus", 0)
    if cpus:
        return int(cpus)
    return int(_get_os(data, "num_cpus")) or 1


def _get_wait_event(data: dict, event_pattern: str) -> dict | None:
    """Find a wait event by partial name match (case-insensitive)."""
    pattern = event_pattern.lower()
    for ev in data.get("wait_events", []):
        name = ev.get("event_name", "") if isinstance(ev, dict) else getattr(ev, "event_name", "")
        if pattern in name.lower():
            return ev if isinstance(ev, dict) else ev.dict() if hasattr(ev, "dict") else ev.model_dump()
    return None


def _get_wait_pct(data: dict, event_pattern: str) -> float:
    """Return pct_db_time for a wait event matching the pattern."""
    ev = _get_wait_event(data, event_pattern)
    if ev:
        return ev.get("pct_db_time", 0.0)
    return 0.0


def _get_wait_avg_ms(data: dict, event_pattern: str) -> float:
    """Return avg_wait_ms for a wait event matching the pattern."""
    ev = _get_wait_event(data, event_pattern)
    if ev:
        return ev.get("avg_wait_ms", 0.0)
    return 0.0


def _aas(data: dict) -> float:
    """Compute Average Active Sessions = db_time_min / elapsed_min."""
    elapsed = data.get("elapsed_min", 0.0)
    db_time = data.get("db_time_min", 0.0)
    if elapsed and elapsed > 0:
        return db_time / elapsed
    return 0.0


def _severity_score(rec: Recommendation) -> float:
    """Produce a numeric sort key: lower priority number first, then
    critical-sounding findings rank higher (heuristic)."""
    # Weight by priority: p1=0, p2=100, p3=200  (lower is worse)
    return rec.priority * 100


# ---------------------------------------------------------------------------
# Core rule engine
# ---------------------------------------------------------------------------

def generate_recommendations(
    good_data: dict | None,
    bad_data: dict,
    comparison: dict | None = None,
) -> list[Recommendation]:
    """Analyze AWR data and produce prioritized recommendations.

    Parameters
    ----------
    good_data : dict | None
        Parsed AWR data for the "good" / baseline period.  May be *None*
        when analysing a single report.
    bad_data : dict
        Parsed AWR data for the "bad" / problem period.
    comparison : dict | None
        Pre-computed comparison results from the comparator service.
        When available, delta-based recommendations are generated.

    Returns
    -------
    list[Recommendation]
        Recommendations sorted by priority (1 first), then severity.
    """
    recs: list[Recommendation] = []

    # -----------------------------------------------------------------
    # 1. HIGH HARD PARSE
    # -----------------------------------------------------------------
    hard_parse_per_sec = _get_load_metric(bad_data, "Hard Parse Count")
    if hard_parse_per_sec == 0.0:
        hard_parse_per_sec = _get_load_metric(bad_data, "Hard parses")
    soft_parse_pct = _get_efficiency(bad_data, "soft_parse_pct")

    if hard_parse_per_sec > 100 or (soft_parse_pct > 0 and soft_parse_pct < 90):
        trigger_detail = (
            f"Hard parse count is {hard_parse_per_sec:.1f}/sec "
            f"(soft parse ratio {soft_parse_pct:.1f}%), indicating excessive "
            f"literal SQL or insufficient cursor reuse."
        )
        recs.append(Recommendation(
            priority=1,
            category="SQL",
            finding=trigger_detail,
            action="Enable cursor_sharing=FORCE or rewrite application to use bind variables",
            oracle_fix="ALTER SYSTEM SET cursor_sharing=FORCE SCOPE=BOTH;",
            impact="Reduces CPU load and shared pool latch contention",
            reference="V$SYSSTAT 'parse count (hard)', Instance Efficiency",
        ))

    # -----------------------------------------------------------------
    # 2. BUFFER CACHE MISS
    # -----------------------------------------------------------------
    buffer_hit = _get_efficiency(bad_data, "buffer_cache_hit_pct")
    if 0 < buffer_hit < 95:
        recs.append(Recommendation(
            priority=1,
            category="Memory",
            finding=(
                f"Buffer cache hit ratio is {buffer_hit:.1f}%, below the "
                f"95% threshold.  Physical reads are consuming I/O bandwidth."
            ),
            action="Increase db_cache_size based on V$DB_CACHE_ADVICE",
            oracle_fix="ALTER SYSTEM SET db_cache_size=XG SCOPE=BOTH;",
            impact="Reduces physical reads and db file sequential/scattered read waits",
            reference="Instance Efficiency, V$DB_CACHE_ADVICE",
        ))

    # -----------------------------------------------------------------
    # 3. HIGH LOG FILE SYNC
    # -----------------------------------------------------------------
    log_sync_ms = _get_wait_avg_ms(bad_data, "log file sync")
    if log_sync_ms > 10:
        recs.append(Recommendation(
            priority=1,
            category="I/O",
            finding=(
                f"Log file sync average wait is {log_sync_ms:.1f}ms, exceeding "
                f"the 10ms threshold.  Commit latency is elevated."
            ),
            action="Move redo logs to faster storage or reduce commit frequency",
            oracle_fix=(
                "-- Move redo logs to SSD/flash\n"
                "-- Consider COMMIT WRITE BATCH NOWAIT for non-critical transactions"
            ),
            impact="Reduces commit latency and session queuing",
            reference="Top Timed Events, V$EVENT_HISTOGRAM",
        ))

    # -----------------------------------------------------------------
    # 4. HIGH PHYSICAL READS
    # -----------------------------------------------------------------
    seq_read_ms = _get_wait_avg_ms(bad_data, "db file sequential read")
    phys_reads_per_sec = _get_load_metric(bad_data, "Physical Reads")
    if phys_reads_per_sec == 0.0:
        phys_reads_per_sec = _get_load_metric(bad_data, "Physical reads")

    if seq_read_ms > 20 or phys_reads_per_sec > 5000:
        details = []
        if seq_read_ms > 20:
            details.append(f"db file sequential read avg {seq_read_ms:.1f}ms (>20ms)")
        if phys_reads_per_sec > 5000:
            details.append(f"physical reads {phys_reads_per_sec:.0f}/sec (>5000)")
        recs.append(Recommendation(
            priority=2,
            category="I/O",
            finding=f"High physical I/O detected: {'; '.join(details)}.",
            action="Check missing indexes, run SQL Tuning Advisor",
            oracle_fix="SELECT * FROM TABLE(DBMS_SQLTUNE.REPORT_TUNING_TASK('task_name'));",
            impact="Reduces I/O wait time and improves SQL response time",
            reference="Top Timed Events, V$SQLSTATS",
        ))

    # -----------------------------------------------------------------
    # 5. PGA PRESSURE
    # -----------------------------------------------------------------
    free_mem_gb = _get_os(bad_data, "free_mem_gb")
    phys_mem_gb = _get_os(bad_data, "phys_mem_gb")
    pga_waits = _get_wait_pct(bad_data, "pga")
    mem_free_pct = (free_mem_gb / phys_mem_gb * 100) if phys_mem_gb > 0 else 100.0

    if pga_waits > 0 or mem_free_pct < 10:
        detail_parts = []
        if mem_free_pct < 10:
            detail_parts.append(
                f"free memory {free_mem_gb:.1f}GB of {phys_mem_gb:.1f}GB "
                f"({mem_free_pct:.1f}%)"
            )
        if pga_waits > 0:
            detail_parts.append(f"PGA-related waits at {pga_waits:.1f}% of DB time")
        recs.append(Recommendation(
            priority=2,
            category="Memory",
            finding=f"PGA memory pressure detected: {'; '.join(detail_parts)}.",
            action="Increase pga_aggregate_target",
            oracle_fix="ALTER SYSTEM SET pga_aggregate_target=XG SCOPE=BOTH;",
            impact="Reduces temp-space I/O and sort/hash-join spills",
            reference="PGA Memory Advisory, V$PGASTAT",
        ))

    # -----------------------------------------------------------------
    # 6. CPU OVERLOAD
    # -----------------------------------------------------------------
    aas_value = _aas(bad_data)
    cpu_count = _get_cpus(bad_data)
    cpu_busy = _get_os(bad_data, "cpu_busy_pct")

    if aas_value > cpu_count * 1.5 or cpu_busy > 90:
        details = []
        if aas_value > cpu_count * 1.5:
            details.append(f"AAS={aas_value:.1f} exceeds CPU count {cpu_count} x 1.5")
        if cpu_busy > 90:
            details.append(f"OS CPU busy {cpu_busy:.1f}%")
        recs.append(Recommendation(
            priority=1,
            category="Configuration",
            finding=f"CPU saturation detected: {'; '.join(details)}.",
            action="Identify top CPU SQL, reduce parallelism, or scale CPU",
            oracle_fix=(
                "-- Identify top CPU consumers:\n"
                "SELECT sql_id, cpu_time/1e6 cpu_s FROM v$sqlstats "
                "ORDER BY cpu_time DESC FETCH FIRST 10 ROWS ONLY;"
            ),
            impact="Reduces response time and prevents runaway queueing",
            reference="Host CPU, Time Model Statistics",
        ))

    # -----------------------------------------------------------------
    # 7. LATCH CONTENTION
    # -----------------------------------------------------------------
    latch_hit = _get_efficiency(bad_data, "latch_hit_pct")
    latch_sp_pct = _get_wait_pct(bad_data, "latch: shared pool")
    latch_other_pct = _get_wait_pct(bad_data, "latch")

    if (0 < latch_hit < 99) or latch_sp_pct > 0:
        detail_parts = []
        if 0 < latch_hit < 99:
            detail_parts.append(f"latch hit ratio {latch_hit:.2f}% (<99%)")
        if latch_sp_pct > 0:
            detail_parts.append(
                f"'latch: shared pool' at {latch_sp_pct:.1f}% DB time"
            )
        recs.append(Recommendation(
            priority=1,
            category="Concurrency",
            finding=f"Latch contention detected: {'; '.join(detail_parts)}.",
            action="Tune shared pool, reduce hard parsing",
            oracle_fix=(
                "-- Increase shared pool sub-pools:\n"
                "ALTER SYSTEM SET \"_kghdsidx_count\"=4 SCOPE=SPFILE;\n"
                "-- Or increase shared_pool_size"
            ),
            impact="Reduces mutex/latch waits and improves concurrency",
            reference="Instance Efficiency, Top Timed Events",
        ))

    # -----------------------------------------------------------------
    # 8. ROW LOCK WAITS
    # -----------------------------------------------------------------
    tx_lock_pct = _get_wait_pct(bad_data, "enq: TX - row lock contention")
    if tx_lock_pct == 0:
        tx_lock_pct = _get_wait_pct(bad_data, "TX - row lock")

    if tx_lock_pct > 3:
        recs.append(Recommendation(
            priority=1,
            category="Concurrency",
            finding=(
                f"Row lock contention at {tx_lock_pct:.1f}% of DB time, "
                f"exceeding the 3% threshold."
            ),
            action="Fix application-level locking, add missing FK indexes",
            oracle_fix=(
                "-- Find blocking sessions:\n"
                "SELECT * FROM v$lock WHERE block > 0;\n"
                "-- Add FK indexes to avoid share locks:\n"
                "-- CREATE INDEX idx_fk ON child_table(fk_column);"
            ),
            impact="Reduces session blocking and improves concurrency",
            reference="Top Timed Events, V$LOCK, V$SESSION",
        ))

    # -----------------------------------------------------------------
    # 9. HIGH REDO GENERATION
    # -----------------------------------------------------------------
    redo_per_sec = _get_load_metric(bad_data, "Redo size")
    if redo_per_sec == 0.0:
        redo_per_sec = _get_load_metric(bad_data, "Redo Size")
    redo_mb_per_sec = redo_per_sec / (1024 * 1024) if redo_per_sec > 0 else 0.0

    if redo_mb_per_sec > 10:
        recs.append(Recommendation(
            priority=3,
            category="I/O",
            finding=(
                f"High redo generation rate of {redo_mb_per_sec:.1f}MB/s "
                f"(threshold 10MB/s).  This can stress log writer and archiver."
            ),
            action="Check for unnecessary updates, use NOLOGGING for bulk ops",
            oracle_fix=(
                "-- For bulk loads:\n"
                "ALTER TABLE big_table NOLOGGING;\n"
                "INSERT /*+ APPEND */ INTO big_table SELECT ...;\n"
                "ALTER TABLE big_table LOGGING;"
            ),
            impact="Reduces log writer latency and archiver pressure",
            reference="Load Profile, V$SYSSTAT 'redo size'",
        ))

    # -----------------------------------------------------------------
    # 10. SQL REGRESSION (comparison-mode only)
    # -----------------------------------------------------------------
    if comparison is not None:
        sql_regressions = comparison.get("sql_regressions", [])
        for sql_reg in sql_regressions:
            if isinstance(sql_reg, dict):
                sql_id = sql_reg.get("sql_id", "?")
                delta = sql_reg.get("delta_pct", 0.0)
                tag = sql_reg.get("tag", "")
                severity = sql_reg.get("severity", "info")
            else:
                sql_id = getattr(sql_reg, "sql_id", "?")
                delta = getattr(sql_reg, "delta_pct", 0.0)
                tag = getattr(sql_reg, "tag", "")
                severity = getattr(sql_reg, "severity", "info")

            if delta > 100 or tag in ("regression", "new_offender"):
                recs.append(Recommendation(
                    priority=1,
                    category="SQL",
                    finding=(
                        f"SQL_ID {sql_id} regressed {delta:.0f}% in elapsed "
                        f"time between good and bad periods (tag: {tag})."
                    ),
                    action=(
                        "Analyze execution plan, check for plan flip.  "
                        "Compare plans with DBMS_XPLAN.DISPLAY_AWR."
                    ),
                    oracle_fix=(
                        f"-- Check plan history:\n"
                        f"SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR('{sql_id}'));\n"
                        f"-- Pin good plan with SQL Plan Baseline:\n"
                        f"EXEC DBMS_SPM.LOAD_PLANS_FROM_AWR(begin_snap=>X, "
                        f"end_snap=>Y, basic_filter=>'sql_id=''{sql_id}''');"
                    ),
                    impact="Directly reduces DB time contribution of regressed SQL",
                    reference="SQL Statistics, DBA_HIST_SQLSTAT",
                ))

    # Fallback: if no comparison provided, check bad_data SQL for outliers
    if comparison is None:
        sql_stats = bad_data.get("sql_stats", [])
        if good_data is not None:
            good_sql_map: dict[str, float] = {}
            for s in good_data.get("sql_stats", []):
                sid = s.get("sql_id", "") if isinstance(s, dict) else getattr(s, "sql_id", "")
                elapsed = (
                    s.get("elapsed_time_secs", 0.0) if isinstance(s, dict)
                    else getattr(s, "elapsed_time_secs", 0.0)
                )
                if sid:
                    good_sql_map[sid] = elapsed

            for s in sql_stats:
                sid = s.get("sql_id", "") if isinstance(s, dict) else getattr(s, "sql_id", "")
                bad_elapsed = (
                    s.get("elapsed_time_secs", 0.0) if isinstance(s, dict)
                    else getattr(s, "elapsed_time_secs", 0.0)
                )
                good_elapsed = good_sql_map.get(sid, 0.0)
                if good_elapsed > 0 and bad_elapsed > 0:
                    delta_pct = ((bad_elapsed - good_elapsed) / good_elapsed) * 100
                    if delta_pct > 100:
                        recs.append(Recommendation(
                            priority=1,
                            category="SQL",
                            finding=(
                                f"SQL_ID {sid} regressed {delta_pct:.0f}% in "
                                f"elapsed time ({good_elapsed:.1f}s -> "
                                f"{bad_elapsed:.1f}s)."
                            ),
                            action=(
                                "Analyze execution plan, check for plan flip.  "
                                "Compare plans with DBMS_XPLAN.DISPLAY_AWR."
                            ),
                            oracle_fix=(
                                f"SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR('{sid}'));"
                            ),
                            impact="Directly reduces DB time contribution of regressed SQL",
                            reference="SQL Statistics",
                        ))

    # -----------------------------------------------------------------
    # 11. LIBRARY CACHE MISS
    # -----------------------------------------------------------------
    lib_hit = _get_efficiency(bad_data, "library_cache_hit_pct")
    if 0 < lib_hit < 95:
        recs.append(Recommendation(
            priority=2,
            category="Memory",
            finding=(
                f"Library cache hit ratio is {lib_hit:.1f}%, below the 95% "
                f"threshold.  Frequent reloads waste CPU and increase latency."
            ),
            action="Increase shared_pool_size, pin frequently used objects",
            oracle_fix=(
                "ALTER SYSTEM SET shared_pool_size=XG SCOPE=BOTH;\n"
                "-- Pin critical packages:\n"
                "EXEC DBMS_SHARED_POOL.KEEP('SCHEMA.PACKAGE');"
            ),
            impact="Reduces library cache misses and parse-related CPU",
            reference="Instance Efficiency, V$LIBRARYCACHE",
        ))

    # -----------------------------------------------------------------
    # 12. EXECUTE TO PARSE LOW
    # -----------------------------------------------------------------
    exec_to_parse = _get_efficiency(bad_data, "execute_to_parse_pct")
    if 0 < exec_to_parse < 75:
        recs.append(Recommendation(
            priority=2,
            category="SQL",
            finding=(
                f"Execute-to-parse ratio is {exec_to_parse:.1f}% (threshold "
                f"75%).  Nearly every execution requires a parse call, wasting "
                f"CPU on repeated soft parses."
            ),
            action=(
                "Use session-cached cursors and hold cursors open in the "
                "application connection pool"
            ),
            oracle_fix=(
                "ALTER SYSTEM SET session_cached_cursors=100 SCOPE=BOTH;\n"
                "ALTER SYSTEM SET open_cursors=500 SCOPE=BOTH;"
            ),
            impact="Reduces parse overhead and CPU consumption",
            reference="Instance Efficiency, V$SYSSTAT",
        ))

    # -----------------------------------------------------------------
    # Comparison-based delta enrichment
    # -----------------------------------------------------------------
    if comparison is not None:
        # Check load profile deltas for large regressions
        for delta in comparison.get("load_profile_delta", []):
            metric = delta.get("metric", "") if isinstance(delta, dict) else getattr(delta, "metric", "")
            delta_pct = delta.get("delta_pct", 0.0) if isinstance(delta, dict) else getattr(delta, "delta_pct", 0.0)
            direction = delta.get("direction", "") if isinstance(delta, dict) else getattr(delta, "direction", "")
            severity = delta.get("severity", "") if isinstance(delta, dict) else getattr(delta, "severity", "")

            if direction == "regression" and severity == "critical" and abs(delta_pct) > 200:
                # Avoid duplicating already-covered metrics
                covered = {"hard parse", "redo size", "physical read"}
                if not any(kw in metric.lower() for kw in covered):
                    recs.append(Recommendation(
                        priority=2,
                        category="Configuration",
                        finding=(
                            f"Load profile metric '{metric}' regressed "
                            f"{delta_pct:.0f}% between good and bad periods."
                        ),
                        action="Investigate root cause of the workload spike",
                        oracle_fix="-- Review AWR Top SQL and Top Events for correlation",
                        impact="Addresses overall workload regression",
                        reference="Load Profile comparison",
                    ))

    # -----------------------------------------------------------------
    # Sort: priority ascending (1 first), then by severity heuristic
    # -----------------------------------------------------------------
    recs.sort(key=lambda r: _severity_score(r))

    return recs


# ---------------------------------------------------------------------------
# Single-report convenience wrapper
# ---------------------------------------------------------------------------

def generate_single_report_recommendations(data: dict) -> list[Recommendation]:
    """Generate recommendations from a single AWR report (no baseline).

    This is a convenience wrapper that calls :func:`generate_recommendations`
    with *good_data* set to ``None`` and no comparison data.
    """
    return generate_recommendations(good_data=None, bad_data=data, comparison=None)
