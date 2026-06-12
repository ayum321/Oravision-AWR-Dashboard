"""Advanced comparison analytics — produces data for the 9 new dashboard panels.

Each public function takes good_data / bad_data dicts (AWRData structure)
and returns plain dicts ready for JSON serialization.
"""
from __future__ import annotations

import re
from typing import Any


def _float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# DESIGN 1 — Workload Composition Pie
# ---------------------------------------------------------------------------

_MODULE_CATEGORIES = {
    "jdbc thin client": "Application (JDBC)",
    "jdbc oci": "Application (JDBC)",
    "sqlplus": "Ad-hoc (SQL*Plus)",
    "plsqldev": "Ad-hoc (PL/SQL Dev)",
    "toad": "Ad-hoc (Toad)",
    "sql developer": "Ad-hoc (SQL Developer)",
    "dbms_scheduler": "Oracle Maintenance",
    "mmon_slave": "Oracle Maintenance",
    "dbms_stats": "Oracle Maintenance",
    "auto optimizer stats": "Oracle Maintenance",
    "oem": "Monitoring (OEM)",
    "datapump": "DataPump",
    "rman": "RMAN Backup",
}

_MAINTENANCE_SQL_PATTERNS = [
    re.compile(r"dbms_stats", re.IGNORECASE),
    re.compile(r"gather.*stat", re.IGNORECASE),
    re.compile(r"sys\.dbms_", re.IGNORECASE),
    re.compile(r"purge", re.IGNORECASE),
    re.compile(r"dbms_scheduler", re.IGNORECASE),
    re.compile(r"mmon", re.IGNORECASE),
]


def _classify_module(module: str, sql_text: str) -> str:
    """Classify a SQL statement into a workload category."""
    mod = (module or "").strip().lower()

    # Check module name against known categories
    for pattern, category in _MODULE_CATEGORIES.items():
        if pattern in mod:
            return category

    # Check SQL text for Oracle maintenance patterns
    for regex in _MAINTENANCE_SQL_PATTERNS:
        if regex.search(sql_text or ""):
            return "Oracle Maintenance"

    if not mod or mod in ("", "unknown"):
        return "Ad-hoc (No Module)"

    return "Application"


def workload_composition(data: dict) -> list[dict]:
    """Build workload composition breakdown by module/category.

    Returns list of {category, elapsed_secs, pct_db_time, sql_count}.
    """
    sql_stats = data.get("sql_stats", [])
    db_time_secs = _float(data.get("db_time_min", 0)) * 60.0

    buckets: dict[str, dict] = {}
    for sql in sql_stats:
        cat = _classify_module(
            sql.get("module", ""),
            sql.get("sql_text", ""),
        )
        if cat not in buckets:
            buckets[cat] = {"elapsed_secs": 0.0, "sql_count": 0}
        buckets[cat]["elapsed_secs"] += _float(sql.get("elapsed_time_secs", 0))
        buckets[cat]["sql_count"] += 1

    result = []
    for cat, vals in sorted(buckets.items(), key=lambda x: -x[1]["elapsed_secs"]):
        pct = (vals["elapsed_secs"] / db_time_secs * 100.0) if db_time_secs > 0 else 0.0
        result.append({
            "category": cat,
            "elapsed_secs": round(vals["elapsed_secs"], 2),
            "pct_db_time": round(pct, 2),
            "sql_count": vals["sql_count"],
        })
    return result


# ---------------------------------------------------------------------------
# DESIGN 2 — Cursor Health Composite Score
# ---------------------------------------------------------------------------

def cursor_health_score(data: dict) -> dict:
    """Compute a composite cursor health score (0–100).

    Combines Execute-to-Parse%, Soft Parse%, logon rate, hard parse rate.
    Returns {score, grade, color, components: [{name, value, weight, status}]}.
    """
    eff = data.get("efficiency", {})
    if not isinstance(eff, dict):
        eff = {}

    load_profile = data.get("load_profile", [])
    lp_map = {m.get("stat_name", "").lower(): m for m in load_profile if isinstance(m, dict)}

    # Component values
    exec_to_parse = _float(eff.get("execute_to_parse_pct", 0))
    soft_parse = _float(eff.get("soft_parse_pct", 0))

    # Hard parses/sec from load profile
    hard_parses_sec = 0.0
    for key in lp_map:
        if "hard parse" in key:
            hard_parses_sec = _float(lp_map[key].get("per_sec", 0))
            break

    # Logons/sec from load profile
    logons_sec = 0.0
    for key in lp_map:
        if "logon" in key:
            logons_sec = _float(lp_map[key].get("per_sec", 0))
            break

    # Scoring weights (total = 100)
    # E2P: 30pts, Soft Parse: 30pts, Hard Parse Rate: 25pts, Logon Rate: 15pts
    components = []

    # E2P score: 100% → 30pts, <30% → 0pts
    e2p_score = min(30.0, max(0.0, exec_to_parse / 100.0 * 30.0))
    e2p_status = "good" if exec_to_parse >= 80 else ("warning" if exec_to_parse >= 50 else "critical")
    components.append({
        "name": "Execute-to-Parse %",
        "value": round(exec_to_parse, 2),
        "unit": "%",
        "weight": 30,
        "score": round(e2p_score, 1),
        "status": e2p_status,
    })

    # Soft parse score: 100% → 30pts, <70% → 0pts
    sp_score = min(30.0, max(0.0, (soft_parse - 70.0) / 30.0 * 30.0))
    sp_status = "good" if soft_parse >= 95 else ("warning" if soft_parse >= 85 else "critical")
    components.append({
        "name": "Soft Parse %",
        "value": round(soft_parse, 2),
        "unit": "%",
        "weight": 30,
        "score": round(sp_score, 1),
        "status": sp_status,
    })

    # Hard parse rate score: 0/s → 25pts, >200/s → 0pts
    hp_score = min(25.0, max(0.0, (200.0 - hard_parses_sec) / 200.0 * 25.0))
    hp_status = "good" if hard_parses_sec < 50 else ("warning" if hard_parses_sec < 200 else "critical")
    components.append({
        "name": "Hard Parses/sec",
        "value": round(hard_parses_sec, 2),
        "unit": "/s",
        "weight": 25,
        "score": round(hp_score, 1),
        "status": hp_status,
    })

    # Logon rate score: <5/s → 15pts, >50/s → 0pts
    lr_score = min(15.0, max(0.0, (50.0 - logons_sec) / 50.0 * 15.0))
    lr_status = "good" if logons_sec < 10 else ("warning" if logons_sec < 50 else "critical")
    components.append({
        "name": "Logons/sec",
        "value": round(logons_sec, 2),
        "unit": "/s",
        "weight": 15,
        "score": round(lr_score, 1),
        "status": lr_status,
    })

    total = round(e2p_score + sp_score + hp_score + lr_score)
    total = max(0, min(100, total))

    if total >= 80:
        grade, color = "A", "green"
    elif total >= 60:
        grade, color = "B", "amber"
    elif total >= 40:
        grade, color = "C", "orange"
    else:
        grade, color = "D", "red"

    return {
        "score": total,
        "grade": grade,
        "color": color,
        "components": components,
    }


# ---------------------------------------------------------------------------
# DESIGN 3 — Causal Chain Auto-Narrative
# ---------------------------------------------------------------------------

def build_causal_chains(
    good_data: dict,
    bad_data: dict,
    sql_regressions: list[dict],
    wait_comparisons: list[dict],
    efficiency_comparisons: list[dict],
) -> list[dict]:
    """Build structured TRIGGER → MECHANISM → SYMPTOMS chains.

    Returns list of {trigger, mechanism, symptoms: [], evidence: [], severity}.
    """
    chains: list[dict] = []
    good_eff = good_data.get("efficiency", {})
    bad_eff = bad_data.get("efficiency", {})
    if not isinstance(good_eff, dict):
        good_eff = {}
    if not isinstance(bad_eff, dict):
        bad_eff = {}

    # Detect auto-stats / maintenance trigger
    bad_sql = bad_data.get("sql_stats", [])
    maintenance_sqls = []
    maintenance_elapsed = 0.0
    for sql in bad_sql:
        cat = _classify_module(sql.get("module", ""), sql.get("sql_text", ""))
        if cat == "Oracle Maintenance":
            maintenance_sqls.append(sql)
            maintenance_elapsed += _float(sql.get("elapsed_time_secs", 0))

    if maintenance_sqls and maintenance_elapsed > 60.0:
        # Check for corresponding efficiency degradation
        e2p_good = _float(good_eff.get("execute_to_parse_pct", 0))
        e2p_bad = _float(bad_eff.get("execute_to_parse_pct", 0))
        symptoms = []
        if e2p_good > 0 and e2p_bad < e2p_good * 0.7:
            symptoms.append(f"E2P {e2p_good:.0f}%→{e2p_bad:.0f}%")

        # Check wait event symptoms
        for wc in wait_comparisons:
            if wc.get("classification") in ("new_bottleneck", "worsening"):
                g_pct = wc.get("good_pct_db_time", 0)
                b_pct = wc.get("bad_pct_db_time", 0)
                symptoms.append(f"{wc['event_name']} {g_pct:.1f}%→{b_pct:.1f}%")

        chains.append({
            "trigger": "Oracle auto-maintenance / statistics gathering",
            "mechanism": ", ".join([
                sql.get("sql_text", "")[:80] for sql in maintenance_sqls[:3]
            ]) + (f" + {len(maintenance_sqls)-3} more" if len(maintenance_sqls) > 3 else ""),
            "symptoms": symptoms[:5],
            "evidence": [
                f"{len(maintenance_sqls)} maintenance SQLs totaling {maintenance_elapsed:.0f}s",
            ],
            "severity": "critical" if maintenance_elapsed > 300 else "warning",
        })

    # Detect DELETE/purge batch trigger
    delete_sqls = [
        s for s in bad_sql
        if "delete" in (s.get("sql_text", "") or "").lower()[:20]
    ]
    delete_elapsed = sum(_float(s.get("elapsed_time_secs", 0)) for s in delete_sqls)
    if delete_sqls and delete_elapsed > 60.0:
        delete_io_pct = sum(_float(s.get("disk_reads", 0)) for s in delete_sqls)
        symptoms = []
        for wc in wait_comparisons:
            if wc.get("classification") in ("new_bottleneck", "worsening"):
                symptoms.append(f"{wc['event_name']} worsened")
        chains.append({
            "trigger": "Batch purge/DELETE activity",
            "mechanism": ", ".join([
                s.get("sql_text", "")[:80] for s in delete_sqls[:2]
            ]),
            "symptoms": symptoms[:5],
            "evidence": [
                f"{len(delete_sqls)} DELETE statements totaling {delete_elapsed:.0f}s",
                f"Physical reads from DELETEs: {delete_io_pct:.0f}",
            ],
            "severity": "critical" if delete_elapsed > 300 else "warning",
        })

    # Detect connection pool drain / session spike
    good_lp = {m.get("stat_name", "").lower(): m for m in good_data.get("load_profile", []) if isinstance(m, dict)}
    bad_lp = {m.get("stat_name", "").lower(): m for m in bad_data.get("load_profile", []) if isinstance(m, dict)}

    good_logons = 0.0
    bad_logons = 0.0
    for key in good_lp:
        if "logon" in key:
            good_logons = _float(good_lp[key].get("per_sec", 0))
    for key in bad_lp:
        if "logon" in key:
            bad_logons = _float(bad_lp[key].get("per_sec", 0))

    if bad_logons > good_logons * 2 and bad_logons > 5:
        chains.append({
            "trigger": "Connection pool drain / session storm",
            "mechanism": f"Logon rate surged {good_logons:.1f}/s → {bad_logons:.1f}/s, likely connection pool exhaustion",
            "symptoms": [f"Logons/sec {good_logons:.1f}→{bad_logons:.1f}"],
            "evidence": [f"Logon rate increased {((bad_logons-good_logons)/max(good_logons,0.1))*100:.0f}%"],
            "severity": "warning",
        })

    # Detect plan regression chain
    plan_changes = [r for r in sql_regressions if r.get("plan_changed")]
    if len(plan_changes) >= 2:
        total_impact = sum(_float(r.get("bad_elapsed_secs", 0)) - _float(r.get("good_elapsed_secs", 0))
                          for r in plan_changes)
        chains.append({
            "trigger": "Execution plan changes",
            "mechanism": f"{len(plan_changes)} SQL statements changed plans",
            "symptoms": [
                f"{r.get('sql_id','?')}: avg elapsed {_float(r.get('good_avg_elapsed',0)):.2f}s→{_float(r.get('bad_avg_elapsed',0)):.2f}s"
                for r in plan_changes[:4]
            ],
            "evidence": [
                f"Total elapsed impact: {total_impact:+.0f}s across {len(plan_changes)} SQLs",
            ],
            "severity": "critical" if total_impact > 300 else "warning",
        })

    # Detect I/O saturation chain
    io_waits = [
        wc for wc in wait_comparisons
        if wc.get("wait_class", "").lower() in ("user i/o", "system i/o")
        and wc.get("classification") in ("new_bottleneck", "worsening")
    ]
    if io_waits:
        chains.append({
            "trigger": "I/O subsystem saturation",
            "mechanism": "Multiple I/O wait events worsened simultaneously",
            "symptoms": [
                f"{w['event_name']}: {w.get('good_pct_db_time',0):.1f}%→{w.get('bad_pct_db_time',0):.1f}% DB Time"
                for w in io_waits[:4]
            ],
            "evidence": [f"{len(io_waits)} I/O wait events degraded"],
            "severity": "critical",
        })

    # Sort by severity
    sev_order = {"critical": 0, "warning": 1, "info": 2}
    chains.sort(key=lambda c: sev_order.get(c["severity"], 9))
    return chains


# ---------------------------------------------------------------------------
# DESIGN 4 — Batch Purge Job Detector
# ---------------------------------------------------------------------------

_TABLE_FROM_SQL = re.compile(
    r"(?:delete\s+from|delete\s+)\s+(?:\w+\.)?(\w+)",
    re.IGNORECASE,
)


def detect_batch_purges(data: dict) -> list[dict]:
    """Detect DELETE statements with high I/O impact.

    Returns list of {sql_id, table_name, executions, elapsed_secs,
    disk_reads, io_pct, purge_volume_estimate, severity, remediation}.
    """
    sql_stats = data.get("sql_stats", [])
    results = []

    total_disk_reads = sum(_float(s.get("disk_reads", 0)) for s in sql_stats)

    for sql in sql_stats:
        text = (sql.get("sql_text", "") or "").strip()
        if not text.lower().startswith("delete"):
            continue

        elapsed = _float(sql.get("elapsed_time_secs", 0))
        disk_reads = _float(sql.get("disk_reads", 0))
        execs = int(_float(sql.get("executions", 0)))
        buffer_gets = _float(sql.get("buffer_gets", 0))

        io_pct = (disk_reads / total_disk_reads * 100.0) if total_disk_reads > 0 else 0.0

        # Extract table name
        match = _TABLE_FROM_SQL.search(text)
        table_name = match.group(1) if match else "UNKNOWN"

        # Purge volume estimate (execs × avg blocks per exec)
        avg_blocks = (buffer_gets / max(execs, 1))
        purge_volume = execs * avg_blocks  # in Oracle blocks

        severity = "critical" if io_pct > 40 else ("warning" if io_pct > 20 else "info")

        remediation = []
        if io_pct > 20:
            remediation.append("Use chunked deletes (ROWNUM batches of 10K-50K) with commits between")
        if execs > 1000:
            remediation.append("Consider partition-level TRUNCATE/DROP if data is time-partitioned")
        if elapsed > 300:
            remediation.append("Schedule purge during low-activity window or stagger across hours")

        results.append({
            "sql_id": sql.get("sql_id", ""),
            "table_name": table_name,
            "executions": execs,
            "elapsed_secs": round(elapsed, 2),
            "disk_reads": int(disk_reads),
            "buffer_gets": int(buffer_gets),
            "io_pct": round(io_pct, 2),
            "purge_volume_estimate": int(purge_volume),
            "severity": severity,
            "remediation": remediation,
            "sql_text_short": text[:200],
        })

    results.sort(key=lambda x: -x["io_pct"])
    return results


# ---------------------------------------------------------------------------
# DESIGN 6 — Business Throughput Panel
# ---------------------------------------------------------------------------

def business_throughput(good_data: dict, bad_data: dict) -> dict:
    """Compute TXN/sec and AAS as primary business metrics.

    Returns {good: {txn_per_sec, aas, db_time_secs, elapsed_secs},
             bad: {txn_per_sec, aas, db_time_secs, elapsed_secs},
             delta: {txn_per_sec_pct, aas_pct, congestion_signal}}.
    """
    def _extract(data: dict) -> dict:
        elapsed_min = _float(data.get("elapsed_min", 0))
        db_time_min = _float(data.get("db_time_min", 0))
        elapsed_secs = elapsed_min * 60.0
        db_time_secs = db_time_min * 60.0
        aas = db_time_secs / elapsed_secs if elapsed_secs > 0 else 0.0

        lp = {m.get("stat_name", "").lower(): m
              for m in data.get("load_profile", []) if isinstance(m, dict)}

        txn_per_sec = 0.0
        for key in lp:
            if "transaction" in key or "user commit" in key:
                txn_per_sec = _float(lp[key].get("per_sec", 0))
                break

        # Fallback: sum user commits + user rollbacks
        if txn_per_sec == 0:
            for key in lp:
                if "commit" in key or "rollback" in key:
                    txn_per_sec += _float(lp[key].get("per_sec", 0))

        return {
            "txn_per_sec": round(txn_per_sec, 2),
            "aas": round(aas, 2),
            "db_time_secs": round(db_time_secs, 2),
            "elapsed_secs": round(elapsed_secs, 2),
        }

    good = _extract(good_data)
    bad = _extract(bad_data)

    txn_delta = 0.0
    if good["txn_per_sec"] > 0:
        txn_delta = ((bad["txn_per_sec"] - good["txn_per_sec"]) / good["txn_per_sec"]) * 100.0

    aas_delta = 0.0
    if good["aas"] > 0:
        aas_delta = ((bad["aas"] - good["aas"]) / good["aas"]) * 100.0

    # Congestion signal: DB Time rises but TXN/sec falls
    congestion = False
    if aas_delta > 10 and txn_delta < -10:
        congestion = True

    return {
        "good": good,
        "bad": bad,
        "delta": {
            "txn_per_sec_pct": round(txn_delta, 2),
            "aas_pct": round(aas_delta, 2),
            "congestion_signal": congestion,
        },
    }


# ---------------------------------------------------------------------------
# DESIGN 7 — SQL Net Performance Assessment
# ---------------------------------------------------------------------------

def sql_net_assessment(
    sql_regressions: list[dict],
    threshold_pct: float = 10.0,
) -> list[dict]:
    """Add 'net_assessment' to each SQL regression entry.

    Assessment: Improved / Stable / Regressed / Cannot Determine.
    Based on per-exec elapsed time delta with configurable threshold.
    """
    results = []
    for sql in sql_regressions:
        good_avg = _float(sql.get("good_avg_elapsed", 0))
        bad_avg = _float(sql.get("bad_avg_elapsed", 0))
        good_execs = int(_float(sql.get("good_executions", 0)))
        bad_execs = int(_float(sql.get("bad_executions", 0)))

        if good_avg == 0 and bad_avg == 0:
            assessment = "Cannot Determine"
            assessment_detail = "No elapsed data available"
        elif good_execs == 0 and bad_execs == 0:
            assessment = "Cannot Determine"
            assessment_detail = "Zero executions in both periods"
        elif good_avg == 0:
            # New in bad period
            assessment = "Cannot Determine"
            assessment_detail = "New SQL — no baseline for comparison"
        else:
            pct_change = ((bad_avg - good_avg) / good_avg) * 100.0
            if pct_change > threshold_pct:
                assessment = "Regressed"
                assessment_detail = f"Per-exec elapsed +{pct_change:.1f}% (>{threshold_pct}% threshold)"
            elif pct_change < -threshold_pct:
                assessment = "Improved"
                assessment_detail = f"Per-exec elapsed {pct_change:.1f}% (>{threshold_pct}% improvement)"
            else:
                assessment = "Stable"
                assessment_detail = f"Per-exec elapsed {pct_change:+.1f}% (within ±{threshold_pct}% tolerance)"

        results.append({
            **sql,
            "net_assessment": assessment,
            "net_assessment_detail": assessment_detail,
        })

    return results


# ---------------------------------------------------------------------------
# DESIGN 8 — Correlated Batch Group Detection
# ---------------------------------------------------------------------------

def detect_batch_groups(
    sql_regressions: list[dict],
    tolerance_pct: float = 5.0,
) -> list[dict]:
    """Detect SQL groups with near-identical execution counts.

    Returns list of {group_id, label, sql_ids: [], exec_count, combined_elapsed,
    combined_pct, sql_count}.
    """
    # Only look at new offenders and regressions in bad period
    candidates = [
        s for s in sql_regressions
        if s.get("tag") in ("new_offender", "regression", "load_increase")
        and int(_float(s.get("bad_executions", 0))) > 0
    ]

    if len(candidates) < 2:
        return []

    # Sort by execution count
    candidates.sort(key=lambda s: int(_float(s.get("bad_executions", 0))))

    groups: list[list[dict]] = []
    used: set[str] = set()

    for i, sql_a in enumerate(candidates):
        if sql_a.get("sql_id", "") in used:
            continue
        execs_a = int(_float(sql_a.get("bad_executions", 0)))
        if execs_a == 0:
            continue

        group = [sql_a]
        used.add(sql_a.get("sql_id", ""))

        for j, sql_b in enumerate(candidates):
            if i == j or sql_b.get("sql_id", "") in used:
                continue
            execs_b = int(_float(sql_b.get("bad_executions", 0)))
            if execs_b == 0:
                continue

            pct_diff = abs(execs_a - execs_b) / max(execs_a, 1) * 100.0
            if pct_diff <= tolerance_pct:
                group.append(sql_b)
                used.add(sql_b.get("sql_id", ""))

        if len(group) >= 2:
            groups.append(group)

    result = []
    for idx, group in enumerate(groups):
        combined_elapsed = sum(_float(s.get("bad_elapsed_secs", 0)) for s in group)
        avg_execs = sum(int(_float(s.get("bad_executions", 0))) for s in group) / len(group)
        result.append({
            "group_id": idx + 1,
            "label": f"Batch Group {chr(65 + idx)}",  # A, B, C...
            "sql_ids": [s.get("sql_id", "") for s in group],
            "exec_count": int(avg_execs),
            "combined_elapsed_secs": round(combined_elapsed, 2),
            "sql_count": len(group),
        })

    result.sort(key=lambda g: -g["combined_elapsed_secs"])
    return result


# ---------------------------------------------------------------------------
# DESIGN 9 — Culprits reorder by normalized impact
# ---------------------------------------------------------------------------

def rank_culprits(
    sql_regressions: list[dict],
    good_data: dict,
    bad_data: dict,
    batch_groups: list[dict],
    workload_good: list[dict],
    workload_bad: list[dict],
) -> list[dict]:
    """Rank culprits by elapsed-time-per-minute (normalized to window duration).

    Returns list of {rank, sql_id, category, elapsed_per_min,
    total_elapsed, pct_db_time, batch_group, tag}.
    """
    bad_elapsed_min = _float(bad_data.get("elapsed_min", 0))
    bad_db_time_secs = _float(bad_data.get("db_time_min", 0)) * 60.0
    if bad_elapsed_min <= 0:
        bad_elapsed_min = 1.0

    # Build batch group lookup
    sql_to_group: dict[str, str] = {}
    for bg in batch_groups:
        for sid in bg.get("sql_ids", []):
            sql_to_group[sid] = bg["label"]

    # Build workload category lookup from bad period
    bad_sql = bad_data.get("sql_stats", [])
    sql_to_category: dict[str, str] = {}
    for sql in bad_sql:
        sid = sql.get("sql_id", "")
        if sid:
            sql_to_category[sid] = _classify_module(
                sql.get("module", ""),
                sql.get("sql_text", ""),
            )

    # Only include non-stable SQL
    culprit_sql = [
        s for s in sql_regressions
        if s.get("tag") in ("new_offender", "regression", "load_increase")
    ]

    result = []
    for sql in culprit_sql:
        sid = sql.get("sql_id", "")
        elapsed = _float(sql.get("bad_elapsed_secs", 0))
        elapsed_per_min = elapsed / bad_elapsed_min
        pct_db = (elapsed / bad_db_time_secs * 100.0) if bad_db_time_secs > 0 else 0.0

        result.append({
            "sql_id": sid,
            "category": sql_to_category.get(sid, "Application"),
            "elapsed_per_min": round(elapsed_per_min, 2),
            "total_elapsed_secs": round(elapsed, 2),
            "pct_db_time": round(pct_db, 2),
            "batch_group": sql_to_group.get(sid, ""),
            "tag": sql.get("tag", "stable"),
            "sql_text_short": (sql.get("sql_text_truncated", "") or "")[:100],
        })

    result.sort(key=lambda x: -x["elapsed_per_min"])

    # Add rank
    for i, r in enumerate(result):
        r["rank"] = i + 1

    return result


# ---------------------------------------------------------------------------
# Master function — produce all advanced analytics at once
# ---------------------------------------------------------------------------

def compute_advanced_analytics(
    good_data: dict,
    bad_data: dict,
    sql_regressions: list[dict],
    wait_comparisons: list[dict],
    efficiency_comparisons: list[dict],
) -> dict:
    """Compute all 9 design outputs in a single call.

    Returns a dict with keys matching each design number.
    """
    wl_good = workload_composition(good_data)
    wl_bad = workload_composition(bad_data)

    cursor_good = cursor_health_score(good_data)
    cursor_bad = cursor_health_score(bad_data)

    causal = build_causal_chains(
        good_data, bad_data,
        sql_regressions, wait_comparisons, efficiency_comparisons,
    )

    purges = detect_batch_purges(bad_data)

    throughput = business_throughput(good_data, bad_data)

    sql_assessed = sql_net_assessment(sql_regressions)

    batch_groups = detect_batch_groups(sql_regressions)

    culprits = rank_culprits(
        sql_regressions, good_data, bad_data,
        batch_groups, wl_good, wl_bad,
    )

    return {
        "workload_composition": {"good": wl_good, "bad": wl_bad},
        "cursor_health": {"good": cursor_good, "bad": cursor_bad},
        "causal_chains": causal,
        "batch_purges": purges,
        "business_throughput": throughput,
        "sql_net_assessments": sql_assessed,
        "batch_groups": batch_groups,
        "culprits": culprits,
    }


def compute_single_analytics(data: dict) -> dict:
    """Compute analytics for a single AWR snapshot using the same engines as compare mode."""
    wl = workload_composition(data)
    cursor = cursor_health_score(data)
    purges = detect_batch_purges(data)
    return {
        "workload_composition": wl,
        "cursor_health": cursor,
        "batch_purges": purges,
    }
