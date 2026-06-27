"""AWR Comparator Engine — compares a 'good period' vs 'bad period' of Oracle AWR data.

Produces a full ComparisonReport with metric deltas, wait event regressions,
SQL regressions, efficiency comparisons, incident indicators, and
prioritised recommendations.

Implements all 10 generic improvements:
  IMP1  — Observation window normalization (per-minute rates)
  IMP2  — Oracle maintenance job classifier
  IMP3  — Separate plan change detection from regression verdict
  IMP4  — Logon storm → E2P causal chain auto-explanation
  IMP5  — Correlated batch group detection
  IMP6  — I/O latency per-event delta
  IMP7  — Transaction throughput as primary KPI
  IMP8  — Single extreme wait event flag
  IMP9  — SQL module-based workload segmentation
  IMP10 — Net performance assessment column

Algorithm phases from reference specification:
  Phase 1  — Normalization to per-second rates; zero-elapsed abort
  Phase 2  — Direction-aware delta scoring (CPU drop = crisis, not improvement)
  Phase 3  — Wait event causal DAG via PATHOLOGY_MAP (causal_parents/children)
  Phase 4  — SQL regression_score = (bad/good elapsed) × log10(executions)
  Phase 6  — Z-score anomaly detection; ratio inversion detection
  Phase 7  — Confidence × severity priority heap
  Phase 8  — Condition-tree narrative from PATHOLOGY_MAP
"""
from __future__ import annotations

import math
import re
import statistics
from typing import Any

from models.comparison import (
    ComparisonReport,
    ComparisonSummary,
    PeriodSummary,
    MetricDelta,
    WaitEventComparison,
    EfficiencyComparison,
    SqlRegression,
    Recommendation,
    NormalizedMetric,
    NormalizedComparison,
)
from services.health_scorer import calculate_health_score
from services.rca_engine import PATHOLOGY_MAP, _get_pathology


# ---------------------------------------------------------------------------
# Root-cause hint lookup for common Oracle wait events
# ---------------------------------------------------------------------------

ROOT_CAUSE_HINTS: dict[str, str] = {
    "db file sequential read": "Single-block I/O. Check index selectivity, storage latency, missing indexes.",
    "db file scattered read": "Multi-block I/O. Full table scans likely. Check execution plans.",
    "log file sync": "Commit wait. Check commit frequency, redo log storage speed, async commit option.",
    "buffer busy waits": "Hot buffer contention. Check segment header blocks, freelist contention.",
    "latch: shared pool": "Shared pool saturation. Hard parse storm. Check literal SQL / bind variables.",
    "latch free": "Generic latch contention. Identify specific latch from v$latch.",
    "cursor: pin S wait on X": "Cursor invalidation under hard parse load. Check parse rate.",
    "enq: TX - row lock": "Row-level lock contention. Application-level serialisation issue.",
    "enq: HW - contention": "High-water mark contention. Segment extension under heavy insert load.",
    "library cache lock": "DDL contention or hard parse storm. Check for DDL during peak load.",
    "read by other session": "Physical I/O contention — sessions waiting for same block.",
    "gc buffer busy": "RAC — global cache busy. Check interconnect and hot objects.",
    "gc cr request": "RAC — cross-instance consistent read. Check workload distribution.",
    "direct path read": "PGA sort/hash spill or parallel query. Check sort_area_size, temp usage.",
    "direct path read temp": "Temp tablespace I/O. PGA pressure, large sorts. Check pga_aggregate_target.",
    "latch: cache buffers chains": "Hot block contention in buffer cache.",
    "db cpu": "CPU consumption. Check for inefficient SQL plans, excessive logical I/O.",
}

_HIGHER_IS_WORSE_KEYWORDS: set[str] = {
    "physical reads", "hard parses", "redo size", "parse count",
}

_HIGHER_IS_BETTER_KEYWORDS: set[str] = {
    "buffer cache hit", "soft parse ratio",
}

_EFFICIENCY_THRESHOLDS: dict[str, tuple[float, str]] = {
    "buffer_cache_hit_pct": (95.0, "Buffer Cache Hit Ratio should be >= 95%"),
    "library_cache_hit_pct": (95.0, "Library Cache Hit Ratio should be >= 95%"),
    "soft_parse_pct": (90.0, "Soft Parse % should be >= 90%"),
    "execute_to_parse_pct": (50.0, "Execute to Parse % should be >= 50%"),
    "latch_hit_pct": (99.0, "Latch Hit % should be >= 99%"),
}


# ---------------------------------------------------------------------------
# IMP2 — Oracle maintenance SQL classifier
# ---------------------------------------------------------------------------

_MAINTENANCE_MODULES = {
    "dbms_scheduler", "mmon_slave", "dbms_stats", "auto optimizer stats",
    "oem", "datapump", "logminer", "goldengate", "xstream",
}

_MAINTENANCE_MODULE_PREFIXES = ("rman",)

_MAINTENANCE_SQL_PATTERNS = [
    re.compile(r"gather_database_stats", re.IGNORECASE),
    re.compile(r"gather_schema_stats", re.IGNORECASE),
    re.compile(r"gather_table_stats", re.IGNORECASE),
    re.compile(r"gather_fixed_objects_stats", re.IGNORECASE),
    re.compile(r"select\s+not_stale\.obj#", re.IGNORECASE),
    re.compile(r"SQL\s*Analyze", re.IGNORECASE),
    re.compile(r"/\*\s*SQL\s*Analyze\s*\*/", re.IGNORECASE),
    re.compile(r"dbms_stats", re.IGNORECASE),
    re.compile(r"dbms_scheduler", re.IGNORECASE),
    re.compile(r"sys\.dbms_", re.IGNORECASE),
]

# Oracle Scheduler Resource Engine — platform-level infrastructure queries
# (RAC/Grid scheduler heartbeats, job dispatch, node coordination)
_PLATFORM_SQL_PATTERNS = [
    re.compile(r"\bSRE_(NODE|JOB|GLOBAL_PROPERTY|NODE_CONFIG|LOCK|QUEUE)\b", re.IGNORECASE),
    re.compile(r"\bSRE_NodeControl\b", re.IGNORECASE),
]
_PLATFORM_MODULE_PREFIXES = ("sre_",)

# IMP9 — Module-to-source mapping
_MODULE_SOURCE_MAP = {
    "jdbc thin client": "Application",
    "jdbc oci": "Application",
    "sqlplus": "Ad-hoc / DBA",
    "plsqldev": "Ad-hoc / DBA",
    "pl/sql developer": "Ad-hoc / DBA",
    "toad": "Ad-hoc / DBA",
    "sql developer": "Ad-hoc / DBA",
    "dbms_scheduler": "Oracle Maintenance",
    "mmon_slave": "Oracle Maintenance",
    "dbms_stats": "Oracle Maintenance",
    "auto optimizer stats": "Oracle Maintenance",
    "oem": "Monitoring (OEM)",
    "datapump": "DataPump",
    "rman": "RMAN Backup",
    "logminer": "Oracle Maintenance",
    "goldengate": "Oracle Maintenance",
    "xstream": "Oracle Maintenance",
    # BI / desktop workbench tools — full-table-scan risk category
    "diawp": "BI / Desktop Tool",
    "diawp.exe": "BI / Desktop Tool",
    "informatica": "ETL / Integration",
    "informaticapc": "ETL / Integration",
    "powerbi": "BI / Desktop Tool",
    "tableau": "BI / Desktop Tool",
    "businessobjects": "BI / Desktop Tool",
    "crystal": "BI / Desktop Tool",
    "cognos": "BI / Desktop Tool",
    "microstrategy": "BI / Desktop Tool",
    "spotfire": "BI / Desktop Tool",
    "qlikview": "BI / Desktop Tool",
    "qliksense": "BI / Desktop Tool",
    "excel": "BI / Desktop Tool",
    "sap": "ETL / Integration",
    "talend": "ETL / Integration",
    "pentaho": "ETL / Integration",
    "datastage": "ETL / Integration",
    "abinitio": "ETL / Integration",
}


def _is_platform_scheduler(module: str, sql_text: str) -> bool:
    """Detect Oracle Scheduler Resource Engine (SRE) platform infrastructure SQL."""
    mod = (module or "").strip().lower()
    for prefix in _PLATFORM_MODULE_PREFIXES:
        if mod.startswith(prefix):
            return True
    for regex in _PLATFORM_SQL_PATTERNS:
        if regex.search(sql_text or ""):
            return True
    return False


def _is_oracle_maintenance(module: str, sql_text: str) -> bool:
    """IMP2: Detect if a SQL is Oracle internal maintenance."""
    mod = (module or "").strip().lower()
    if mod in _MAINTENANCE_MODULES:
        return True
    for prefix in _MAINTENANCE_MODULE_PREFIXES:
        if mod.startswith(prefix):
            return True
    for regex in _MAINTENANCE_SQL_PATTERNS:
        if regex.search(sql_text or ""):
            return True
    return False


def _classify_source(module: str, sql_text: str) -> str:
    """IMP9: Classify SQL into a workload source category."""
    # Check platform scheduler BEFORE generic maintenance — more specific
    if _is_platform_scheduler(module, sql_text):
        return "Platform / Scheduler"
    if _is_oracle_maintenance(module, sql_text):
        return "Oracle Maintenance"
    mod = (module or "").strip().lower()
    for pattern, source in _MODULE_SOURCE_MAP.items():
        if pattern in mod:
            return source
    # PL/SQL blocks / CALL statements with no matching module are application code,
    # not ad-hoc DBA work — they're scheduled or called from application tier
    txt_upper = (sql_text or "").lstrip().upper()
    if txt_upper.startswith(("BEGIN ", "DECLARE", "CALL ")):
        return "Application"
    if not mod or mod in ("", "unknown"):
        return "Ad-hoc / DBA"
    return mod  # use module name as-is


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_higher_worse(stat_name: str) -> bool:
    name_lower = stat_name.lower()
    for kw in _HIGHER_IS_BETTER_KEYWORDS:
        if kw in name_lower:
            return False
    for kw in _HIGHER_IS_WORSE_KEYWORDS:
        if kw in name_lower:
            return True
    return True


def _float(val: Any, default: float = 0.0) -> float:
    try:
        # Strip comma thousands-separators so "87,699,626" → 87699626.0
        return float(str(val).replace(",", "")) if val is not None else default
    except (TypeError, ValueError):
        return default


def _lp_value(data: dict, *keywords: str) -> float:
    """Find a load-profile metric by keyword and return its per_sec value."""
    lp = data.get("load_profile", [])
    for m in lp:
        if not isinstance(m, dict):
            continue
        sn = (m.get("stat_name", "") or "").lower()
        for kw in keywords:
            if kw in sn:
                return _float(m.get("per_sec", 0))
    return 0.0


def _lp_metric_available(data: dict, keyword: str) -> bool:
    """Return whether a load-profile metric was actually present in the report."""
    for metric in data.get("load_profile", []) or []:
        if not isinstance(metric, dict):
            continue
        stat_name = (metric.get("stat_name", "") or "").lower()
        if keyword.lower() in stat_name:
            return True
    return False


def _lp_any_metric_available(data: dict, *keywords: str) -> bool:
    return any(_lp_metric_available(data, keyword) for keyword in keywords)


def _efficiency_metric_available(data: dict, metric_key: str) -> bool:
    """Keep an omitted ratio distinct from a measured zero."""
    declared = data.get("efficiency_available")
    if isinstance(declared, list):
        return metric_key in declared
    efficiency = data.get("efficiency", {})
    return isinstance(efficiency, dict) and metric_key in efficiency


def _cpu_count(data: dict) -> int:
    db_info = data.get("db_info", {}) or {}
    os_stats = data.get("os_stats", {}) or {}
    return int(_float(
        data.get("cpus", 0)
        or db_info.get("cpu_count", 0)
        or os_stats.get("num_cpus", 0)
        or 0
    ))


# ---------------------------------------------------------------------------
# Period summary builder (IMP1, IMP7)
# ---------------------------------------------------------------------------

def _compute_period_summary(data: dict, label: str) -> PeriodSummary:
    elapsed_min = _float(data.get("elapsed_min", 0.0))
    db_time_min = _float(data.get("db_time_min", 0.0))

    # Phase 1 — Zero-elapsed abort: a zero-elapsed snapshot produces divide-by-zero
    # poison values downstream. Flag it and return a zeroed summary rather than NaN.
    if elapsed_min <= 0:
        return PeriodSummary(
            label=f"{label} [INVALID_SNAPSHOT: elapsed_min=0]",
            snap_begin=int(data.get("begin_snap", 0)),
            snap_end=int(data.get("end_snap", 0)),
        )

    elapsed_secs = elapsed_min * 60.0
    db_time_secs = db_time_min * 60.0
    aas = db_time_secs / elapsed_secs if elapsed_secs > 0 else 0.0

    # IMP7 — Transaction throughput
    txn_per_sec_available = _lp_any_metric_available(
        data, "transaction", "user commit", "commit", "rollback",
    )
    txn_per_sec = _lp_value(data, "transaction", "user commit")
    if txn_per_sec == 0:
        txn_per_sec = _lp_value(data, "commit") + _lp_value(data, "rollback")

    # IMP1 — normalized rates
    db_time_per_min = db_time_secs / elapsed_min if elapsed_min > 0 else 0.0
    parses_per_min_available = _lp_any_metric_available(
        data, "parse count (total)", "parse count",
    )
    parse_per_sec = _lp_value(data, "parse count (total)", "parse count")
    parses_per_min = parse_per_sec * 60.0

    return PeriodSummary(
        label=label,
        snap_begin=int(data.get("begin_snap", 0)),
        snap_end=int(data.get("end_snap", 0)),
        db_time_secs=round(db_time_secs, 2),
        elapsed_secs=round(elapsed_secs, 2),
        elapsed_min=round(elapsed_min, 2),
        aas=round(aas, 2),
        txn_per_sec=round(txn_per_sec, 2),
        txn_per_sec_available=txn_per_sec_available,
        db_time_per_min=round(db_time_per_min, 2),
        parses_per_min=round(parses_per_min, 2),
        parses_per_min_available=parses_per_min_available,
    )


# ---------------------------------------------------------------------------
# A) Load-profile metric delta calculation
# ---------------------------------------------------------------------------

def _compare_load_profile(good_data: dict, bad_data: dict) -> list[MetricDelta]:
    good_lp = good_data.get("load_profile", [])
    bad_lp = bad_data.get("load_profile", [])

    good_map = {m.get("stat_name", "").lower(): m for m in good_lp if isinstance(m, dict)}
    bad_map = {m.get("stat_name", "").lower(): m for m in bad_lp if isinstance(m, dict)}

    all_keys = sorted(set(good_map) | set(bad_map))
    deltas: list[MetricDelta] = []

    for key in all_keys:
        if key not in good_map or key not in bad_map:
            continue
        good_m = good_map.get(key, {})
        bad_m = bad_map.get(key, {})

        good_val = _float(good_m.get("per_sec", 0.0))
        bad_val = _float(bad_m.get("per_sec", 0.0))
        good_per_txn = _float(good_m.get("per_txn", 0.0))
        bad_per_txn = _float(bad_m.get("per_txn", 0.0))

        stat_name = bad_m.get("stat_name") or good_m.get("stat_name", key)

        if good_val != 0.0:
            change_pct = ((bad_val - good_val) / abs(good_val)) * 100.0
        elif bad_val != 0.0:
            change_pct = 100.0
        else:
            change_pct = 0.0

        higher_worse = _is_higher_worse(stat_name)

        if abs(change_pct) < 1.0:
            direction = "stable"
        elif higher_worse:
            direction = "regression" if change_pct > 0 else "improvement"
        else:
            direction = "regression" if change_pct < 0 else "improvement"

        abs_delta = abs(change_pct)
        if abs_delta > 200.0:
            severity = "critical"
        elif abs_delta > 50.0:
            severity = "warning"
        else:
            severity = "info"

        if direction == "improvement":
            severity = "good"

        deltas.append(MetricDelta(
            metric=stat_name,
            good_value=round(good_val, 4),
            bad_value=round(bad_val, 4),
            good_per_txn=round(good_per_txn, 4),
            bad_per_txn=round(bad_per_txn, 4),
            change_pct=round(change_pct, 2),
            direction=direction,
            severity=severity if direction != "stable" else "info",
        ))

    deltas.sort(key=lambda d: (0 if d.direction == "regression" else 1, -abs(d.change_pct)))
    return deltas


# ---------------------------------------------------------------------------
# B) Wait-event regression detection (IMP6, IMP8, Phase 1/3/6/7)
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHT: dict[str, float] = {
    "critical": 100.0,
    "high": 70.0,
    "medium": 40.0,
    "low": 15.0,
}


def _compare_wait_events(
    good_data: dict,
    bad_data: dict,
    good_elapsed_secs: float = 0.0,
    bad_elapsed_secs: float = 0.0,
) -> list[WaitEventComparison]:
    good_events = good_data.get("wait_events", [])
    bad_events = bad_data.get("wait_events", [])

    good_map = {e.get("event_name", "").lower(): e for e in good_events if isinstance(e, dict)}
    bad_map = {e.get("event_name", "").lower(): e for e in bad_events if isinstance(e, dict)}

    # Phase 1 — Normalize wait times to per-second rates when elapsed differs.
    # pct_db_time is already window-normalized by Oracle, so it is the primary
    # comparison signal. Raw time_waited_secs is only used for avg-wait computation.
    g_elapsed = max(good_elapsed_secs, 1.0)
    b_elapsed = max(bad_elapsed_secs, 1.0)

    all_events = sorted(set(good_map) | set(bad_map))
    comparisons: list[WaitEventComparison] = []

    for key in all_events:
        good_e = good_map.get(key, {})
        bad_e = bad_map.get(key, {})

        event_name = bad_e.get("event_name") or good_e.get("event_name", key)
        good_time = _float(good_e.get("time_waited_secs", 0.0))
        bad_time = _float(bad_e.get("time_waited_secs", 0.0))
        good_pct = _float(good_e.get("pct_db_time", 0.0))
        bad_pct = _float(bad_e.get("pct_db_time", 0.0))
        wait_class = bad_e.get("wait_class") or good_e.get("wait_class", "Other")

        # Phase 1 — per-second rates (for cross-window delta)
        good_per_sec = good_time / g_elapsed if good_time > 0 else 0.0
        bad_per_sec = bad_time / b_elapsed if bad_time > 0 else 0.0

        # IMP6 — Latency columns
        good_total_waits = int(_float(good_e.get("total_waits", 0)))
        bad_total_waits = int(_float(bad_e.get("total_waits", 0)))
        good_avg_ms = _float(good_e.get("avg_wait_ms", 0.0))
        bad_avg_ms = _float(bad_e.get("avg_wait_ms", 0.0))

        # Compute avg if not present
        if good_avg_ms == 0 and good_time > 0 and good_total_waits > 0:
            good_avg_ms = good_time * 1000.0 / good_total_waits
        if bad_avg_ms == 0 and bad_time > 0 and bad_total_waits > 0:
            bad_avg_ms = bad_time * 1000.0 / bad_total_waits

        latency_delta_pct = 0.0
        if good_avg_ms > 0:
            latency_delta_pct = ((bad_avg_ms - good_avg_ms) / good_avg_ms) * 100.0

        # IMP6 — volume vs latency flag
        pct_increase = bad_pct > good_pct * 1.2 and bad_pct > 2.0
        latency_increased = latency_delta_pct > 50.0
        if pct_increase and latency_increased:
            latency_flag = "both"
        elif pct_increase and not latency_increased:
            latency_flag = "volume_increase"
        elif latency_increased:
            latency_flag = "latency_increase"
        else:
            latency_flag = ""

        # IMP8 — Extreme wait (avg wait > 60s)
        extreme_wait_flag = bad_avg_ms > 60000.0

        # Phase 1 — primary delta uses per-second normalized rates
        if good_per_sec > 0:
            delta_pct = ((bad_per_sec - good_per_sec) / good_per_sec) * 100.0
        elif bad_per_sec > 0:
            delta_pct = 100.0
        elif good_pct > 0:
            delta_pct = ((bad_pct - good_pct) / good_pct) * 100.0
        elif bad_pct > 0:
            delta_pct = 100.0
        else:
            delta_pct = 0.0

        # Absolute pct_db_time delta (simpler signal for threshold checks)
        delta_pct_db_time = bad_pct - good_pct

        # Phase 6 — new dominant wait detection
        # Event not in good top-10 AND pct_db_time > 2.0 in bad = NEW_DOMINANT_WAIT
        is_new_dominant = (key not in good_map) and (bad_pct > 2.0)

        # -- Commit wait proportionality guard --------------------------------
        # log file sync / "Commit" class waits scale directly with transaction rate.
        # If the commit rate fell proportionally to the transaction throughput change,
        # classifying the wait as "worsening" is a false positive.
        # Check: if bad_pct is higher but txn/s in bad is proportionally lower,
        # the same amount of commit work appears as a higher pct of a smaller DB Time.
        _commit_proportional = False
        _commit_note = ""
        _wc_is_commit = (
            (wait_class or "").lower() == "commit"
            or "log file sync" in event_name.lower()
        )
        if _wc_is_commit and bad_pct > good_pct:
            # Pull per-second commit rate from load profile if available
            good_commits_s = _lp_value(good_data, "user commit") or _lp_value(good_data, "commit")
            bad_commits_s  = _lp_value(bad_data,  "user commit") or _lp_value(bad_data,  "commit")
            if good_commits_s > 0 and bad_commits_s > 0:
                commit_delta_pct = ((bad_commits_s - good_commits_s) / good_commits_s) * 100.0
                pct_wait_delta   = bad_pct - good_pct
                # If commit rate fell or stayed similar, the wait % increase is an
                # artefact of the smaller DB Time denominator, not a real regression.
                if commit_delta_pct < 10.0:
                    _commit_proportional = True
                    _commit_note = (
                        f"Commit rate changed {commit_delta_pct:+.0f}% while log file sync %DB Time "
                        f"rose {pct_wait_delta:+.1f}pp — proportional to throughput change; "
                        f"not an independent regression. Latency avg: {bad_avg_ms:.1f}ms."
                    )
            elif bad_per_sec > 0 and good_per_sec > 0:
                # Fall back to raw per-second rate comparison
                rate_delta_pct = ((bad_per_sec - good_per_sec) / good_per_sec) * 100.0
                if rate_delta_pct < 20.0:
                    _commit_proportional = True
                    _commit_note = (
                        f"Log file sync rate/sec changed {rate_delta_pct:+.0f}% — "
                        f"proportional to workload change, not an independent bottleneck."
                    )

        # Classification
        if is_new_dominant:
            classification = "new_bottleneck"
        elif key in bad_map and key not in good_map:
            classification = "new_bottleneck"
        elif _commit_proportional and not latency_increased:
            # Commit waits look higher in % only because DB Time denominator shrank;
            # actual commit work didn't worsen — downgrade to stable
            classification = "stable"
        elif delta_pct > 100.0 or (bad_pct > good_pct * 2 and bad_pct > 5.0):
            classification = "worsening"
        elif delta_pct_db_time > 5.0:
            # Absolute pct_db_time spike > 5pp even if relative delta < 100%
            classification = "worsening"
        elif delta_pct < -50.0:
            classification = "improving"
        else:
            classification = "stable"

        # Phase 7 — confidence score per finding
        # Based on number of supporting signals (pct spike + latency spike + new event)
        confidence_signals = 0
        if is_new_dominant:
            confidence_signals += 2  # strongest signal
        if delta_pct_db_time > 5.0:
            confidence_signals += 1
        if delta_pct > 100.0:
            confidence_signals += 1
        if latency_increased:
            confidence_signals += 1
        if extreme_wait_flag:
            confidence_signals += 1
        if bad_pct > 20.0:
            confidence_signals += 1
        confidence = min(confidence_signals / 4.0, 1.0)  # clamp to [0,1]

        # Phase 8 — PATHOLOGY_MAP enrichment
        pathology = _get_pathology(event_name)
        hint = pathology.get("meaning", "")
        if not hint:
            # Fallback to old ROOT_CAUSE_HINTS
            hint = ROOT_CAUSE_HINTS.get(event_name.lower(), "")
            if not hint:
                for pattern, h in ROOT_CAUSE_HINTS.items():
                    if pattern in event_name.lower():
                        hint = h
                        break

        comparisons.append(WaitEventComparison(
            event_name=event_name,
            good_time_secs=round(good_time, 4),
            bad_time_secs=round(bad_time, 4),
            good_pct_db_time=round(good_pct, 2),
            bad_pct_db_time=round(bad_pct, 2),
            delta_pct=round(delta_pct, 2),
            delta_pct_db_time=round(delta_pct_db_time, 2),
            wait_class=wait_class,
            classification=classification,
            root_cause_hint=hint,
            pathology_meaning=pathology.get("meaning", ""),
            pathology_investigate=pathology.get("investigate", []),
            causal_parents=pathology.get("causal_parents", []),
            causal_children=pathology.get("causal_children", []),
            good_total_waits=good_total_waits,
            bad_total_waits=bad_total_waits,
            good_avg_wait_ms=round(good_avg_ms, 3),
            bad_avg_wait_ms=round(bad_avg_ms, 3),
            latency_delta_pct=round(latency_delta_pct, 2),
            latency_flag=latency_flag,
            good_implied_max_ms=round(good_avg_ms, 3),
            bad_implied_max_ms=round(bad_avg_ms, 3),
            extreme_wait_flag=extreme_wait_flag,
            confidence=round(confidence, 3),
            is_new_dominant=is_new_dominant,
            proportionality_note=_commit_note,
        ))

    # Phase 7 — sort by confidence × severity weight for priority heap behavior
    def _sort_key(c: WaitEventComparison) -> float:
        if c.classification == "new_bottleneck":
            sev_w = 100.0
        elif c.classification == "worsening":
            sev_w = 70.0
        elif c.classification == "stable":
            sev_w = 15.0
        else:
            sev_w = 5.0
        return -(c.confidence * sev_w + c.bad_pct_db_time)

    comparisons.sort(key=_sort_key)
    return comparisons


# ---------------------------------------------------------------------------
# C) SQL regression detection (IMP1, IMP2, IMP3, IMP9, IMP10)
# ---------------------------------------------------------------------------

def _compute_net_assessment(
    good_avg: float, bad_avg: float,
    good_execs: int, bad_execs: int,
    good_elapsed: float, bad_elapsed: float,
    threshold_pct: float = 10.0,
) -> tuple[str, str]:
    """IMP10: Compute net performance assessment."""
    if good_elapsed > 0 and bad_elapsed == 0 and bad_execs == 0:
        return "Disappeared", "SQL not present in bad period"
    if good_elapsed == 0 and good_execs == 0 and bad_elapsed > 0:
        return "New SQL", "Not in baseline — cannot compare per-exec"
    if good_execs < 3 or bad_execs < 3:
        return "Cannot Determine", f"Insufficient executions (good={good_execs}, bad={bad_execs})"
    if good_avg == 0 and bad_avg == 0:
        return "Cannot Determine", "No elapsed data available"
    if good_avg == 0:
        return "Cannot Determine", "Zero baseline avg elapsed"

    pct_change = ((bad_avg - good_avg) / good_avg) * 100.0
    if pct_change > threshold_pct:
        return "Regressed", f"Per-exec elapsed +{pct_change:.1f}% (>{threshold_pct}% threshold)"
    elif pct_change < -threshold_pct:
        return "Improved", f"Per-exec elapsed {pct_change:.1f}% (>{threshold_pct}% improvement)"
    else:
        return "Stable", f"Per-exec elapsed {pct_change:+.1f}% (within ±{threshold_pct}% tolerance)"


def _compute_plan_verdict(plan_changed: bool, good_avg: float, bad_avg: float) -> str:
    """IMP3: Separate plan change detection from regression verdict."""
    if not plan_changed:
        return ""
    if good_avg == 0:
        return "PLAN CHANGED"
    pct_change = ((bad_avg - good_avg) / good_avg) * 100.0
    if pct_change > 10.0:
        return "PLAN CHANGED \u2014 REGRESSED"
    elif pct_change < -10.0:
        return "PLAN CHANGED \u2014 IMPROVED"
    else:
        return "PLAN CHANGED \u2014 STABLE"


def _compare_sql_stats(
    good_data: dict,
    bad_data: dict,
    good_elapsed_min: float,
    bad_elapsed_min: float,
) -> list[SqlRegression]:
    good_sql = good_data.get("sql_stats", [])
    bad_sql = bad_data.get("sql_stats", [])

    good_map = {s.get("sql_id", ""): s for s in good_sql if isinstance(s, dict) and s.get("sql_id")}
    bad_map = {s.get("sql_id", ""): s for s in bad_sql if isinstance(s, dict) and s.get("sql_id")}

    # Build ADDM-referenced SQL set
    addm_sql_ids: set[str] = set()
    for finding in bad_data.get("addm_findings", []):
        if isinstance(finding, dict):
            for sid in finding.get("referenced_sql_ids", []):
                addm_sql_ids.add(sid)
    for finding in good_data.get("addm_findings", []):
        if isinstance(finding, dict):
            for sid in finding.get("referenced_sql_ids", []):
                addm_sql_ids.add(sid)

    all_ids = sorted(set(good_map) | set(bad_map))
    regressions: list[SqlRegression] = []

    g_emin = max(good_elapsed_min, 1.0)
    b_emin = max(bad_elapsed_min, 1.0)

    for sql_id in all_ids:
        good_s = good_map.get(sql_id, {})
        bad_s = bad_map.get(sql_id, {})

        good_elapsed = _float(good_s.get("elapsed_time_secs", 0.0))
        bad_elapsed = _float(bad_s.get("elapsed_time_secs", 0.0))
        good_execs = int(_float(good_s.get("executions", 0)))
        bad_execs = int(_float(bad_s.get("executions", 0)))
        good_avg = _float(good_s.get("avg_elapsed_secs", 0.0))
        bad_avg = _float(bad_s.get("avg_elapsed_secs", 0.0))
        good_cpu = _float(good_s.get("cpu_time_secs", 0.0))
        bad_cpu = _float(bad_s.get("cpu_time_secs", 0.0))
        good_gets = _float(good_s.get("buffer_gets", 0.0))
        bad_gets = _float(bad_s.get("buffer_gets", 0.0))
        good_reads = _float(good_s.get("disk_reads", 0.0))
        bad_reads = _float(bad_s.get("disk_reads", 0.0))
        good_rows_per_exec = _float(good_s.get("rows_per_exec", 0.0))
        bad_rows_per_exec = _float(bad_s.get("rows_per_exec", 0.0))
        good_rows_processed = int(_float(good_s.get("rows_processed", 0.0)))
        bad_rows_processed = int(_float(bad_s.get("rows_processed", 0.0)))
        good_plan_hash = str(good_s.get("plan_hash_value", ""))
        bad_plan_hash = str(bad_s.get("plan_hash_value", ""))

        if good_rows_processed == 0 and good_rows_per_exec > 0 and good_execs > 0:
            good_rows_processed = int(round(good_rows_per_exec * good_execs))
        if bad_rows_processed == 0 and bad_rows_per_exec > 0 and bad_execs > 0:
            bad_rows_processed = int(round(bad_rows_per_exec * bad_execs))

        plan_changed = (
            good_plan_hash != bad_plan_hash
            and bool(good_plan_hash)
            and bool(bad_plan_hash)
        )

        sql_text = (bad_s.get("sql_text") or good_s.get("sql_text", ""))[:2000]
        sql_text_full = bad_s.get("sql_text_full") or good_s.get("sql_text_full", "")
        sql_text_truncated_str = bad_s.get("sql_text_truncated") or good_s.get("sql_text_truncated", "")
        text_verified = bool(bad_s.get("text_verified") or good_s.get("text_verified", False))
        tables_referenced = bad_s.get("tables_referenced") or good_s.get("tables_referenced", [])
        sql_module = (bad_s.get("module") or good_s.get("module", ""))
        sql_action = (bad_s.get("action") or good_s.get("action", ""))
        addm_ref = sql_id in addm_sql_ids or bool(bad_s.get("addm_referenced")) or bool(good_s.get("addm_referenced"))

        # IMP2, IMP9
        is_maint = _is_oracle_maintenance(sql_module, sql_text)
        source_cat = _classify_source(sql_module, sql_text)

        # IMP3
        plan_verdict = _compute_plan_verdict(plan_changed, good_avg, bad_avg)

        # IMP10
        net_assessment, net_detail = _compute_net_assessment(
            good_avg, bad_avg, good_execs, bad_execs, good_elapsed, bad_elapsed,
        )

        # IMP1 — per-minute rates
        good_elapsed_per_min = good_elapsed / g_emin
        bad_elapsed_per_min = bad_elapsed / b_emin
        good_execs_per_min = good_execs / g_emin
        bad_execs_per_min = bad_execs / b_emin

        # Elapsed delta using normalized per-min rates
        if good_elapsed_per_min > 0:
            delta_pct = ((bad_elapsed_per_min - good_elapsed_per_min) / good_elapsed_per_min) * 100.0
        elif bad_elapsed_per_min > 0:
            delta_pct = 100.0
        else:
            delta_pct = 0.0

        if good_execs_per_min > 0:
            exec_delta_pct = ((bad_execs_per_min - good_execs_per_min) / good_execs_per_min) * 100.0
        elif bad_execs_per_min > 0:
            exec_delta_pct = 100.0
        else:
            exec_delta_pct = 0.0

        if good_avg > 0:
            avg_elapsed_delta_pct = ((bad_avg - good_avg) / good_avg) * 100.0
        elif bad_avg > 0:
            avg_elapsed_delta_pct = 100.0
        else:
            avg_elapsed_delta_pct = 0.0

        # Existing SQL: prioritize slowdown ratio with a modest volume weight.
        # New SQL: prioritize normalized total elapsed contribution so high-volume
        # statements are not hidden merely because each execution is fast.
        # log10(executions) is the volume weight: a SQL running 144k times × 40x slower
        # scores dramatically higher than one running 10 times × 40x slower.
        regression_score = 0.0
        if good_avg > 0 and bad_avg > 0 and bad_execs > 0:
            regression_score = (bad_avg / good_avg) * math.log10(bad_execs + 1)
        elif bad_avg > 0 and bad_execs > 0:
            regression_score = bad_elapsed_per_min * math.log10(bad_execs + 1)

        new_sql_impactful = sql_id not in good_map and (
            bad_elapsed >= 10.0
            or bad_elapsed_per_min >= 1.0
            or bad_execs_per_min >= 100.0
        )

        # Tag classification
        if is_maint:
            if sql_id in bad_map and sql_id not in good_map:
                tag = "stable"
            elif avg_elapsed_delta_pct > 100.0:
                tag = "regression"
            else:
                tag = "stable"
        elif new_sql_impactful:
            # Strictly new and materially visible in elapsed time or execution volume.
            tag = "new_offender"
        elif sql_id in good_map and good_avg > 0.001 and bad_avg > good_avg * 2:
            # Per-exec cost at least doubled — regression regardless of frequency change
            tag = "regression"
        elif sql_id in good_map and good_avg > 0.001 and exec_delta_pct > 300.0 and avg_elapsed_delta_pct <= 50.0:
            # Frequency exploded but per-exec cost stable — load increase, not plan problem
            tag = "load_increase"
        elif sql_id in good_map and good_avg > 0.001 and bad_avg < good_avg * 0.8:
            tag = "improved"
        else:
            tag = "stable"

        # Severity
        if tag == "new_offender":
            severity = "critical" if bad_elapsed > 10.0 else "warning"
        elif tag == "regression":
            severity = "critical" if delta_pct > 500.0 else "warning"
            if plan_changed and "REGRESSED" in plan_verdict and severity != "critical":
                severity = "critical"
        elif tag == "load_increase":
            severity = "warning"
        elif tag == "improved":
            severity = "info"
        else:
            severity = "info"

        # CPU/IO breakdown for bad period
        cpu_pct = 0.0
        io_pct = 0.0
        if bad_elapsed > 0:
            cpu_pct = (bad_cpu / bad_elapsed * 100.0) if bad_cpu > 0 else 0.0
            # Approximate I/O time = elapsed - cpu (rough but useful)
            io_time = bad_elapsed - bad_cpu
            io_pct = (io_time / bad_elapsed * 100.0) if io_time > 0 else 0.0

        # Phase 4 — wait absorption detection
        # If a SQL's CPU% dropped while elapsed rose, the additional time is spent
        # waiting, not computing. The SQL is being serialized on a wait event.
        wait_absorption = False
        wait_absorption_note = ""
        if (
            sql_id in good_map and sql_id in bad_map
            and good_avg > 0 and bad_avg > good_avg * 1.2  # elapsed rose
            and good_elapsed > 0 and bad_elapsed > 0
        ):
            good_cpu_pct = (good_cpu / good_elapsed * 100.0) if good_cpu > 0 else 0.0
            bad_cpu_pct = cpu_pct
            cpu_pct_drop = good_cpu_pct - bad_cpu_pct
            if cpu_pct_drop > 15.0 and bad_cpu_pct < 20.0:
                wait_absorption = True
                missing_time = bad_avg - (good_avg * (bad_cpu_pct / max(good_cpu_pct, 1.0)))
                wait_absorption_note = (
                    f"CPU% dropped {good_cpu_pct:.1f}%→{bad_cpu_pct:.1f}% while elapsed rose "
                    f"{good_avg:.2f}s→{bad_avg:.2f}s. The extra ~{bad_avg - good_avg:.2f}s/exec "
                    f"is wait time (sessions blocked on a wait event, not doing CPU work)."
                )

        regressions.append(SqlRegression(
            sql_id=sql_id,
            sql_text_truncated=sql_text[:200] if sql_text else "",
            sql_text_full=sql_text_full,
            text_verified=text_verified,
            tables_referenced=tables_referenced if isinstance(tables_referenced, list) else [],
            sql_module=sql_module,
            source_category=source_cat,
            is_oracle_maintenance=is_maint,
            addm_referenced=addm_ref,
            tag=tag,
            good_elapsed_secs=round(good_elapsed, 4),
            bad_elapsed_secs=round(bad_elapsed, 4),
            good_avg_elapsed=round(good_avg, 4),
            bad_avg_elapsed=round(bad_avg, 4),
            good_executions=good_execs,
            bad_executions=bad_execs,
            good_cpu_secs=round(good_cpu, 4),
            bad_cpu_secs=round(bad_cpu, 4),
            good_buffer_gets=round(good_gets, 4),
            bad_buffer_gets=round(bad_gets, 4),
            good_disk_reads=round(good_reads, 4),
            bad_disk_reads=round(bad_reads, 4),
            good_rows_processed=good_rows_processed,
            bad_rows_processed=bad_rows_processed,
            good_rows_per_exec=round(good_rows_per_exec, 4),
            bad_rows_per_exec=round(bad_rows_per_exec, 4),
            good_plan_hash=good_plan_hash,
            bad_plan_hash=bad_plan_hash,
            plan_changed=plan_changed,
            plan_verdict=plan_verdict,
            net_assessment=net_assessment,
            net_assessment_detail=net_detail,
            delta_pct=round(delta_pct, 2),
            exec_delta_pct=round(exec_delta_pct, 2),
            avg_elapsed_delta_pct=round(avg_elapsed_delta_pct, 2),
            severity=severity,
            good_elapsed_per_min=round(good_elapsed_per_min, 4),
            bad_elapsed_per_min=round(bad_elapsed_per_min, 4),
            good_execs_per_min=round(good_execs_per_min, 4),
            bad_execs_per_min=round(bad_execs_per_min, 4),
            cpu_pct=round(cpu_pct, 1),
            io_pct=round(io_pct, 1),
            regression_score=round(regression_score, 4),
            wait_absorption=wait_absorption,
            wait_absorption_note=wait_absorption_note,
            sql_action=sql_action,
        ))

    # Phase 4 — Sort regressions by regression_score (log10-weighted priority heap)
    # This ensures a SQL running 144k times × 40x slower ranks above one running
    # 10 times × 40x slower, which is the correct triage priority.
    _tag_order = {"new_offender": 0, "regression": 1, "load_increase": 2, "improved": 3, "stable": 4}
    regressions.sort(key=lambda r: (
        _tag_order.get(r.tag, 9),
        -r.regression_score if r.regression_score > 0 else -r.bad_elapsed_secs,
    ))
    return regressions


# ---------------------------------------------------------------------------
# D) Instance Efficiency comparison
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# D0) DBWR Instance Activity Stats comparison  (Trigger 3)
# ---------------------------------------------------------------------------

_DBWR_STAT_KEYS = [
    ("dbwr checkpoint buffers written", "dbwr_checkpoint_written"),
    ("dirty buffers inspected",          "dirty_buffers_inspected"),
    ("free buffer inspected",            "free_buffer_inspected"),
    ("redo log space requests",          "redo_log_space_requests"),
    ("write complete waits",             "write_complete_waits"),
]


def _lookup_instance_stat(activity: list[dict], keyword: str) -> float:
    """Return the 'total' or 'value' column from Instance Activity Stats by keyword match.
    Keys are normalised to lowercase in _parse_instance_activity, so lookups are
    case-insensitive.  Also handles both the capitalised form ('Statistic') that
    older parser versions emitted and the normalised lowercase form."""
    kw = keyword.lower()
    for row in activity:
        # _parse_instance_activity now lowercases all keys; handle legacy uppercase too
        name = (
            row.get("statistic") or row.get("Statistic")
            or row.get("stat_name") or row.get("name") or ""
        ).lower()
        if kw in name:
            # Try 'total' first (AWR snap-delta column), fall back to 'value'
            for col in ("total", "Total", "value", "Value", "per second", "per Second", "per_second"):
                v = row.get(col)
                if v is not None:
                    return _float(v)
    return 0.0


def _compare_dbwr_activity_stats(
    good_data: dict,
    bad_data: dict,
    good_elapsed_sec: float,
    bad_elapsed_sec: float,
) -> dict:
    """
    Trigger 3 — Compare the five DBWR-related Instance Activity Stats between periods.
    Returns a dict with per-second rates and spike detection for use in JS verdict logic.
    """
    good_act = good_data.get("_instance_activity", [])
    bad_act  = bad_data.get("_instance_activity", [])

    g_secs = max(good_elapsed_sec, 1.0)
    b_secs = max(bad_elapsed_sec,  1.0)

    stats = {}
    spike_detected = False
    spike_stat = ""
    spike_pct = 0.0

    for keyword, field in _DBWR_STAT_KEYS:
        g_val = _lookup_instance_stat(good_act, keyword)
        b_val = _lookup_instance_stat(bad_act,  keyword)
        g_rate = g_val / g_secs
        b_rate = b_val / b_secs
        pct = ((b_rate - g_rate) / g_rate * 100.0) if g_rate > 0 else (100.0 if b_rate > 0 else 0.0)
        stats[field] = {
            "good_total": round(g_val, 2),
            "bad_total":  round(b_val, 2),
            "good_per_sec": round(g_rate, 4),
            "bad_per_sec":  round(b_rate, 4),
            "delta_pct":    round(pct, 1),
        }
        # Primary spike threshold: DBWR checkpoint buffers written/s > 50% increase
        if field == "dbwr_checkpoint_written" and pct > 50.0 and b_rate > 0:
            spike_detected = True
            spike_stat = keyword
            spike_pct = pct

    return {
        "stats": stats,
        "spike_detected": spike_detected,
        "spike_stat":     spike_stat,
        "spike_pct":      round(spike_pct, 1),
        "note": (
            f"DBWR write volume spike: '{spike_stat}' rate increased {spike_pct:.0f}% "
            f"({stats.get('dbwr_checkpoint_written',{}).get('good_per_sec',0):.2f}/s → "
            f"{stats.get('dbwr_checkpoint_written',{}).get('bad_per_sec',0):.2f}/s). "
            "More dirty buffers → DBWR cannot flush fast enough → free buffer waits → sessions stall."
        ) if spike_detected else "",
        "data_available": len(good_act) > 0 or len(bad_act) > 0,
    }


def _compare_efficiency(good_data: dict, bad_data: dict) -> list[EfficiencyComparison]:
    good_eff = good_data.get("efficiency", {})
    bad_eff = bad_data.get("efficiency", {})
    if not isinstance(good_eff, dict):
        good_eff = {}
    if not isinstance(bad_eff, dict):
        bad_eff = {}

    comparisons: list[EfficiencyComparison] = []

    for metric_key, (threshold, description) in _EFFICIENCY_THRESHOLDS.items():
        if not (
            _efficiency_metric_available(good_data, metric_key)
            and _efficiency_metric_available(bad_data, metric_key)
        ):
            continue
        good_val = _float(good_eff.get(metric_key, 0.0))
        bad_val = _float(bad_eff.get(metric_key, 0.0))
        delta = bad_val - good_val

        if bad_val < threshold - 10.0:
            severity = "critical"
            message = f"{metric_key} dropped to {bad_val:.2f}% (critical threshold: {threshold}%)"
        elif bad_val < threshold:
            severity = "warning"
            message = f"{metric_key} is {bad_val:.2f}% (below threshold: {threshold}%)"
        elif delta < -5.0:
            severity = "warning"
            message = f"{metric_key} degraded by {abs(delta):.2f}pp (still above threshold)"
        else:
            severity = "good"
            message = f"{metric_key} is {bad_val:.2f}% (healthy)"

        comparisons.append(EfficiencyComparison(
            metric=metric_key,
            good_val=round(good_val, 2),
            bad_val=round(bad_val, 2),
            delta=round(delta, 2),
            threshold=f">= {threshold}%",
            message=message,
            severity=severity,
        ))

    _sev_order = {"critical": 0, "warning": 1, "info": 2, "good": 3}
    comparisons.sort(key=lambda c: _sev_order.get(c.severity, 9))
    return comparisons


# ---------------------------------------------------------------------------
# IMP4 — Logon storm -> E2P causal chain
# ---------------------------------------------------------------------------

_LOGON_STORM_EXPLANATION = (
    "Connection pool logon storm detected. New sessions start with empty cursor "
    "caches, forcing re-parse of all SQL. This is the primary driver of E2P "
    "degradation. Remediate the connection pool before addressing SQL-level "
    "symptoms. Check: pool max-size vs peak concurrency, pool timeout configuration "
    "causing drain/refill cycles, whether Oracle DRCP is appropriate."
)


def _detect_logon_storm(good_data: dict, bad_data: dict) -> str:
    good_logons = _lp_value(good_data, "logon")
    bad_logons = _lp_value(bad_data, "logon")

    if not (
        _lp_metric_available(good_data, "logon")
        and _lp_metric_available(bad_data, "logon")
        and _efficiency_metric_available(good_data, "execute_to_parse_pct")
        and _efficiency_metric_available(bad_data, "execute_to_parse_pct")
    ):
        return ""

    good_eff = good_data.get("efficiency", {})
    bad_eff = bad_data.get("efficiency", {})
    if not isinstance(good_eff, dict):
        good_eff = {}
    if not isinstance(bad_eff, dict):
        bad_eff = {}

    good_e2p = _float(good_eff.get("execute_to_parse_pct", 0))
    bad_e2p = _float(bad_eff.get("execute_to_parse_pct", 0))

    logon_ratio = bad_logons / max(good_logons, 0.01)
    e2p_drop = good_e2p - bad_e2p

    if logon_ratio >= 2.0 and e2p_drop >= 20.0:
        return _LOGON_STORM_EXPLANATION
    return ""


# ---------------------------------------------------------------------------
# IMP5 — Correlated batch group detection
# ---------------------------------------------------------------------------

def _detect_batch_groups(
    sql_regressions: list[SqlRegression],
    tolerance_pct: float = 5.0,
) -> list[dict]:
    candidates = [
        s for s in sql_regressions
        if s.tag in ("new_offender", "regression", "load_increase")
        and s.bad_executions > 0
        and not s.is_oracle_maintenance
    ]
    if len(candidates) < 2:
        return []

    candidates.sort(key=lambda s: s.bad_executions)

    groups: list[list[SqlRegression]] = []
    used: set[str] = set()

    for i, sql_a in enumerate(candidates):
        if sql_a.sql_id in used:
            continue
        execs_a = sql_a.bad_executions
        group = [sql_a]
        used.add(sql_a.sql_id)

        for j, sql_b in enumerate(candidates):
            if i == j or sql_b.sql_id in used:
                continue
            execs_b = sql_b.bad_executions
            pct_diff = abs(execs_a - execs_b) / max(execs_a, 1) * 100.0
            if pct_diff <= tolerance_pct:
                group.append(sql_b)
                used.add(sql_b.sql_id)

        if len(group) >= 2:
            groups.append(group)

    result = []
    for idx, group in enumerate(groups):
        combined_elapsed = sum(s.bad_elapsed_secs for s in group)
        combined_io = sum(s.bad_disk_reads for s in group)
        avg_execs = sum(s.bad_executions for s in group) / len(group)
        result.append({
            "group_id": idx + 1,
            "label": f"Batch Group {chr(65 + idx)}",
            "sql_ids": [s.sql_id for s in group],
            "exec_count": int(avg_execs),
            "combined_elapsed_secs": round(combined_elapsed, 2),
            "combined_disk_reads": int(combined_io),
            "sql_count": len(group),
        })

    result.sort(key=lambda g: -g["combined_elapsed_secs"])
    return result


# ---------------------------------------------------------------------------
# IMP9 — Workload composition summary
# ---------------------------------------------------------------------------

def _workload_composition(sql_regressions: list[SqlRegression], period: str) -> list[dict]:
    buckets: dict[str, dict] = {}
    for sql in sql_regressions:
        cat = sql.source_category
        elapsed = sql.good_elapsed_secs if period == "good" else sql.bad_elapsed_secs
        if cat not in buckets:
            buckets[cat] = {"elapsed_secs": 0.0, "sql_count": 0}
        buckets[cat]["elapsed_secs"] += elapsed
        buckets[cat]["sql_count"] += 1

    total = sum(v["elapsed_secs"] for v in buckets.values())
    result = []
    for cat, vals in sorted(buckets.items(), key=lambda x: -x[1]["elapsed_secs"]):
        pct = (vals["elapsed_secs"] / total * 100.0) if total > 0 else 0.0
        result.append({
            "category": cat,
            "elapsed_secs": round(vals["elapsed_secs"], 2),
            "pct_total": round(pct, 2),
            "sql_count": vals["sql_count"],
        })
    return result


# ---------------------------------------------------------------------------
# E) Incident indicator detection (IMP8 integrated)
# ---------------------------------------------------------------------------

def _detect_incidents(
    good_data: dict,
    bad_data: dict,
    wait_comparisons: list[WaitEventComparison],
    sql_regressions: list[SqlRegression],
    load_deltas: list[MetricDelta],
) -> list[dict]:
    incidents: list[dict] = []

    for wc in wait_comparisons:
        if "tx" in wc.event_name.lower() and "lock" in wc.event_name.lower():
            if wc.bad_pct_db_time > 10.0:
                incidents.append({
                    "indicator": "lock_driven_freeze",
                    "severity": "critical",
                    "description": (
                        f"TX lock contention consuming {wc.bad_pct_db_time:.1f}% of DB time "
                        f"in bad period (was {wc.good_pct_db_time:.1f}% in good period)."
                    ),
                    "evidence": {"event": wc.event_name, "bad_pct_db_time": wc.bad_pct_db_time},
                    "remediation": (
                        "Identify blocking sessions via V$LOCK / DBA_BLOCKERS. "
                        "Review application commit frequency and transaction isolation."
                    ),
                })

    regressed_sql = [
        r for r in sql_regressions
        if r.tag in ("regression", "new_offender") and not r.is_oracle_maintenance
    ]
    if len(regressed_sql) >= 3:
        incidents.append({
            "indicator": "plan_flip_cascade",
            "severity": "warning",
            "description": (
                f"{len(regressed_sql)} application SQL statements show regressions."
            ),
            "evidence": {"regressed_count": len(regressed_sql), "sql_ids": [r.sql_id for r in regressed_sql[:10]]},
            "remediation": "Check DBA_HIST_SQL_PLAN for plan changes. Use DBMS_SPM to lock good plans.",
        })

    for d in load_deltas:
        if "hard parse" in d.metric.lower() and d.change_pct > 200.0:
            incidents.append({
                "indicator": "hard_parse_storm",
                "severity": "critical",
                "description": f"Hard parses increased by {d.change_pct:.0f}% ({d.good_value:.1f}/s -> {d.bad_value:.1f}/s).",
                "evidence": {"metric": d.metric, "good_value": d.good_value, "bad_value": d.bad_value},
                "remediation": "Enable CURSOR_SHARING=FORCE. Identify literal SQL in V$SQL.",
            })

    for wc in wait_comparisons:
        if wc.event_name.lower() in ("db file sequential read", "db file scattered read"):
            if wc.good_time_secs > 0 and wc.delta_pct > 200.0:
                incidents.append({
                    "indicator": "storage_degradation",
                    "severity": "critical",
                    "description": (
                        f"I/O wait '{wc.event_name}' increased by {wc.delta_pct:.0f}% "
                        f"({wc.good_time_secs:.1f}s -> {wc.bad_time_secs:.1f}s)."
                    ),
                    "evidence": {"event": wc.event_name, "delta_pct": wc.delta_pct},
                    "remediation": "Check storage latency via V$IOSTAT_FILE and OS iostat.",
                })

    # IMP8 — Extreme wait event alerts
    for wc in wait_comparisons:
        if wc.extreme_wait_flag:
            incidents.append({
                "indicator": "extreme_wait_event",
                "severity": "critical",
                "description": (
                    f"Critical Single Event: '{wc.event_name}' avg wait "
                    f"{wc.bad_avg_wait_ms / 1000.0:.1f}s (>60s threshold). "
                    f"Severe blocking regardless of %DB time ({wc.bad_pct_db_time:.1f}%)."
                ),
                "evidence": {
                    "event": wc.event_name,
                    "avg_wait_secs": round(wc.bad_avg_wait_ms / 1000.0, 2),
                    "total_waits": wc.bad_total_waits,
                },
                "remediation": f"Investigate '{wc.event_name}' via V$EVENT_HISTOGRAM.",
            })

    # ---- Direct-path read / segment invisibility detection ------------------
    # When physical_reads/s is high but read_io_requests/s is low relative to
    # phys_reads, the reads are going through direct-path (bypassing buffer cache).
    # These are INVISIBLE in Segments by Physical Reads — the segments section
    # tracks block-level reads, not direct-path I/O.  Flag this so the analyst
    # knows to look at SQL-level disk reads rather than segments.
    bad_phys_reads  = _lp_value(bad_data,  "physical read")   # blocks/s
    bad_read_io_req = _lp_value(bad_data,  "read io requests") # actual IO ops/s
    good_phys_reads = _lp_value(good_data, "physical read")
    good_read_io_req= _lp_value(good_data, "read io requests")
    # Direct-path reads typically have a high blocks-per-IO ratio (multiblock)
    # whereas index reads are 1:1.  Ratio > 10 blocks/IO → strong FTS signal.
    if bad_phys_reads > 20 and bad_read_io_req > 0:
        bad_blocks_per_io = bad_phys_reads / bad_read_io_req
        good_blocks_per_io = (good_phys_reads / good_read_io_req) if good_read_io_req > 0 else 1.0
        if bad_blocks_per_io > 10 and bad_blocks_per_io > good_blocks_per_io * 2:
            incidents.append({
                "indicator": "direct_path_full_scan",
                "severity": "warning",
                "description": (
                    f"Direct-path full-table-scan pattern detected: "
                    f"{bad_phys_reads:.0f} physical read blocks/s but only "
                    f"{bad_read_io_req:.1f} read IO requests/s "
                    f"({bad_blocks_per_io:.0f} blocks/IO — multiblock FTS signature). "
                    f"These reads bypass the buffer cache and will NOT appear in "
                    f"Segments by Physical Reads. Check SQL Ordered by Physical Reads "
                    f"for statements with high disk_reads and 0%% IO in wait events."
                ),
                "evidence": {
                    "bad_phys_reads_per_sec": round(bad_phys_reads, 1),
                    "bad_read_io_requests_per_sec": round(bad_read_io_req, 1),
                    "bad_blocks_per_io": round(bad_blocks_per_io, 1),
                    "good_blocks_per_io": round(good_blocks_per_io, 1),
                },
                "remediation": (
                    "Identify FTS statements in SQL Ordered by Physical Reads. "
                    "Run EXPLAIN PLAN on suspects — look for TABLE ACCESS FULL on large tables. "
                    "Gather up-to-date optimizer statistics (DBMS_STATS.GATHER_TABLE_STATS). "
                    "Verify indexes exist and are visible: SELECT index_name, status, visibility "
                    "FROM dba_indexes WHERE table_name = '<table>';"
                ),
            })

    # ---- Critical SQL disappeared from bad period ---------------------------
    # When a high-value SQL that ran significantly in the GOOD period is completely
    # absent from the BAD period, this is strong evidence the job failed to reach
    # that processing stage — not a normal workload shift.
    good_sql = good_data.get("sql_stats", [])
    bad_sql_ids = {s.get("sql_id", "") for s in bad_data.get("sql_stats", []) if s.get("sql_id")}
    disappeared_critical = []
    for gs in (good_sql or []):
        if not isinstance(gs, dict):
            continue
        sid = gs.get("sql_id", "")
        if not sid or sid in bad_sql_ids:
            continue
        good_elapsed = _float(gs.get("elapsed_time_secs", 0))
        good_execs   = int(_float(gs.get("executions", 0)))
        good_pct     = _float(gs.get("pct_db_time", 0))
        # Critical disappeared: ran >5% of good DB time OR >10K executions and >10s total
        if good_pct >= 5.0 or (good_execs >= 10000 and good_elapsed >= 10.0):
            disappeared_critical.append({
                "sql_id": sid,
                "good_elapsed_secs": round(good_elapsed, 2),
                "good_executions": good_execs,
                "good_pct_db_time": round(good_pct, 2),
                "module": gs.get("module", ""),
                "sql_text": (gs.get("sql_text") or "")[:120],
            })
    if disappeared_critical:
        top_d = sorted(disappeared_critical, key=lambda x: -x["good_pct_db_time"])
        top_ids = ", ".join(d["sql_id"] for d in top_d[:3])
        total_good_elapsed = sum(d["good_elapsed_secs"] for d in top_d)
        incidents.insert(0, {
            "indicator": "critical_sql_disappeared",
            "severity": "critical",
            "description": (
                f"{len(disappeared_critical)} critical SQL statement(s) present in the GOOD "
                f"period are completely absent from the BAD period AWR (top: {top_ids}). "
                f"These accounted for {total_good_elapsed:.0f}s of elapsed time in the GOOD period. "
                f"This is strong evidence the batch job or process did NOT complete its primary "
                f"processing work — it stalled, failed, or was blocked before reaching these "
                f"execution stages. The lower DB Time in the BAD period reflects less productive "
                f"work, NOT lower load."
            ),
            "evidence": {
                "disappeared_count": len(disappeared_critical),
                "top_sql_ids": [d["sql_id"] for d in top_d[:5]],
                "total_good_elapsed_secs": round(total_good_elapsed, 1),
            },
            "remediation": (
                "1. Check application/batch job logs for errors or early exits during the BAD period. "
                "2. Verify the job reached its processing stages (scheduler logs, job history). "
                "3. Identify what WAS running in BAD that prevented these SQLs from executing. "
                "4. Compare the execution plans of SQLs that ran in BAD vs GOOD for divergence signs."
            ),
        })

    # ── 1. Lock / TX Contention Storm ────────────────────────────────────────
    tx_events = [wc for wc in wait_comparisons
                 if any(k in wc.event_name.lower() for k in ("enq: tx", "row lock", "enq: tm"))]
    tx_bad_pct = sum(wc.bad_pct_db_time for wc in tx_events)
    tx_good_pct = sum(wc.good_pct_db_time for wc in tx_events)
    if tx_bad_pct > 5.0 and tx_bad_pct > tx_good_pct * 1.5:
        incidents.append({
            "indicator": "lock_tx_contention_storm",
            "severity": "critical" if tx_bad_pct > 15.0 else "warning",
            "pattern_name": "Lock / TX Contention Storm",
            "description": (
                f"TX/row-lock contention consuming {tx_bad_pct:.1f}% of DB time "
                f"(up from {tx_good_pct:.1f}%). Blocking chains likely active."
            ),
            "evidence": {"events": [wc.event_name for wc in tx_events], "bad_pct_db_time": tx_bad_pct},
            "remediation": (
                "Run ASH blocker tree to identify blockers. "
                "Review application commit frequency and transaction isolation."
            ),
            "next_step": "ASH blocker tree",
            "diagnostic_sql": (
                "SELECT blocking_session, sid, wait_class, event, seconds_in_wait, sql_id "
                "FROM v$session WHERE blocking_session IS NOT NULL ORDER BY seconds_in_wait DESC;"
            ),
        })

    # ── 2. Hot Block Contention ───────────────────────────────────────────────
    hot_block_events = [wc for wc in wait_comparisons
                        if any(k in wc.event_name.lower()
                               for k in ("buffer busy", "read by other session",
                                         "cache buffers chains", "gc buffer busy"))]
    hb_bad_pct = sum(wc.bad_pct_db_time for wc in hot_block_events)
    hb_good_pct = sum(wc.good_pct_db_time for wc in hot_block_events)
    if hb_bad_pct > 3.0 and hb_bad_pct > hb_good_pct * 2.0:
        incidents.append({
            "indicator": "hot_block_contention",
            "severity": "critical" if hb_bad_pct > 10.0 else "warning",
            "pattern_name": "Hot Block Contention",
            "description": (
                f"Hot block waits ({', '.join(wc.event_name for wc in hot_block_events[:2])}) "
                f"total {hb_bad_pct:.1f}% DB time (was {hb_good_pct:.1f}%). "
                "Indicates hot index/table blocks — monotonic keys or block-level row clustering."
            ),
            "evidence": {"events": [wc.event_name for wc in hot_block_events], "bad_pct_db_time": hb_bad_pct},
            "remediation": (
                "Check V$SEGSTAT / DBA_HIST_SEG_STAT for segments with high buffer_busy_waits. "
                "Consider reverse-key indexes for monotonic columns. "
                "Use DBMS_SPACE.OBJECT_SPACE_USAGE to find hot objects."
            ),
            "next_step": "Wait-class drilldown → Concurrency",
            "diagnostic_sql": (
                "SELECT object_name, object_type, value "
                "FROM v$segstat s JOIN dba_objects o ON s.obj# = o.object_id "
                "WHERE statistic_name = 'buffer busy waits' ORDER BY value DESC FETCH FIRST 10 ROWS ONLY;"
            ),
        })

    # ── 3. Log Switch / Redo File Undersizing ────────────────────────────────
    log_switch_events = [wc for wc in wait_comparisons
                         if "log file switch" in wc.event_name.lower()]
    ls_bad_pct = sum(wc.bad_pct_db_time for wc in log_switch_events)
    redo_delta = next((d for d in load_deltas if "redo size" in d.metric.lower()), None)
    if ls_bad_pct > 1.0 or (redo_delta and redo_delta.change_pct > 100.0 and log_switch_events):
        incidents.append({
            "indicator": "log_switch_undersizing",
            "severity": "warning",
            "pattern_name": "Log Switch / Redo File Undersizing",
            "description": (
                f"Log file switch waits present ({ls_bad_pct:.1f}% DB time). "
                + (f"Redo generation increased {redo_delta.change_pct:.0f}%." if redo_delta else "")
                + " Small redo logs cause frequent checkpoints and log switches."
            ),
            "evidence": {
                "log_switch_pct_db_time": ls_bad_pct,
                "redo_delta_pct": redo_delta.change_pct if redo_delta else 0,
            },
            "remediation": (
                "Check current redo log size: SELECT GROUP#, BYTES/1048576 AS MB FROM V$LOG. "
                "Target 15–30 minute switch interval. Resize logs to match redo generation rate."
            ),
            "next_step": "File I/O stats → redo log performance",
            "diagnostic_sql": (
                "SELECT group#, sequence#, bytes/1048576 AS mb, status "
                "FROM v$log ORDER BY group#;"
            ),
        })

    # ── 4. Log Buffer Pressure ────────────────────────────────────────────────
    log_buf_events = [wc for wc in wait_comparisons
                      if "log buffer space" in wc.event_name.lower()]
    lb_bad_pct = sum(wc.bad_pct_db_time for wc in log_buf_events)
    if lb_bad_pct > 0.5:
        incidents.append({
            "indicator": "log_buffer_pressure",
            "severity": "warning",
            "pattern_name": "Log Buffer Pressure",
            "description": (
                f"'log buffer space' waits = {lb_bad_pct:.2f}% DB time. "
                "LGWR cannot flush redo fast enough — sessions stall writing redo entries."
            ),
            "evidence": {"bad_pct_db_time": lb_bad_pct},
            "remediation": (
                "Increase LOG_BUFFER init parameter (default 3–8 MB; try 32–64 MB for write-heavy workloads). "
                "Check redo log storage latency. Ensure redo logs are on separate fast storage."
            ),
            "next_step": "File I/O stats → redo path",
            "diagnostic_sql": (
                "SELECT name, value FROM v$sysstat "
                "WHERE name IN ('redo log space requests', 'redo buffer allocation retries');"
            ),
        })

    # ── 5. Temp Spill / Workarea Starvation ──────────────────────────────────
    temp_events = [wc for wc in wait_comparisons
                   if any(k in wc.event_name.lower()
                          for k in ("direct path read temp", "direct path write temp",
                                    "direct path write", "direct path read"))]
    temp_bad_pct = sum(wc.bad_pct_db_time for wc in temp_events)
    temp_good_pct = sum(wc.good_pct_db_time for wc in temp_events)
    pga_delta = next((d for d in load_deltas if "pga" in d.metric.lower()), None)
    if temp_bad_pct > 2.0 and temp_bad_pct > temp_good_pct * 1.5:
        incidents.append({
            "indicator": "temp_spill_workarea_starvation",
            "severity": "critical" if temp_bad_pct > 10.0 else "warning",
            "pattern_name": "Temp Spill / Workarea Starvation",
            "description": (
                f"Temp I/O waits = {temp_bad_pct:.1f}% DB time (was {temp_good_pct:.1f}%). "
                "Sorts/hash joins are spilling to disk — PGA workarea too small or query plans suboptimal."
            ),
            "evidence": {
                "events": [wc.event_name for wc in temp_events],
                "bad_pct_db_time": temp_bad_pct,
            },
            "remediation": (
                "Check PGA_AGGREGATE_TARGET and workarea auto-tuning. "
                "Identify spilling SQL via V$SQL_WORKAREA_HISTOGRAM. "
                "Review join order and missing indexes for hash/sort operations."
            ),
            "next_step": "SQL Monitor report for spilling SQL",
            "diagnostic_sql": (
                "SELECT sql_id, operation_type, policy, estimated_optimal_size/1024 AS optimal_kb, "
                "last_memory_used/1024 AS used_kb, last_execution "
                "FROM v$sql_workarea_active ORDER BY last_memory_used DESC FETCH FIRST 10 ROWS ONLY;"
            ),
        })

    # ── 6. Undo Pressure / Snapshot Too Old Risk ─────────────────────────────
    undo_events = [wc for wc in wait_comparisons
                   if any(k in wc.event_name.lower()
                          for k in ("undo segment", "transaction", "snapshot too old",
                                    "enq: us -"))]
    dml_delta = next((d for d in load_deltas
                      if any(k in d.metric.lower() for k in ("user commits", "user rollbacks"))), None)
    if undo_events or (dml_delta and dml_delta.change_pct > 200.0):
        undo_bad_pct = sum(wc.bad_pct_db_time for wc in undo_events)
        incidents.append({
            "indicator": "undo_pressure",
            "severity": "warning",
            "pattern_name": "Undo Pressure / Snapshot Risk",
            "description": (
                f"Undo-related contention detected ({undo_bad_pct:.1f}% DB time). "
                + (f"DML volume increased {dml_delta.change_pct:.0f}%." if dml_delta else "")
                + " Long readers against changing data risk ORA-01555 snapshot too old errors."
            ),
            "evidence": {
                "events": [wc.event_name for wc in undo_events],
                "dml_delta_pct": dml_delta.change_pct if dml_delta else 0,
            },
            "remediation": (
                "Check UNDO_RETENTION vs query duration. "
                "Run: SELECT name, value FROM v$parameter WHERE name LIKE 'undo%'. "
                "Review DBA_UNDO_EXTENTS for shrinkage under pressure."
            ),
            "next_step": "Compare periods — DML volume change",
            "diagnostic_sql": (
                "SELECT tablespace_name, status, SUM(bytes)/1048576 AS mb "
                "FROM dba_undo_extents GROUP BY tablespace_name, status ORDER BY status;"
            ),
        })

    # ── 7. Connection / Session Storm ────────────────────────────────────────
    logon_delta = next((d for d in load_deltas
                        if "logon" in d.metric.lower()), None)
    good_sessions = int(_float(good_data.get("logons_current_begin", 0)))
    bad_sessions  = int(_float(bad_data.get("logons_current_begin", 0)))
    session_surge = (bad_sessions > good_sessions * 1.5 and bad_sessions > 50)
    logon_surge   = logon_delta and logon_delta.change_pct > 100.0
    if session_surge or logon_surge:
        incidents.append({
            "indicator": "connection_session_storm",
            "severity": "critical" if (session_surge and bad_sessions > good_sessions * 2) else "warning",
            "pattern_name": "Connection / Session Storm",
            "description": (
                f"Session count surged from {good_sessions} to {bad_sessions} "
                f"({'+' if bad_sessions > good_sessions else ''}{bad_sessions - good_sessions} sessions). "
                + (f"Logon rate increased {logon_delta.change_pct:.0f}%." if logon_delta else "")
                + " Application retry loops, pool leaks, or traffic surge likely."
            ),
            "evidence": {
                "good_sessions": good_sessions,
                "bad_sessions": bad_sessions,
                "logon_delta_pct": logon_delta.change_pct if logon_delta else 0,
            },
            "remediation": (
                "Check V$SESSION for session sources (PROGRAM, MACHINE, USERNAME). "
                "Review application connection pool settings and retry logic. "
                "Consider DRCP (Database Resident Connection Pooling) for short-lived connections."
            ),
            "next_step": "ASH blocker tree — session distribution",
            "diagnostic_sql": (
                "SELECT username, program, machine, status, COUNT(*) AS cnt "
                "FROM v$session WHERE type = 'USER' "
                "GROUP BY username, program, machine, status ORDER BY cnt DESC;"
            ),
        })

    # ── 8. Network Stall Pattern ─────────────────────────────────────────────
    net_events = [wc for wc in wait_comparisons
                  if wc.event_name.lower().startswith(("sql*net", "oracle net"))]
    net_bad_pct = sum(wc.bad_pct_db_time for wc in net_events)
    net_good_pct = sum(wc.good_pct_db_time for wc in net_events)
    if net_bad_pct > 2.0 and net_bad_pct > net_good_pct * 2.0:
        incidents.append({
            "indicator": "network_stall",
            "severity": "warning",
            "pattern_name": "Network Stall Pattern",
            "description": (
                f"SQL*Net / Oracle Net waits = {net_bad_pct:.1f}% DB time (was {net_good_pct:.1f}%). "
                "Problem is likely OUTSIDE the database: slow client fetches, "
                "app-server latency, or chatty row-by-row fetch behavior."
            ),
            "evidence": {"events": [wc.event_name for wc in net_events], "bad_pct_db_time": net_bad_pct},
            "remediation": (
                "Check array fetch size (SDU, TDU, ARRAYSIZE). "
                "Use SQL*Net tracing to identify chatty clients. "
                "Verify network path latency between app and DB tiers."
            ),
            "next_step": "Wait-class drilldown → Network class",
            "diagnostic_sql": (
                "SELECT wait_class, event, total_waits, time_waited/100 AS time_s "
                "FROM v$system_event WHERE wait_class = 'Network' ORDER BY time_waited DESC;"
            ),
        })

    # ── 9. Configuration Bottleneck ──────────────────────────────────────────
    config_events = [wc for wc in wait_comparisons
                     if wc.event_name.lower().startswith(("resmgr", "resource manager",
                                                          "shared server", "dispatcher"))]
    cfg_bad_pct = sum(wc.bad_pct_db_time for wc in config_events)
    cfg_good_pct = sum(wc.good_pct_db_time for wc in config_events)
    mem_delta = next((d for d in load_deltas
                      if any(k in d.metric.lower() for k in ("sga", "pga target"))), None)
    if cfg_bad_pct > 2.0 and cfg_bad_pct > cfg_good_pct * 2.0:
        incidents.append({
            "indicator": "configuration_bottleneck",
            "severity": "warning",
            "pattern_name": "Configuration Bottleneck",
            "description": (
                f"Resource Manager / configuration wait events = {cfg_bad_pct:.1f}% DB time "
                f"(was {cfg_good_pct:.1f}%). Workload being throttled by Resource Manager plans "
                "or session/process limits."
            ),
            "evidence": {"events": [wc.event_name for wc in config_events], "bad_pct_db_time": cfg_bad_pct},
            "remediation": (
                "Check current Resource Manager plan: SELECT name FROM v$rsrc_plan WHERE is_top_plan = 'TRUE'. "
                "Review PROCESSES, SESSIONS init parameters. "
                "Verify memory targets (SGA_TARGET, PGA_AGGREGATE_TARGET) vs actual workload."
            ),
            "next_step": "Wait-class drilldown → Configuration class",
            "diagnostic_sql": (
                "SELECT consumer_group_name, requests, cpu_wait_time, cpu_waits "
                "FROM v$rsrc_consumer_group ORDER BY cpu_wait_time DESC;"
            ),
        })

    # ── 10. Scheduler / Job Collision ────────────────────────────────────────
    # Proxy: maintenance SQL active + high RMAN/stats waits in bad period
    maint_sql_active = [sr for sr in sql_regressions if sr.is_oracle_maintenance
                        and sr.tag in ("regression", "new_offender")]
    rman_events = [wc for wc in wait_comparisons
                   if any(k in wc.event_name.lower() for k in ("backup", "rman", "control file"))]
    rman_bad_pct = sum(wc.bad_pct_db_time for wc in rman_events)
    if len(maint_sql_active) >= 2 or rman_bad_pct > 5.0:
        incidents.append({
            "indicator": "scheduler_job_collision",
            "severity": "warning",
            "pattern_name": "Scheduler / Job Collision",
            "description": (
                f"{len(maint_sql_active)} Oracle maintenance SQL(s) regressed. "
                + (f"RMAN/backup waits = {rman_bad_pct:.1f}% DB time. " if rman_bad_pct > 0 else "")
                + "Overlapping maintenance windows colliding with application workload."
            ),
            "evidence": {
                "maint_sql_count": len(maint_sql_active),
                "rman_pct_db_time": rman_bad_pct,
                "maint_sql_ids": [sr.sql_id for sr in maint_sql_active[:5]],
            },
            "remediation": (
                "Check DBA_SCHEDULER_JOBS for overlapping job windows. "
                "Move stats gathering, RMAN, and purge jobs to a dedicated maintenance window. "
                "Use DBMS_SCHEDULER.SET_ATTRIBUTE to adjust job priorities and windows."
            ),
            "next_step": "Compare periods — batch window good vs bad",
            "diagnostic_sql": (
                "SELECT job_name, job_class, enabled, state, last_start_date, run_duration "
                "FROM dba_scheduler_jobs WHERE enabled = 'TRUE' ORDER BY last_start_date DESC;"
            ),
        })

    # ── 11. RAC Interconnect / GC Storm ──────────────────────────────────────
    rac_events = [wc for wc in wait_comparisons
                  if any(k in wc.event_name.lower()
                         for k in ("gc cr request", "gc buffer busy", "gc current request",
                                   "gc cr block", "gc current block", "cluster"))]
    rac_bad_pct = sum(wc.bad_pct_db_time for wc in rac_events)
    rac_good_pct = sum(wc.good_pct_db_time for wc in rac_events)
    if rac_bad_pct > 3.0 and rac_bad_pct > rac_good_pct * 1.5:
        incidents.append({
            "indicator": "rac_gc_storm",
            "severity": "critical" if rac_bad_pct > 15.0 else "warning",
            "pattern_name": "RAC Interconnect / GC Storm",
            "description": (
                f"RAC Global Cache waits = {rac_bad_pct:.1f}% DB time (was {rac_good_pct:.1f}%). "
                "Cross-instance block pinging or interconnect saturation detected."
            ),
            "evidence": {"events": [wc.event_name for wc in rac_events], "bad_pct_db_time": rac_bad_pct},
            "remediation": (
                "Check GV$SEGMENT_STATISTICS for segments with high GC waits. "
                "Review service placement (application should connect to the same instance as its data). "
                "Check interconnect utilization via GV$CLUSTER_INTERCONNECTS."
            ),
            "next_step": "Wait-class drilldown → Cluster class",
            "diagnostic_sql": (
                "SELECT inst_id, event, total_waits, average_wait "
                "FROM gv$system_event WHERE wait_class = 'Cluster' "
                "ORDER BY average_wait DESC FETCH FIRST 20 ROWS ONLY;"
            ),
        })

    # ── 12. Long-Running SQL Regression ──────────────────────────────────────
    long_sql = [sr for sr in sql_regressions
                if sr.tag in ("regression", "new_offender")
                and not sr.is_oracle_maintenance
                and sr.bad_elapsed_secs > 60.0]   # >60s total in bad period
    if long_sql:
        top = sorted(long_sql, key=lambda r: -r.bad_elapsed_secs)
        worst = top[0]
        incidents.append({
            "indicator": "long_running_sql_regression",
            "severity": "critical" if worst.bad_elapsed_secs > 300.0 else "warning",
            "pattern_name": "Long-Running SQL Regression",
            "description": (
                f"{len(long_sql)} SQL statement(s) running significantly longer than baseline. "
                f"Worst: SQL {worst.sql_id} — {worst.good_elapsed_secs:.0f}s → {worst.bad_elapsed_secs:.0f}s "
                f"({worst.delta_pct:+.0f}%). "
                + ("Plan changed. " if worst.plan_changed else "")
                + "Likely plan regression, stale stats, or bind variable skew."
            ),
            "evidence": {
                "count": len(long_sql),
                "worst_sql_id": worst.sql_id,
                "worst_bad_elapsed": round(worst.bad_elapsed_secs, 1),
                "plan_changed": worst.plan_changed,
            },
            "remediation": (
                "Use Real-Time SQL Monitoring for execution-level visibility. "
                "Compare plans: SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR('<sql_id>')); "
                "Gather fresh statistics or use SQL Plan Baseline to lock good plan."
            ),
            "next_step": "SQL Monitor report",
            "diagnostic_sql": (
                "SELECT sql_id, plan_hash_value, executions, "
                "elapsed_time/1e6 AS elapsed_s, cpu_time/1e6 AS cpu_s "
                "FROM dba_hist_sqlstat WHERE sql_id = '{sql_id}' ORDER BY snap_id DESC;"
            ).replace("{sql_id}", worst.sql_id),
        })

    return incidents


# ---------------------------------------------------------------------------
# Recommendation generator
# ---------------------------------------------------------------------------

def _generate_recommendations(
    load_deltas: list[MetricDelta],
    wait_comparisons: list[WaitEventComparison],
    efficiency_comparisons: list[EfficiencyComparison],
    sql_regressions: list[SqlRegression],
    incidents: list[dict],
    logon_storm_explanation: str,
) -> list[Recommendation]:
    recs: list[Recommendation] = []

    # IMP4 — Logon storm as top recommendation
    if logon_storm_explanation:
        recs.append(Recommendation(
            priority=1,
            category="Connection Pool",
            finding="Logon storm \u2192 Execute-to-Parse degradation detected",
            action=logon_storm_explanation,
            oracle_fix="SELECT username, program, machine, count(*) FROM v$session GROUP BY username, program, machine ORDER BY 4 DESC;",
            impact="Primary driver of cursor cache invalidation and hard parse load",
            reference="Oracle DRCP and Connection Pool Best Practices",
        ))

    for inc in incidents:
        severity = inc.get("severity", "info")
        priority = 1 if severity == "critical" else 2
        recs.append(Recommendation(
            priority=priority,
            category="Incident",
            finding=inc["description"],
            action=inc.get("remediation", ""),
            oracle_fix="",
            impact="Direct impact on DB availability or response time",
            reference="Oracle Support: AWR Incident Analysis",
        ))

    for wc in wait_comparisons:
        if wc.classification in ("new_bottleneck", "worsening"):
            priority = 1 if wc.bad_pct_db_time > 20.0 else 2
            finding = (
                f"Wait event '{wc.event_name}' classified as {wc.classification}: "
                f"{wc.good_time_secs:.1f}s -> {wc.bad_time_secs:.1f}s ({wc.delta_pct:+.0f}%)"
            )
            if wc.latency_flag == "volume_increase":
                finding += " [Volume increase \u2014 stable latency, more waits]"
            elif wc.latency_flag == "latency_increase":
                finding += " [Latency increase \u2014 storage/contention problem]"
            elif wc.latency_flag == "both":
                finding += " [Both volume and latency increased]"

            recs.append(Recommendation(
                priority=priority,
                category="Concurrency" if "lock" in wc.event_name.lower() or "latch" in wc.event_name.lower() else "I/O",
                finding=finding,
                action=wc.root_cause_hint or f"Investigate {wc.event_name} root cause",
                oracle_fix=f"SELECT * FROM V$EVENT_HISTOGRAM WHERE event = '{wc.event_name}';",
                impact=f"{wc.bad_pct_db_time:.1f}% of DB time in bad period",
                reference="Oracle Wait Event Reference",
            ))

    for sr in sql_regressions:
        if sr.tag in ("new_offender", "regression") and not sr.is_oracle_maintenance:
            priority = 1 if sr.severity == "critical" else 2
            finding = (
                f"SQL {sr.sql_id} tagged as {sr.tag}: "
                f"elapsed {sr.good_elapsed_secs:.1f}s -> {sr.bad_elapsed_secs:.1f}s ({sr.delta_pct:+.0f}%)"
            )
            action = "Check execution plan changes with DBMS_XPLAN.DISPLAY_AWR."
            # IMP3 — context-aware SPM recommendation
            if sr.plan_changed and "REGRESSED" in sr.plan_verdict:
                action += " Plan change caused regression \u2014 consider SQL Plan Baseline (DBMS_SPM)."
            elif sr.plan_changed and "IMPROVED" in sr.plan_verdict:
                action = "Plan changed but per-exec performance IMPROVED. No action needed."
            elif sr.plan_changed and "STABLE" in sr.plan_verdict:
                action = "Plan changed but per-exec performance is STABLE. Monitor only."

            recs.append(Recommendation(
                priority=priority,
                category="SQL",
                finding=finding,
                action=action,
                oracle_fix=f"SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR('{sr.sql_id}'));",
                impact=f"{sr.bad_elapsed_secs:.1f}s total elapsed in bad period",
                reference="Oracle SQL Tuning Guide",
            ))

    # IMP2 — maintenance SQL grouped recommendation
    maint_regressions = [sr for sr in sql_regressions if sr.is_oracle_maintenance and sr.tag == "regression"]
    if maint_regressions:
        sql_ids = ", ".join(s.sql_id for s in maint_regressions[:5])
        total_elapsed = sum(s.bad_elapsed_secs for s in maint_regressions)
        recs.append(Recommendation(
            priority=2,
            category="Maintenance Scheduling",
            finding=f"{len(maint_regressions)} Oracle maintenance SQL(s) regressed ({sql_ids}), consuming {total_elapsed:.0f}s total.",
            action="Review DBMS_SCHEDULER job windows. Move maintenance to off-peak hours.",
            oracle_fix="SELECT job_name, enabled, state, last_start_date FROM dba_scheduler_jobs WHERE enabled = 'TRUE' ORDER BY last_start_date DESC;",
            impact=f"{total_elapsed:.0f}s maintenance overhead in bad period",
            reference="Oracle Auto Maintenance Tasks Management",
        ))

    for ec in efficiency_comparisons:
        if ec.severity in ("critical", "warning"):
            priority = 1 if ec.severity == "critical" else 2
            recs.append(Recommendation(
                priority=priority,
                category="Memory" if "cache" in ec.metric.lower() else "Configuration",
                finding=ec.message,
                action=f"Review {ec.metric} and associated SGA/PGA parameters",
                oracle_fix="",
                impact=f"Degraded from {ec.good_val:.1f}% to {ec.bad_val:.1f}%",
                reference="Oracle Instance Tuning Guide",
            ))

    for ld in load_deltas:
        if ld.severity == "critical" and ld.direction == "regression":
            recs.append(Recommendation(
                priority=2,
                category="Configuration",
                finding=f"Load profile metric '{ld.metric}' regressed by {ld.change_pct:+.0f}% ({ld.good_value:.1f} -> {ld.bad_value:.1f})",
                action="Investigate workload change or configuration drift",
                oracle_fix="",
                impact="Significant workload increase detected",
                reference="Oracle Load Profile Analysis",
            ))

    # De-duplicate
    seen: set[str] = set()
    unique: list[Recommendation] = []
    for r in sorted(recs, key=lambda x: x.priority):
        key = r.finding[:100]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    unique.sort(key=lambda r: r.priority)
    return unique


# ---------------------------------------------------------------------------
# Overall severity classifier
# ---------------------------------------------------------------------------

def _classify_overall_severity(health_good: int, health_bad: int, incidents: list[dict]) -> tuple[str, str]:
    score_drop = health_good - health_bad
    critical_incidents = [i for i in incidents if i.get("severity") == "critical"]

    if critical_incidents or score_drop >= 40 or health_bad < 50:
        severity = "critical"
        desc = f"Critical regression: health score {health_good} → {health_bad} ({score_drop:+d} pts). {len(critical_incidents)} critical incident(s)."
    elif score_drop >= 15 or health_bad < 70:
        severity = "degraded"
        desc = f"Performance degradation: health score {health_good} → {health_bad} ({score_drop:+d} pts)."
    else:
        severity = "healthy"
        desc = f"No significant regression: health score {health_good} → {health_bad} ({score_drop:+d} pts)."

    return desc, severity


# ---------------------------------------------------------------------------
# Bottleneck type classifier
# ---------------------------------------------------------------------------

def _classify_bottleneck(data: dict) -> str:
    """Classify the primary bottleneck type from wait events."""
    events = data.get("wait_events", [])
    if not events:
        return "Unknown"
    
    cpu_pct = 0.0
    io_pct = 0.0
    concurrency_pct = 0.0
    
    for ev in events:
        if not isinstance(ev, dict):
            continue
        pct = _float(ev.get("pct_db_time", 0))
        wclass = (ev.get("wait_class", "") or "").lower()
        ename = (ev.get("event_name", "") or "").lower()
        
        if "cpu" in ename or wclass == "cpu":
            cpu_pct += pct
        elif wclass in ("user i/o", "system i/o") or "i/o" in wclass:
            io_pct += pct
        elif wclass in ("concurrency", "application") or "lock" in ename or "latch" in ename:
            concurrency_pct += pct
    
    top_type = max([("CPU", cpu_pct), ("I/O", io_pct), ("Concurrency", concurrency_pct)], key=lambda x: x[1])
    return top_type[0] if top_type[1] > 5 else "Mixed"


# ---------------------------------------------------------------------------
# Evidence-based headline generator (RULE: headline must answer
# "what changed and why did DB Time rise?")
# ---------------------------------------------------------------------------

def _generate_evidence_headline(
    good_data: dict,
    bad_data: dict,
    good_summary: "PeriodSummary",
    bad_summary: "PeriodSummary",
    sql_regressions: list[SqlRegression],
    wait_comparisons: list[WaitEventComparison],
    logon_storm: str,
    good_bottleneck: str,
    bad_bottleneck: str,
) -> tuple[str, list[str]]:
    """Generate a pinpointed, evidence-backed headline.
    
    Returns (headline_text, list_of_evidence_strings).
    Rules:
    - Do NOT say 'New workload injection' if maintenance SQLs are also present
    - Do NOT say 'Plan regression' unless per-exec worsened AND plan hash changed
    - Do NOT say 'CPU bottleneck worsened' if both periods have same bottleneck at similar %
    - DO answer: what changed between the two periods and why did DB Time rise
    """
    evidence: list[str] = []
    drivers: list[str] = []
    
    # 1. DB Time delta
    db_time_delta_pct = 0.0
    if good_summary.db_time_secs > 0:
        db_time_delta_pct = ((bad_summary.db_time_secs - good_summary.db_time_secs) / good_summary.db_time_secs) * 100.0
    
    if abs(db_time_delta_pct) < 5:
        return (
            f"DB Time stable ({db_time_delta_pct:+.0f}%). Both periods are {bad_bottleneck}-bound. No significant regression detected.",
            [f"DB Time: {good_summary.db_time_secs:.0f}s → {bad_summary.db_time_secs:.0f}s ({db_time_delta_pct:+.0f}%)"]
        )

    # ---- DB Time INVERSION guard: lower DB Time + lower throughput = stall ----
    # When bad DB Time is lower than good, a naive reading calls it an improvement.
    # But if throughput (txn/s) ALSO fell and fell proportionally MORE than DB Time,
    # the database did LESS productive work — consistent with a job failure, stall,
    # or blocking before primary processing stages reached.
    good_txn = good_summary.txn_per_sec
    bad_txn  = bad_summary.txn_per_sec
    txn_delta_pct_eh = ((bad_txn - good_txn) / good_txn * 100.0) if good_txn > 0 else 0.0
    if (
        good_summary.txn_per_sec_available
        and bad_summary.txn_per_sec_available
        and db_time_delta_pct < -5.0
        and txn_delta_pct_eh < -5.0
    ):
        good_db_per_txn = (good_summary.db_time_secs / max(good_txn * good_summary.elapsed_secs, 1.0))
        bad_db_per_txn  = (bad_summary.db_time_secs  / max(bad_txn  * bad_summary.elapsed_secs,  1.0))
        db_per_txn_delta = ((bad_db_per_txn - good_db_per_txn) / max(good_db_per_txn, 0.0001)) * 100.0
        if txn_delta_pct_eh < db_time_delta_pct - 5.0:
            stall_evidence = [
                f"DB Time fell {abs(db_time_delta_pct):.0f}% ({good_summary.db_time_secs:.0f}s → {bad_summary.db_time_secs:.0f}s) — LESS work completed, not faster execution",
                f"Transactions/sec fell {abs(txn_delta_pct_eh):.0f}% ({good_txn:.2f} → {bad_txn:.2f}/s) — throughput collapse",
                f"DB Time per transaction rose +{db_per_txn_delta:.0f}% — each remaining transaction is more expensive",
            ]
            stall_headline = (
                f"THROUGHPUT COLLAPSE — DB Time fell {abs(db_time_delta_pct):.0f}% but transactions/sec also fell "
                f"{abs(txn_delta_pct_eh):.0f}%. This is NOT an improvement: the bad period completed less productive "
                f"work per unit of time. Likely cause: job failure, early stall, or blocking before primary processing stages."
            )
            return stall_headline, stall_evidence

    evidence.append(f"DB Time {db_time_delta_pct:+.0f}% ({good_summary.db_time_secs:.0f}s → {bad_summary.db_time_secs:.0f}s)")
    
    # 2. Bottleneck shift
    if good_bottleneck == bad_bottleneck:
        evidence.append(f"Both periods are {bad_bottleneck}-bound (bottleneck type unchanged)")
    else:
        evidence.append(f"Bottleneck shifted: {good_bottleneck} → {bad_bottleneck}")
        drivers.append(f"bottleneck shift {good_bottleneck}→{bad_bottleneck}")
    
    # 3. New application SQL (excluding maintenance)
    new_app_sql = [s for s in sql_regressions if s.tag == "new_offender" and not s.is_oracle_maintenance]
    new_maint_sql = [s for s in sql_regressions if s.tag == "new_offender" and s.is_oracle_maintenance]
    regressed_sql = [s for s in sql_regressions if s.tag == "regression" and not s.is_oracle_maintenance]
    plan_regressed = [s for s in sql_regressions if s.plan_changed and "REGRESSED" in s.plan_verdict]
    
    if new_app_sql:
        top_new = sorted(new_app_sql, key=lambda s: s.bad_elapsed_secs, reverse=True)
        top_id = top_new[0].sql_id
        top_elapsed = top_new[0].bad_elapsed_secs
        drivers.append(f"{len(new_app_sql)} new application SQL(s) (top: {top_id}, {top_elapsed:.0f}s)")
        evidence.append(f"New SQL: {len(new_app_sql)} previously unseen, top={top_id} ({top_elapsed:.0f}s)")
    
    if new_maint_sql:
        total_maint_elapsed = sum(s.bad_elapsed_secs for s in new_maint_sql)
        evidence.append(f"Oracle maintenance: {len(new_maint_sql)} auto-stats/purge SQL(s) ({total_maint_elapsed:.0f}s total)")
        if total_maint_elapsed > 60:
            drivers.append(f"Oracle auto-maintenance ({total_maint_elapsed:.0f}s)")
    
    # 4. Plan regressions (only if per-exec actually worsened)
    if plan_regressed:
        ids = ", ".join(s.sql_id for s in plan_regressed[:3])
        drivers.append(f"{len(plan_regressed)} plan regression(s): {ids}")
        evidence.append(f"Plan changes with per-exec degradation: {ids}")
    
    # 5. SQL regressions (same plan, worse performance)
    same_plan_regressed = [s for s in regressed_sql if not s.plan_changed]
    if same_plan_regressed:
        total_delta = sum(s.bad_elapsed_secs - s.good_elapsed_secs for s in same_plan_regressed if s.good_elapsed_secs > 0)
        if total_delta > 10:
            evidence.append(f"{len(same_plan_regressed)} SQL(s) regressed without plan change (+{total_delta:.0f}s cumulative)")
    
    # 6. Logon storm
    if logon_storm:
        drivers.append("connection pool logon storm → parse storm")
        evidence.append("Logon storm detected: E2P degradation from new session flood")
    
    # 7. Wait event changes
    worsened_waits = [w for w in wait_comparisons if w.classification == "worsening" and w.bad_pct_db_time > 5]
    new_waits = [w for w in wait_comparisons if w.classification == "new_bottleneck" and w.bad_pct_db_time > 5]
    if worsened_waits:
        top_wait = max(worsened_waits, key=lambda w: w.bad_pct_db_time)
        evidence.append(f"Top worsened wait: '{top_wait.event_name}' {top_wait.good_pct_db_time:.1f}%→{top_wait.bad_pct_db_time:.1f}% DB Time")
    if new_waits:
        for nw in new_waits[:2]:
            drivers.append(f"new wait '{nw.event_name}' ({nw.bad_pct_db_time:.1f}% DB Time)")
    
    # 8. Execution rate change
    good_exec_rate = _lp_value(good_data, "execute", "user call")
    bad_exec_rate = _lp_value(bad_data, "execute", "user call")
    if good_exec_rate > 0 and bad_exec_rate > 0:
        exec_delta = ((bad_exec_rate - good_exec_rate) / good_exec_rate) * 100.0
        if abs(exec_delta) > 50:
            evidence.append(f"Execution rate {exec_delta:+.0f}% ({good_exec_rate:.0f}/s → {bad_exec_rate:.0f}/s)")
            if exec_delta > 100:
                drivers.append(f"execution rate surge +{exec_delta:.0f}%")
    
    # Build headline
    direction = "rose" if db_time_delta_pct > 0 else "fell"
    if not drivers:
        headline = (
            f"DB Time {direction} {abs(db_time_delta_pct):.0f}%. "
            f"Both periods {bad_bottleneck}-bound — no single dominant cause identified. "
            f"Review load profile deltas for workload composition changes."
        )
    else:
        driver_text = " + ".join(drivers[:3])
        headline = f"DB Time {direction} {abs(db_time_delta_pct):.0f}% driven by: {driver_text}."
    
    return headline, evidence


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Normalized Comparison — canonical single source of truth
# ---------------------------------------------------------------------------

_LP_SPEC: list[tuple[str, str, str, bool, str]] = [
    # (lp_key, label, unit, higher_is_bad, explanation)
    ("db_time",        "DB Time/sec",         "/sec", True,  "Total database work per second. Core workload intensity metric."),
    ("db_cpu",         "DB CPU/sec",           "/sec", True,  "CPU consumed by database per second. Increasing means more compute demand."),
    ("logical_reads",  "Logical Reads/sec",    "/sec", True,  "Buffer gets per second. High values indicate intensive SQL scanning."),
    ("physical_reads", "Physical Reads/sec",   "/sec", True,  "Disk read blocks per second. High value with low Read IO Requests/s = large multi-block full-table scans (direct-path, invisible to Segments section). High value with proportionally high Read IO Requests/s = many single-block index reads. Compare both metrics together."),
    ("physical_writes","Physical Writes/sec",  "/sec", True,  "Disk writes per second. Increase may indicate more DML or redo/undo activity."),
    ("redo_size",      "Redo Size/sec",        "/sec", True,  "Bytes of redo generated per second. Higher means more DML workload."),
    ("hard_parses",    "Hard Parses/sec",      "/sec", True,  "Hard parses per second. >100/s indicates literal SQL or cursor invalidation."),
    ("parses",         "Total Parses/sec",     "/sec", True,  "All parses per second. Drives CPU overhead and shared pool pressure."),
    ("executes",       "Executes/sec",         "/sec", False, "SQL executions per second. Application throughput indicator."),
    ("transactions",   "Transactions/sec",     "/sec", False, "User commits+rollbacks per second. Primary business throughput KPI."),
    ("logons",         "Logons/sec",           "/sec", True,  "New session creations per second. Spike signals connection pool churn."),
    ("user_calls",     "User Calls/sec",       "/sec", False, "User-originated calls per second. Overall application request rate."),
    ("sorts",          "Sorts/sec",            "/sec", True,  "Sort operations per second. High PGA usage if disk sorts occur."),
    ("block_changes",  "Block Changes/sec",    "/sec", True,  "Buffer blocks modified per second. Correlates with redo and DML volume."),
]

_EFF_SPEC: list[tuple[str, str, str, bool, list[float], str]] = [
    # (eff_key, label, unit, higher_is_bad, [good_thresh, warn_thresh], explanation)
    ("buffer_cache_hit_pct",  "Buffer Cache Hit %",  "%", False, [99.0, 95.0], "Data found in RAM vs disk. <95% = excessive physical I/O."),
    ("library_cache_hit_pct", "Library Cache Hit %", "%", False, [99.0, 97.0], "SQL look-ups that found the cursor in memory. Low = shared pool too small."),
    ("soft_parse_pct",        "Soft Parse %",        "%", False, [99.0, 95.0], "SQL executions that reused a cached plan. <95% = hard parse storm."),
    ("execute_to_parse_pct",  "Execute to Parse %",  "%", False, [90.0, 70.0], "% executes reusing open cursor. Low = cursor caching not enabled."),
    ("latch_hit_pct",         "Latch Hit %",         "%", False, [99.9, 99.0], "Internal Oracle lock efficiency. <99% = contention in shared memory."),
]

_SIG_THRESHOLD = 15.0   # |delta_pct| >= this → is_significant


def _nm_direction(delta_pct: float, higher_is_bad: bool) -> str:
    if abs(delta_pct) < 2.0:
        return "stable"
    if higher_is_bad:
        return "regression" if delta_pct > 0 else "improvement"
    return "regression" if delta_pct < 0 else "improvement"


def _nm_severity(delta_pct: float, direction: str) -> str:
    a = abs(delta_pct)
    if direction == "improvement":
        return "good"
    if direction == "stable":
        return "info"
    if a >= 100:
        return "critical"
    if a >= 40:
        return "warning"
    return "info"


def _lp_val_from_raw(data: dict, keyword: str) -> float:
    """Extract per-second value from raw load_profile list by keyword."""
    for m in data.get("load_profile", []):
        if not isinstance(m, dict):
            continue
        sn = (m.get("stat_name", "") or "").lower()
        if keyword.lower() in sn:
            return _float(m.get("per_sec", m.get("per_second", 0)))
    return 0.0


_LP_KEYWORD_MAP = {
    "db_time":        "db time",
    "db_cpu":         "db cpu",
    "logical_reads":  "logical read",
    "physical_reads": "physical read",
    "physical_writes":"physical write",
    "redo_size":      "redo size",
    "hard_parses":    "hard parse",
    "parses":         "parse count",
    "executes":       "execut",
    "transactions":   "transaction",
    "logons":         "logon",
    "user_calls":     "user call",
    "sorts":          "sort",
    "block_changes":  "block change",
}


def _build_normalized_comparison(
    good_data: dict,
    bad_data: dict,
    good_summary: PeriodSummary,
    bad_summary: PeriodSummary,
    wait_comparisons: list,
) -> NormalizedComparison:
    """
    Build the canonical single source of truth for all comparison metrics.
    Called once from compare_periods(). Stored in ComparisonReport.normalized_comparison.
    """
    all_metrics: list[NormalizedMetric] = []

    # ── 1. Load Profile metrics ───────────────────────────────────────────────
    for key, label, unit, higher_is_bad, explanation in _LP_SPEC:
        kw = _LP_KEYWORD_MAP.get(key, key.replace("_", " "))
        if not (
            _lp_metric_available(good_data, kw)
            and _lp_metric_available(bad_data, kw)
        ):
            continue
        gv = _lp_val_from_raw(good_data, kw)
        bv = _lp_val_from_raw(bad_data, kw)
        delta = ((bv - gv) / abs(gv) * 100.0) if gv != 0 else (100.0 if bv > 0 else 0.0)
        direction = _nm_direction(delta, higher_is_bad)
        severity = _nm_severity(delta, direction)
        all_metrics.append(NormalizedMetric(
            key=key, label=label, group="load_profile",
            good_val=round(gv, 4), bad_val=round(bv, 4), unit=unit,
            delta_pct=round(delta, 2), direction=direction, severity=severity,
            is_significant=abs(delta) >= _SIG_THRESHOLD,
            higher_is_bad=higher_is_bad, explanation=explanation,
        ))

    # ── 2. Instance Efficiency metrics ───────────────────────────────────────
    good_eff = good_data.get("efficiency", {})
    bad_eff = bad_data.get("efficiency", {})
    for key, label, unit, higher_is_bad, thresholds, explanation in _EFF_SPEC:
        if not (
            _efficiency_metric_available(good_data, key)
            and _efficiency_metric_available(bad_data, key)
        ):
            continue
        gv = _float(good_eff.get(key, 0.0))
        bv = _float(bad_eff.get(key, 0.0))
        delta = ((bv - gv) / abs(gv) * 100.0) if gv != 0 else (100.0 if abs(bv) > 0 else 0.0)
        direction = _nm_direction(delta, higher_is_bad)
        severity = _nm_severity(delta, direction)
        # For efficiency ratios, degradation below threshold always significant
        below_thresh = (bv < thresholds[1]) and not higher_is_bad
        all_metrics.append(NormalizedMetric(
            key=key, label=label, group="efficiency",
            good_val=round(gv, 2), bad_val=round(bv, 2), unit=unit,
            delta_pct=round(delta, 2), direction=direction, severity=severity,
            is_significant=abs(delta) >= _SIG_THRESHOLD or below_thresh,
            higher_is_bad=higher_is_bad, explanation=explanation,
        ))

    # ── 3. Core workload metrics ──────────────────────────────────────────────
    db_time_delta = ((bad_summary.db_time_secs - good_summary.db_time_secs) / max(good_summary.db_time_secs, 0.01)) * 100
    aas_delta = ((bad_summary.aas - good_summary.aas) / max(good_summary.aas, 0.01)) * 100
    for key, gv, bv, label, unit, higher_is_bad, explanation, available in [
        ("db_time_total", good_summary.db_time_secs / 60, bad_summary.db_time_secs / 60,
         "DB Time (min)", "min", True, "Total database active time. Core load indicator.", True),
        ("aas", good_summary.aas, bad_summary.aas,
         "Avg Active Sessions", "", True, "Sessions actively working. >CPU count = possible saturation — cross-check DB CPU% share before concluding.", True),
        ("txn_per_sec", good_summary.txn_per_sec, bad_summary.txn_per_sec,
         "Transactions/sec", "/sec", False, "Business throughput KPI (commits+rollbacks per second).",
         good_summary.txn_per_sec_available and bad_summary.txn_per_sec_available),
        ("elapsed_min", good_summary.elapsed_min, bad_summary.elapsed_min,
         "Elapsed Window", "min", False, "Observation window length. Large difference = unequal comparison.", True),
    ]:
        if not available:
            continue
        delta = ((bv - gv) / max(abs(gv), 0.01)) * 100 if gv != 0 else (100.0 if abs(bv) > 0 else 0.0)
        direction = _nm_direction(delta, higher_is_bad)
        severity = _nm_severity(delta, direction)
        all_metrics.append(NormalizedMetric(
            key=key, label=label, group="workload",
            good_val=round(gv, 2), bad_val=round(bv, 2), unit=unit,
            delta_pct=round(delta, 2), direction=direction, severity=severity,
            is_significant=abs(delta) >= _SIG_THRESHOLD,
            higher_is_bad=higher_is_bad, explanation=explanation,
        ))

    # ── 4. Top wait events (new/worsening only) ────────────────────────────
    for wc in wait_comparisons[:10]:
        if wc.classification in ("new_bottleneck", "worsening"):
            delta = wc.delta_pct
            all_metrics.append(NormalizedMetric(
                key=f"wait_{wc.event_name.replace(' ', '_').lower()[:40]}",
                label=wc.event_name,
                group="wait",
                good_val=round(wc.good_pct_db_time, 2),
                bad_val=round(wc.bad_pct_db_time, 2),
                unit="% DB Time",
                delta_pct=round(delta, 2),
                direction="regression" if delta > 0 else ("improvement" if delta < 0 else "stable"),
                severity="critical" if wc.bad_pct_db_time > 20 else ("warning" if wc.bad_pct_db_time > 5 else "info"),
                is_significant=wc.classification in ("new_bottleneck", "worsening"),
                higher_is_bad=True,
                explanation=wc.root_cause_hint or f"Wait event contributing {wc.bad_pct_db_time:.1f}% of DB time.",
            ))

    # ── Build filtered views ──────────────────────────────────────────────────
    significant = [m for m in all_metrics if m.is_significant]
    lp_metrics = [m for m in all_metrics if m.group == "load_profile" and m.is_significant]
    eff_metrics = [m for m in all_metrics if m.group == "efficiency"]
    wait_metrics = [m for m in all_metrics if m.group == "wait"]

    regressions = [m for m in significant if m.direction == "regression"]
    top_reg = max(regressions, key=lambda m: abs(m.delta_pct), default=None)

    return NormalizedComparison(
        all_metrics=all_metrics,
        significant=significant,
        load_profile=lp_metrics,
        efficiency=eff_metrics,
        wait_events=wait_metrics,
        db_time_delta_pct=round(db_time_delta, 1),
        aas_good=good_summary.aas,
        aas_bad=bad_summary.aas,
        top_regression=top_reg.label if top_reg else "",
        top_regression_pct=abs(top_reg.delta_pct) if top_reg else 0.0,
        critical_count=sum(1 for m in significant if m.severity == "critical"),
        warning_count=sum(1 for m in significant if m.severity == "warning"),
    )


# ---------------------------------------------------------------------------
# Phase 6 — Z-Score Anomaly Detection for wait events
# ---------------------------------------------------------------------------

def _detect_zscore_anomalies(wait_comparisons: list[WaitEventComparison]) -> list[dict]:
    """
    Phase 6: Z-score pass over all wait event pct_db_time values.
    Any wait event whose bad_pct_db_time deviates > 2.5 std-devs from the
    distribution of good_pct_db_time values is flagged as a z-score anomaly.

    Uses the good run as the population baseline. Absence in good = treat as 0.
    Returns list of anomaly findings to be added to incident_indicators.
    """
    if not wait_comparisons:
        return []

    # Population = all good_pct_db_time values (including 0 for absent events)
    good_values = [wc.good_pct_db_time for wc in wait_comparisons]
    if len(good_values) < 3:
        return []

    try:
        mean_good = statistics.mean(good_values)
        stdev_good = statistics.stdev(good_values)
    except statistics.StatisticsError:
        return []

    if stdev_good < 0.01:
        return []

    anomalies = []
    for wc in wait_comparisons:
        zscore = (wc.bad_pct_db_time - mean_good) / stdev_good
        # Write back z-score to the comparison object (model field)
        wc.zscore = round(zscore, 2)

        if zscore > 2.5 and wc.bad_pct_db_time > 2.0:
            severity = "critical" if zscore > 4.0 else "warning"
            anomalies.append({
                "indicator": "zscore_wait_anomaly",
                "severity": severity,
                "event_name": wc.event_name,
                "zscore": round(zscore, 2),
                "description": (
                    f"'{wc.event_name}' is a {zscore:.1f}σ statistical outlier: "
                    f"{wc.bad_pct_db_time:.1f}% of DB time (baseline mean: {mean_good:.1f}%). "
                    f"This event is anomalously dominant in the bad period."
                ),
                "evidence": {
                    "good_pct": wc.good_pct_db_time,
                    "bad_pct": wc.bad_pct_db_time,
                    "zscore": round(zscore, 2),
                    "population_mean": round(mean_good, 2),
                    "population_stdev": round(stdev_good, 2),
                },
                "remediation": (
                    wc.pathology_meaning or wc.root_cause_hint
                    or f"Investigate '{wc.event_name}' — statistically anomalous in this period."
                ),
            })
    return anomalies


# ---------------------------------------------------------------------------
# Phase 3 — Causal Chain Builder (PATHOLOGY_MAP DAG traversal)
# ---------------------------------------------------------------------------

def _build_causal_chain_text(wait_comparisons: list[WaitEventComparison]) -> str:
    """
    Phase 3: Use PATHOLOGY_MAP causal_children edges to confirm causal hypotheses.

    For each anomalous wait event (new_bottleneck or worsening):
    - Look up its causal_children in PATHOLOGY_MAP
    - Check if those children are ALSO anomalous in this comparison
    - If yes: draw a confirmed causal edge → build chain text

    The root is the anomalous event with NO incoming edges from other anomalous events.
    This is deterministic and data-driven — the chain is discovered from data,
    not hardcoded per AWR pair.
    """
    # Anomalous events set (normalized keys)
    anomalous: dict[str, WaitEventComparison] = {}
    for wc in wait_comparisons:
        if wc.classification in ("new_bottleneck", "worsening") and wc.bad_pct_db_time > 1.0:
            anomalous[wc.event_name.lower()] = wc

    if not anomalous:
        return ""

    # Build confirmed causal edges
    edges: list[tuple[str, str]] = []  # (parent, child) both normalized
    for parent_key, parent_wc in anomalous.items():
        pathology = _get_pathology(parent_wc.event_name)
        for child in pathology.get("causal_children", []):
            child_key = child.lower()
            # Check if child is also anomalous (confirmed by data)
            for anomalous_key in anomalous:
                if child_key in anomalous_key or anomalous_key.startswith(child_key[:12]):
                    edges.append((parent_key, anomalous_key))
                    break

    if not edges:
        # No confirmed edges — just list anomalous events by severity
        top = sorted(anomalous.values(), key=lambda w: -w.bad_pct_db_time)
        events_text = " | ".join(f"'{w.event_name}' ({w.bad_pct_db_time:.1f}% DB time)" for w in top[:3])
        return f"Isolated anomalous events (no confirmed causal chain): {events_text}"

    # Find roots: anomalous events with no incoming edges from other anomalous events
    has_incoming: set[str] = {child for _, child in edges}
    roots = [k for k in anomalous if k not in has_incoming]

    def _chain_from(node: str, depth: int = 0) -> str:
        if depth > 5:
            return ""
        wc = anomalous.get(node)
        if not wc:
            return node
        children_edges = [child for parent, child in edges if parent == node]
        label = f"'{wc.event_name}' ({wc.bad_pct_db_time:.1f}% DB time)"
        if not children_edges:
            return label
        child_chains = " → ".join(_chain_from(c, depth + 1) for c in children_edges[:2])
        return f"{label} → {child_chains}"

    chains = [_chain_from(root) for root in roots[:2]]
    return " | ".join(chains)


# ---------------------------------------------------------------------------
# Phase 6 — Ratio Inversion Detection (scored finding)
# ---------------------------------------------------------------------------

def _detect_ratio_inversion(good_summary: "PeriodSummary", bad_summary: "PeriodSummary") -> tuple[bool, float, str]:
    """
    Phase 6: Ratio inversion = transactions/sec DOWN + DB time/sec UP.
    This means sessions are spinning in wait loops rather than completing work.
    Returns (is_inverted, severity_score 0.0-1.0, description).

    Different from congestion_signal (which just checks AAS vs TXN):
    this uses the actual per-second DB time rate as the metric.
    """
    if not (
        good_summary.txn_per_sec_available
        and bad_summary.txn_per_sec_available
    ):
        return False, 0.0, ""

    good_txn = good_summary.txn_per_sec
    bad_txn = bad_summary.txn_per_sec
    good_db_per_sec = good_summary.db_time_secs / max(good_summary.elapsed_secs, 1.0)
    bad_db_per_sec = bad_summary.db_time_secs / max(bad_summary.elapsed_secs, 1.0)

    if good_txn <= 0 or good_db_per_sec <= 0:
        return False, 0.0, ""

    txn_delta_pct = ((bad_txn - good_txn) / good_txn) * 100.0
    db_time_delta_pct = ((bad_db_per_sec - good_db_per_sec) / good_db_per_sec) * 100.0

    # Inversion: throughput dropped AND DB time per sec rose
    if txn_delta_pct < -10.0 and db_time_delta_pct > 20.0:
        # Score: the more severe the divergence, the higher the score
        score = min(abs(txn_delta_pct) / 100.0 + db_time_delta_pct / 200.0, 1.0)
        desc = (
            f"Ratio inversion: transactions/sec changed {txn_delta_pct:+.0f}% "
            f"({good_txn:.2f}→{bad_txn:.2f}/s) while DB time/sec rose {db_time_delta_pct:+.0f}% "
            f"({good_db_per_sec:.1f}→{bad_db_per_sec:.1f}s/s). "
            f"Sessions are consuming more DB time but completing less work — classic wait-loop congestion."
        )
        return True, round(score, 3), desc

    # Reverse paradox: BOTH throughput AND DB time fell, but throughput fell MORE.
    # Lower DB Time is NOT an improvement — the database did less productive work.
    # The ratio of DB time per transaction ROSE, meaning each completed transaction
    # cost more resources. This is the signature of a stalled/failed batch job.
    if txn_delta_pct < -10.0 and db_time_delta_pct < -5.0:
        # DB time per transaction in each period
        good_db_per_txn = good_db_per_sec / max(good_txn, 0.0001)
        bad_db_per_txn  = bad_db_per_sec  / max(bad_txn,  0.0001)
        db_per_txn_delta_pct = ((bad_db_per_txn - good_db_per_txn) / max(good_db_per_txn, 0.0001)) * 100.0
        # If throughput fell proportionally MORE than DB time, efficiency degraded
        if txn_delta_pct < db_time_delta_pct - 5.0:
            score = min(abs(txn_delta_pct - db_time_delta_pct) / 100.0, 1.0)
            desc = (
                f"Throughput collapse paradox: DB time/sec fell {abs(db_time_delta_pct):.0f}% "
                f"({good_db_per_sec:.1f}→{bad_db_per_sec:.1f}s/s) but transactions/sec fell even more "
                f"({txn_delta_pct:+.0f}%, {good_txn:.2f}→{bad_txn:.2f}/s). "
                f"DB Time per transaction rose {db_per_txn_delta_pct:+.0f}% — the remaining work was less efficient. "
                f"Lower total DB Time reflects less productive work done, NOT a performance improvement. "
                f"Consistent with batch job starvation, early termination, or blocked processing stages."
            )
            return True, round(score, 3), desc

    return False, 0.0, ""


# Main entry point
# ---------------------------------------------------------------------------

def compare_periods(good_data: dict, bad_data: dict) -> ComparisonReport:
    """Compare a 'good' AWR period against a 'bad' AWR period."""
    health_good = calculate_health_score(good_data)
    health_bad = calculate_health_score(bad_data)

    good_summary = _compute_period_summary(good_data, "Good Period (Baseline)")
    bad_summary = _compute_period_summary(bad_data, "Bad Period (Problem)")

    # Phase 1 — Zero-elapsed abort: if either period has invalid snapshot, signal clearly
    good_is_invalid = "INVALID_SNAPSHOT" in good_summary.label
    bad_is_invalid = "INVALID_SNAPSHOT" in bad_summary.label

    load_deltas = _compare_load_profile(good_data, bad_data)
    wait_comparisons = _compare_wait_events(
        good_data, bad_data,
        good_summary.elapsed_secs, bad_summary.elapsed_secs,
    )
    sql_regressions = _compare_sql_stats(
        good_data, bad_data,
        good_summary.elapsed_min, bad_summary.elapsed_min,
    )
    efficiency_comparisons = _compare_efficiency(good_data, bad_data)
    logon_storm_explanation = _detect_logon_storm(good_data, bad_data)
    batch_groups = _detect_batch_groups(sql_regressions)
    incidents = _detect_incidents(good_data, bad_data, wait_comparisons, sql_regressions, load_deltas)

    # Phase 6 — Z-score anomaly detection pass (mutates wc.zscore in place)
    zscore_anomalies = _detect_zscore_anomalies(wait_comparisons)
    incidents.extend(zscore_anomalies)

    # Phase 6 — Ratio inversion (scored finding)
    ratio_inv, ratio_inv_score, ratio_inv_desc = _detect_ratio_inversion(good_summary, bad_summary)
    if ratio_inv:
        incidents.insert(0, {
            "indicator": "ratio_inversion",
            "severity": "critical" if ratio_inv_score > 0.5 else "warning",
            "description": ratio_inv_desc,
            "evidence": {"ratio_inversion_score": ratio_inv_score},
            "remediation": (
                "Sessions consuming more DB time but completing fewer transactions — "
                "wait-loop congestion. Identify dominant wait event and trace to root cause."
            ),
        })

    # Phase 3 — Causal chain text from PATHOLOGY_MAP DAG traversal
    causal_chain_text = _build_causal_chain_text(wait_comparisons)

    # Add invalid snapshot incidents
    if good_is_invalid:
        incidents.insert(0, {
            "indicator": "invalid_snapshot",
            "severity": "critical",
            "description": "Good period snapshot has elapsed_min=0 — comparison metrics may be unreliable.",
            "evidence": {"period": "good"},
            "remediation": "Re-upload good period AWR with valid snapshot boundaries.",
        })
    if bad_is_invalid:
        incidents.insert(0, {
            "indicator": "invalid_snapshot",
            "severity": "critical",
            "description": "Bad period snapshot has elapsed_min=0 — comparison metrics may be unreliable.",
            "evidence": {"period": "bad"},
            "remediation": "Re-upload bad period AWR with valid snapshot boundaries.",
        })

    overall_desc, overall_severity = _classify_overall_severity(health_good["score"], health_bad["score"], incidents)

    # Bottleneck classification
    good_bottleneck = _classify_bottleneck(good_data)
    bad_bottleneck = _classify_bottleneck(bad_data)
    bottleneck_shift = ""
    if good_bottleneck != bad_bottleneck:
        bottleneck_shift = f"{good_bottleneck}→{bad_bottleneck}"

    # Evidence-based headline
    headline, headline_evidence = _generate_evidence_headline(
        good_data, bad_data, good_summary, bad_summary,
        sql_regressions, wait_comparisons, logon_storm_explanation,
        good_bottleneck, bad_bottleneck,
    )

    # IMP7 — Congestion signal
    congestion_signal = False
    congestion_message = ""
    if (
        good_summary.txn_per_sec_available
        and bad_summary.txn_per_sec_available
        and good_summary.txn_per_sec > 0
        and bad_summary.txn_per_sec > 0
    ):
        txn_delta = ((bad_summary.txn_per_sec - good_summary.txn_per_sec) / good_summary.txn_per_sec) * 100.0
        aas_delta = ((bad_summary.aas - good_summary.aas) / max(good_summary.aas, 0.01)) * 100.0
        if aas_delta > 10 and txn_delta < -10:
            congestion_signal = True
            congestion_message = (
                f"Congestion indicator — DB time/AAS increased +{aas_delta:.0f}% "
                f"but transactions/sec decreased {txn_delta:.0f}%. More resources consumed "
                "but fewer business transactions completed."
            )

    # Key deltas for summary
    db_time_delta_pct = 0.0
    if good_summary.db_time_secs > 0:
        db_time_delta_pct = ((bad_summary.db_time_secs - good_summary.db_time_secs) / good_summary.db_time_secs) * 100.0
    
    exec_rate_delta_pct = 0.0
    good_exec_rate = _lp_value(good_data, "execute", "user call")
    bad_exec_rate = _lp_value(bad_data, "execute", "user call")
    if (
        _lp_any_metric_available(good_data, "execute", "user call")
        and _lp_any_metric_available(bad_data, "execute", "user call")
        and good_exec_rate > 0
    ):
        exec_rate_delta_pct = ((bad_exec_rate - good_exec_rate) / good_exec_rate) * 100.0

    cpus = _cpu_count(bad_data) or _cpu_count(good_data) or 1
    cpu_capacity = (bad_summary.aas / max(cpus, 1)) * 100.0

    recommendations = _generate_recommendations(
        load_deltas, wait_comparisons, efficiency_comparisons,
        sql_regressions, incidents, logon_storm_explanation,
    )

    summary = ComparisonSummary(
        good_period=good_summary,
        bad_period=bad_summary,
        health_score_good=health_good["score"],
        health_score_bad=health_bad["score"],
        overall_regression=overall_desc,
        severity=overall_severity,
        congestion_signal=congestion_signal,
        congestion_message=congestion_message,
        ratio_inversion=ratio_inv,
        ratio_inversion_score=ratio_inv_score,
        causal_chain_text=causal_chain_text,
        headline=headline,
        headline_evidence=headline_evidence,
        good_bottleneck=good_bottleneck,
        bad_bottleneck=bad_bottleneck,
        bottleneck_shift=bottleneck_shift,
        db_time_delta_pct=round(db_time_delta_pct, 1),
        exec_rate_delta_pct=round(exec_rate_delta_pct, 1),
        aas_good=good_summary.aas,
        aas_bad=bad_summary.aas,
        cpu_capacity_used_pct=round(cpu_capacity, 1),
    )

    top_wait_dict = {
        "comparisons": [wc.model_dump() for wc in wait_comparisons],
        "new_bottlenecks": [wc.model_dump() for wc in wait_comparisons if wc.classification == "new_bottleneck"],
        "worsening": [wc.model_dump() for wc in wait_comparisons if wc.classification == "worsening"],
        "improving": [wc.model_dump() for wc in wait_comparisons if wc.classification == "improving"],
        "extreme_waits": [wc.model_dump() for wc in wait_comparisons if wc.extreme_wait_flag],
        # Phase 7 — top findings by confidence × severity (priority heap)
        "top_priority": [
            wc.model_dump() for wc in wait_comparisons
            if wc.classification in ("new_bottleneck", "worsening") and wc.confidence > 0.3
        ][:5],
    }

    efficiency_dict = {
        "comparisons": [ec.model_dump() for ec in efficiency_comparisons],
        "alerts": [ec.model_dump() for ec in efficiency_comparisons if ec.severity in ("critical", "warning")],
    }

    workload_good = _workload_composition(sql_regressions, "good")
    workload_bad = _workload_composition(sql_regressions, "bad")

    # SQL Zones: classify into structured groups
    sql_high_frequency = sorted(
        [s for s in sql_regressions if s.bad_execs_per_min > 50 or s.good_execs_per_min > 50],
        key=lambda s: s.bad_execs_per_min, reverse=True,
    )
    sql_plan_changes = [s for s in sql_regressions if s.plan_changed]
    sql_new_in_bad = sorted(
        [s for s in sql_regressions if s.tag == "new_offender" and not s.is_oracle_maintenance],
        key=lambda s: s.bad_elapsed_secs, reverse=True,
    )
    sql_maintenance = [s for s in sql_regressions if s.is_oracle_maintenance]

    # ADDM findings passthrough
    addm_findings = []
    for src in [bad_data, good_data]:
        for f in src.get("addm_findings", []):
            if isinstance(f, dict):
                addm_findings.append(f)

    # Build canonical normalized comparison (single source of truth)
    norm = _build_normalized_comparison(
        good_data, bad_data, good_summary, bad_summary, wait_comparisons
    )

    # Trigger 3 — DBWR Instance Activity Stats comparison
    dbwr_activity = _compare_dbwr_activity_stats(
        good_data, bad_data,
        good_summary.elapsed_secs, bad_summary.elapsed_secs,
    )

    return ComparisonReport(
        summary=summary,
        load_profile_delta=load_deltas,
        top_wait_events=top_wait_dict,
        instance_efficiency=efficiency_dict,
        sql_regressions=sql_regressions,
        recommendations=recommendations,
        incident_indicators=incidents,
        rca_chains=[],
        logon_storm_explanation=logon_storm_explanation,
        batch_groups=batch_groups,
        addm_findings=addm_findings,
        sql_high_frequency=sql_high_frequency,
        sql_plan_changes=sql_plan_changes,
        sql_new_in_bad=sql_new_in_bad,
        sql_maintenance=sql_maintenance,
        normalized_comparison=norm,
        dbwr_activity=dbwr_activity,
    )
