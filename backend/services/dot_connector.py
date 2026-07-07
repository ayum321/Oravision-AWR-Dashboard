"""
AWR Dot-Connector Analysis Engine
===================================
Connects the dots across AWR sections to produce smart, AI-style insights.
Follows the real-world DBA methodology:
  1. Where is DB Time going? (Time Model / Wait Class breakdown)
  2. Load Profile shifts — what changed?
  3. SQL Analysis — execution count changes vs per-exec time changes
  4. Wait Events — what's blocking sessions?
  5. Cross-reference ADDM + Efficiency + OS stats

Key principle: AWR aggregates data. This engine un-aggregates the story.
- Execution count increase = data volume change, NOT a SQL regression
- Per-execution time increase = plan flip or resource contention
- New SQL IDs = code deployment or ad-hoc queries
- Log file sync spikes = commit-in-loop anti-pattern
"""
from __future__ import annotations

from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_eff(data: dict, field: str) -> float:
    eff = data.get("efficiency", {})
    return eff.get(field, 0.0) if isinstance(eff, dict) else getattr(eff, field, 0.0)


def _get_os(data: dict, field: str) -> float:
    os_s = data.get("os_stats", {})
    return os_s.get(field, 0.0) if isinstance(os_s, dict) else getattr(os_s, field, 0.0)


def _lp_val(data: dict, pattern: str) -> float:
    for m in data.get("load_profile", []):
        name = m.get("stat_name", "") if isinstance(m, dict) else getattr(m, "stat_name", "")
        if pattern.lower() in name.lower():
            return m.get("per_sec", 0.0) if isinstance(m, dict) else getattr(m, "per_sec", 0.0)
    return 0.0


def _wait_event(data: dict, pattern: str) -> dict | None:
    for ev in data.get("wait_events", []):
        name = ev.get("event_name", "") if isinstance(ev, dict) else ""
        if pattern.lower() in name.lower():
            return ev
    return None


def _wait_pct(data: dict, pattern: str) -> float:
    ev = _wait_event(data, pattern)
    return ev.get("pct_db_time", 0.0) if ev else 0.0


def _wait_avg_ms(data: dict, pattern: str) -> float:
    ev = _wait_event(data, pattern)
    return ev.get("avg_wait_ms", 0.0) if ev else 0.0


def _wait_time_secs(data: dict, pattern: str) -> float:
    ev = _wait_event(data, pattern)
    return ev.get("time_waited_secs", 0.0) if ev else 0.0


def _wait_total_waits(data: dict, pattern: str) -> float:
    ev = _wait_event(data, pattern)
    return ev.get("total_waits", 0) if ev else 0


def _tm_pct(data: dict, pattern: str) -> float:
    for t in data.get("time_model", []):
        name = t.get("stat_name", "") if isinstance(t, dict) else ""
        if pattern.lower() in name.lower():
            return t.get("pct_db_time", 0.0) if isinstance(t, dict) else 0.0
    return 0.0


def _tm_secs(data: dict, pattern: str) -> float:
    for t in data.get("time_model", []):
        name = t.get("stat_name", "") if isinstance(t, dict) else ""
        if pattern.lower() in name.lower():
            return t.get("time_secs", 0.0) if isinstance(t, dict) else 0.0
    return 0.0


def _aas(data: dict) -> float:
    elapsed = data.get("elapsed_min", 0)
    db_time = data.get("db_time_min", 0)
    return db_time / elapsed if elapsed and elapsed > 0 else 0.0


def _db_time_ratio(data: dict) -> float:
    return _aas(data)


def _get_sql_stats(data: dict) -> list[dict]:
    return data.get("sql_stats", [])


def _get_wait_class_breakdown(data: dict) -> dict[str, float]:
    """Aggregate wait events by wait class to see where DB time goes."""
    breakdown = {}
    for ev in data.get("wait_events", []):
        wc = ev.get("wait_class", "Other") or "Other"
        pct = ev.get("pct_db_time", 0.0)
        breakdown[wc] = breakdown.get(wc, 0.0) + pct
    return breakdown


# ──────────────────────────────────────────────────────────────────────────────
# Single-report dot-connection analysis
# ──────────────────────────────────────────────────────────────────────────────

def analyze_awr_data(data: dict) -> list[dict[str, Any]]:
    """Analyze a single AWR report and produce connected insights."""
    insights: list[dict[str, Any]] = []
    cpus = data.get("cpus", 0) or data.get("num_cpus", 0) or 1
    aas = _aas(data)
    ratio = _db_time_ratio(data)
    db_time_min = data.get("db_time_min", 0)
    elapsed_min = data.get("elapsed_min", 0)

    # ── 0. DB Time Breakdown — WHERE is time going? ──────────────────────
    # This is the FIRST thing a DBA looks at
    wait_breakdown = _get_wait_class_breakdown(data)
    db_cpu_pct = _wait_pct(data, "DB CPU") or _tm_pct(data, "DB CPU")
    io_pct = wait_breakdown.get("User I/O", 0) + wait_breakdown.get("System I/O", 0)
    concurrency_pct = wait_breakdown.get("Concurrency", 0)
    commit_pct = wait_breakdown.get("Commit", 0)
    app_pct = wait_breakdown.get("Application", 0)

    if db_time_min > 0:
        top_class = max(wait_breakdown.items(), key=lambda x: x[1]) if wait_breakdown else ("DB CPU", db_cpu_pct)
        evidence = [f"DB Time: {db_time_min:.1f} min, Elapsed: {elapsed_min:.1f} min, AAS: {aas:.1f}"]
        if db_cpu_pct > 0:
            evidence.append(f"DB CPU: {db_cpu_pct:.1f}% of DB Time")
        for wc, pct in sorted(wait_breakdown.items(), key=lambda x: -x[1])[:5]:
            if pct > 0.5:
                evidence.append(f"{wc}: {pct:.1f}% of DB Time")

        severity = "info"
        if ratio > 5:
            severity = "critical"
        elif ratio > 2:
            severity = "warning"

        insights.append({
            "severity": severity,
            "title": "DB Time Breakdown",
            "summary": (
                f"DB Time is {ratio:.1f}x elapsed time (AAS: {aas:.1f}, CPUs: {cpus}). "
                f"Primary time consumer: {top_class[0]} at {top_class[1]:.1f}% of DB Time. "
                + (f"CPU-bound workload. " if db_cpu_pct > 50 else "")
                + (f"I/O-bound workload ({io_pct:.0f}% in I/O waits). " if io_pct > 30 else "")
                + (f"Concurrency contention significant ({concurrency_pct:.0f}%). " if concurrency_pct > 10 else "")
                + (f"Commit overhead notable ({commit_pct:.0f}%). " if commit_pct > 5 else "")
            ),
            "evidence": evidence,
            "root_cause": (
                "CPU-bound: check top SQL by CPU time, inefficient plans, PL/SQL loops." if db_cpu_pct > 50
                else "I/O-bound: check buffer cache sizing, missing indexes, full table scans." if io_pct > 30
                else "Concurrency: check lock contention, latch waits, buffer busy." if concurrency_pct > 15
                else "Mixed workload — review top SQL and wait events for specific bottlenecks."
            ),
            "action": (
                "Review SQL ordered by CPU Time. Check for unnecessary full scans." if db_cpu_pct > 50
                else "Review SQL ordered by Reads. Check buffer cache hit ratio and add indexes." if io_pct > 30
                else "Check V$LOCK for blocking sessions. Review top waits by class." if concurrency_pct > 15
                else "Review top 5 wait events and top SQL by elapsed time."
            ),
        })

    # ── 1. SQL Concentration Analysis ────────────────────────────────────
    # Are a few SQLs dominating? This reveals batch jobs or problem queries
    sqls = _get_sql_stats(data)
    if sqls and db_time_min > 0:
        db_time_secs = db_time_min * 60
        sorted_sqls = sorted(sqls, key=lambda s: s.get("elapsed_time_secs", 0), reverse=True)
        top1 = sorted_sqls[0] if sorted_sqls else {}
        top3_elapsed = sum(s.get("elapsed_time_secs", 0) for s in sorted_sqls[:3])
        top1_pct = (top1.get("elapsed_time_secs", 0) / db_time_secs * 100) if db_time_secs > 0 else 0
        top3_pct = (top3_elapsed / db_time_secs * 100) if db_time_secs > 0 else 0

        if top1_pct > 30 or top3_pct > 60:
            top_details = []
            for s in sorted_sqls[:3]:
                sid = s.get("sql_id", "?")
                elapsed = s.get("elapsed_time_secs", 0)
                execs = s.get("executions", 0)
                per_exec = elapsed / execs if execs > 0 else elapsed
                cpu = s.get("cpu_time_secs", 0)
                sql_text = (s.get("sql_text", "") or "")[:60]
                top_details.append(
                    f"{sid}: {elapsed:.0f}s total, {execs} execs, {per_exec:.2f}s/exec, "
                    f"CPU {cpu:.0f}s — {sql_text}"
                )

            # Determine if it's a volume issue or slow query
            top1_execs = top1.get("executions", 0)
            top1_per_exec = top1.get("elapsed_time_secs", 0) / top1_execs if top1_execs > 0 else top1.get("elapsed_time_secs", 0)

            # Single-execution confidence discount — mirrors the compare-mode
            # SQL ranking scorer's discount (executions<=1 -> reliability caveat).
            # A single-execution SQL dominating elapsed time is frequently a
            # top-level batch-job dispatcher/wrapper block (AWR attributes the
            # ENTIRE job's wall-clock time to one top-level cursor) or an ad-hoc
            # one-shot statement, not necessarily "the" problem query — do not
            # report it as a confirmed concentration finding without that caveat.
            single_exec_caveat = top1_execs == 1

            if single_exec_caveat:
                root = (
                    f"SQL {top1.get('sql_id','?')} ran only once but accounts for {top1_pct:.0f}% of DB Time. "
                    f"A single-execution statement dominating elapsed time is often a top-level batch-job "
                    f"dispatcher/wrapper (AWR attributes the whole job's runtime to it) rather than the actual "
                    f"regressed statement — inspect the SQL text for a step-dispatch pattern before tuning it directly."
                )
            elif top1_execs > 1000 and top1_per_exec < 1:
                root = (
                    f"SQL {top1.get('sql_id','?')} executes {top1_execs:,} times at {top1_per_exec:.3f}s each. "
                    f"This is a high-frequency lightweight query — the volume is the problem, not the query itself. "
                    f"Check if data volume increased or if application is calling this in a loop."
                )
            elif top1_per_exec > 10:
                root = (
                    f"SQL {top1.get('sql_id','?')} averages {top1_per_exec:.1f}s per execution — this is a slow query. "
                    f"Check execution plan, missing indexes, or stale statistics."
                )
            else:
                root = f"Top SQL {top1.get('sql_id','?')}: {top1_execs} executions at {top1_per_exec:.2f}s each."

            insights.append({
                "severity": "warning" if single_exec_caveat else ("critical" if top1_pct > 50 else "warning"),
                "title": f"Top SQL Dominating DB Time ({top1_pct:.0f}%)" + (" — verify not a job wrapper" if single_exec_caveat else ""),
                "summary": (
                    f"Top 1 SQL consumes {top1_pct:.0f}% of DB Time, top 3 consume {top3_pct:.0f}%. "
                    f"{'Severe concentration — fix these and overall performance improves dramatically.' if top3_pct > 60 else 'Significant concentration in few SQL statements.'}"
                ),
                "evidence": top_details,
                "root_cause": root,
                "action": (
                    f"Focus tuning on SQL {top1.get('sql_id','?')}. "
                    + ("Reduce execution count — check application loop logic. " if top1_execs > 1000 and top1_per_exec < 1 else "")
                    + ("Check execution plan with DBMS_XPLAN.DISPLAY_CURSOR. Verify statistics freshness. " if top1_per_exec > 5 else "")
                    + "Use SQL Tuning Advisor: EXEC DBMS_SQLTUNE.CREATE_TUNING_TASK."
                ),
            })

    # ── 2. Hard Parse Storm detection ────────────────────────────────────
    hard_parses = _lp_val(data, "hard parse")
    soft_parse_pct = _get_eff(data, "soft_parse_pct")
    parse_time_pct = _tm_pct(data, "parse time elapsed")
    latch_sp_pct = _wait_pct(data, "latch: shared pool")

    if hard_parses > 50 or (0 < soft_parse_pct < 90):
        evidence = [f"Hard parses: {hard_parses:.0f}/sec", f"Soft parse %: {soft_parse_pct:.1f}%"]
        if parse_time_pct > 5:
            evidence.append(f"Parse time: {parse_time_pct:.1f}% of DB time")
        if latch_sp_pct > 0:
            evidence.append(f"Latch: shared pool waits: {latch_sp_pct:.1f}% of DB time")

        insights.append({
            "severity": "critical" if hard_parses > 200 or latch_sp_pct > 5 else "warning",
            "title": "Parsing Overhead (Hard Parse Storm)",
            "summary": (
                f"Hard parse rate is {hard_parses:.0f}/sec with soft parse ratio at {soft_parse_pct:.1f}%. "
                f"{'Shared pool latch contention detected — this is severe.' if latch_sp_pct > 1 else ''} "
                "Literal SQL without bind variables is the most common cause."
            ),
            "evidence": evidence,
            "root_cause": "Application SQL using literal values instead of bind variables, flooding the shared pool with unique cursors.",
            "action": "Set CURSOR_SHARING=FORCE for immediate relief. Long-term: rewrite SQL to use bind variables. Monitor V$SQLAREA for non-sharable cursors.",
        })

    # ── 3. I/O Bottleneck ────────────────────────────────────────────────
    seq_read_pct = _wait_pct(data, "db file sequential read")
    seq_read_ms = _wait_avg_ms(data, "db file sequential read")
    scattered_pct = _wait_pct(data, "db file scattered read")
    phys_reads = _lp_val(data, "physical read")
    buffer_hit = _get_eff(data, "buffer_cache_hit_pct")

    if seq_read_pct > 10 or scattered_pct > 5 or (0 < buffer_hit < 90):
        evidence = []
        if seq_read_pct > 0:
            evidence.append(f"db file sequential read: {seq_read_pct:.1f}% DB time, avg {seq_read_ms:.1f}ms {'(SLOW)' if seq_read_ms > 10 else '(OK)'}")
        if scattered_pct > 0:
            evidence.append(f"db file scattered read: {scattered_pct:.1f}% DB time (full table scans)")
        if phys_reads > 0:
            evidence.append(f"Physical reads: {phys_reads:.0f}/sec")
        if 0 < buffer_hit < 100:
            evidence.append(f"Buffer cache hit: {buffer_hit:.1f}% {'(LOW)' if buffer_hit < 95 else ''}")

        is_storage_slow = seq_read_ms > 10
        is_full_scans = scattered_pct > seq_read_pct

        insights.append({
            "severity": "critical" if (seq_read_pct + scattered_pct) > 30 or buffer_hit < 90 else "warning",
            "title": "I/O Bottleneck" + (" — Slow Storage" if is_storage_slow else " — Full Table Scans" if is_full_scans else ""),
            "summary": (
                f"I/O waits consume {seq_read_pct + scattered_pct:.0f}% of DB time. "
                + (f"Storage latency is {seq_read_ms:.0f}ms (should be <5ms for SSD). " if is_storage_slow else "")
                + (f"Full table scan waits ({scattered_pct:.0f}%) suggest missing indexes. " if is_full_scans else "")
            ),
            "evidence": evidence,
            "root_cause": (
                "Storage subsystem is slow — check ASM rebalance, disk health, SAN throughput." if is_storage_slow
                else "Excessive full table scans — missing indexes or stale optimizer statistics." if is_full_scans
                else "High I/O volume — review SQL ordered by Physical Reads."
            ),
            "action": (
                "Check SQL ordered by Reads. "
                + ("Move data to faster storage. Check AWR I/O stats per tablespace. " if is_storage_slow else "")
                + ("Add indexes for full-scan queries: review SQL ordered by Buffer Gets. " if is_full_scans else "")
                + ("Increase DB_CACHE_SIZE. " if buffer_hit < 95 else "")
            ),
        })

    # ── 4. Log File Sync / Commit Storm ──────────────────────────────────
    # Real-world: "AWR showed log file sync. Many assumed storage. ASH revealed
    # a module committing inside a loop thousands of times per second."
    log_sync_pct = _wait_pct(data, "log file sync")
    log_sync_ms = _wait_avg_ms(data, "log file sync")
    log_sync_waits = _wait_total_waits(data, "log file sync")
    commits_per_sec = _lp_val(data, "user commit") or _lp_val(data, "commit")
    txns_per_sec = _lp_val(data, "user call") or _lp_val(data, "transaction")

    if log_sync_pct > 2 or log_sync_ms > 10:
        evidence = [
            f"log file sync: {log_sync_pct:.1f}% DB time, avg {log_sync_ms:.1f}ms",
            f"Total log sync waits: {log_sync_waits:,.0f}",
        ]
        if commits_per_sec > 0:
            evidence.append(f"Commits/sec: {commits_per_sec:.0f}")

        # Distinguish storage-slow from commit-too-frequent
        is_commit_storm = commits_per_sec > 500 and log_sync_ms < 15
        is_storage_issue = log_sync_ms > 15

        insights.append({
            "severity": "critical" if log_sync_ms > 20 or is_commit_storm else "warning",
            "title": "Commit Storm" if is_commit_storm else "Log File Sync — Redo I/O Bottleneck",
            "summary": (
                f"Log file sync at {log_sync_pct:.1f}% DB time, avg {log_sync_ms:.1f}ms. "
                + (f"Commit rate is {commits_per_sec:.0f}/sec — application is committing too frequently. "
                   "This is typically a COMMIT inside a loop." if is_commit_storm else "")
                + (f"Redo log write latency is {log_sync_ms:.0f}ms — storage is slow for redo writes." if is_storage_issue else "")
            ),
            "evidence": evidence,
            "root_cause": (
                "Application is committing inside a loop (thousands of micro-commits). "
                "Each COMMIT forces a redo log write and waits for it to complete."
                if is_commit_storm else
                "Redo log storage is slow. Check if redo logs are on shared storage, "
                "undersized, or competing with datafile I/O."
            ),
            "action": (
                "Batch commits: COMMIT every 1000-5000 rows instead of every row. "
                "Use FORALL with SAVE EXCEPTIONS in PL/SQL. "
                "Check application code for COMMIT inside cursor loops."
                if is_commit_storm else
                "Move redo logs to faster storage (NVMe/battery-backed write cache). "
                "Size redo logs to <3 switches/hour. Separate redo from datafiles."
            ),
        })

    # ── 5. Lock Contention ───────────────────────────────────────────────
    tx_lock_pct = _wait_pct(data, "enq: TX")
    if tx_lock_pct == 0:
        tx_lock_pct = _wait_pct(data, "row lock")
    lib_cache_pct = _wait_pct(data, "library cache")
    buffer_busy_pct = _wait_pct(data, "buffer busy")

    total_contention = tx_lock_pct + lib_cache_pct + buffer_busy_pct
    if total_contention > 2:
        evidence = []
        if tx_lock_pct > 0:
            evidence.append(f"TX row lock: {tx_lock_pct:.1f}% DB time")
        if lib_cache_pct > 0:
            evidence.append(f"Library cache: {lib_cache_pct:.1f}% DB time")
        if buffer_busy_pct > 0:
            evidence.append(f"Buffer busy: {buffer_busy_pct:.1f}% DB time")

        insights.append({
            "severity": "critical" if total_contention > 10 else "warning",
            "title": "Concurrency Contention",
            "summary": (
                f"Concurrency-related waits total {total_contention:.1f}% of DB time. "
                + (f"Row lock contention ({tx_lock_pct:.1f}%) — sessions blocking each other. " if tx_lock_pct > 1 else "")
                + (f"Library cache contention ({lib_cache_pct:.1f}%) — shared pool pressure. " if lib_cache_pct > 1 else "")
            ),
            "evidence": evidence,
            "root_cause": (
                "Multiple sessions updating same rows, or long uncommitted transactions."
                if tx_lock_pct > lib_cache_pct else
                "Shared pool contention from parsing or shared pool sizing."
            ),
            "action": (
                "Check V$LOCK and V$SESSION for blocking chains. "
                "Add missing FK indexes. Reduce transaction scope."
                if tx_lock_pct > 1 else
                "Increase SHARED_POOL_SIZE. Use bind variables. Pin hot cursors."
            ),
        })

    # ── 5b. Configuration Wait Class (enq:HW, enq:CF, log buffer space) ─
    config_pct = wait_breakdown.get("Configuration", 0)
    hw_pct = _wait_pct(data, "enq: HW")
    hw_avg_ms = _wait_avg_ms(data, "enq: HW")

    if config_pct > 5 or hw_pct > 2:
        evidence = [f"Configuration wait class: {config_pct:.1f}% of DB Time"]
        if hw_pct > 0:
            evidence.append(f"enq: HW - contention: {hw_pct:.1f}% DB time, avg {hw_avg_ms:.1f}ms")

        # Cross-reference: find top INSERT by executions
        insert_detail = ""
        insert_sqls = [s for s in sqls if "INSERT" in (s.get("sql_text", "") or "").upper()]
        insert_sqls.sort(key=lambda s: s.get("executions", 0), reverse=True)
        if insert_sqls and hw_pct > 2:
            top_ins = insert_sqls[0]
            ins_id = top_ins.get("sql_id", "?")
            ins_execs = top_ins.get("executions", 0)
            ins_text = (top_ins.get("sql_text", "") or "")[:80]
            evidence.append(f"Top INSERT: {ins_id} ({ins_execs:,} execs) — {ins_text}")
            insert_detail = (
                f" Top INSERT SQL: {ins_id} ({ins_execs:,} executions) — "
                f"its target table is almost certainly the hot segment."
            )

        insights.append({
            "severity": "critical" if config_pct > 20 or (hw_pct > 5 and hw_avg_ms > 1000) else "warning",
            "title": (
                f"Segment Extension Bottleneck (enq: HW)" if hw_pct > config_pct * 0.5
                else f"Configuration Wait Class: {config_pct:.1f}% DB Time"
            ),
            "summary": (
                (f"enq: HW - contention at {hw_pct:.1f}% DB time (avg {hw_avg_ms:.1f}ms). "
                 f"Multiple sessions simultaneously extending the SAME segment beyond its High Water Mark. "
                 f"Only ONE session holds HW enqueue at a time — all others queue.{insert_detail}"
                 if hw_pct > 2 else
                 f"Configuration wait class consuming {config_pct:.1f}% of DB Time. "
                 f"This is a resource sizing problem, NOT a SQL tuning or concurrency issue.")
            ),
            "evidence": evidence,
            "root_cause": (
                "High-volume concurrent INSERTs into one table. "
                "Oracle must extend the segment one session at a time. "
                "Pre-allocate extents or use larger NEXT extent size."
                if hw_pct > 2 else
                "Configuration-class waits indicate resource sizing problems: "
                "extent management, redo buffer sizing, or controlfile contention."
            ),
            "action": (
                "Pre-allocate extents: ALTER TABLE t ALLOCATE EXTENT (SIZE 100M). "
                "Increase NEXT extent size in storage clause. "
                "Run before batch: DBMS_SPACE.GROW_EXTENT or manual DDL."
                if hw_pct > 2 else
                "Check V$ENQUEUE_STATISTICS for the dominant enqueue. "
                "This requires administrative/DDL fix, not SQL tuning."
            ),
        })

    # ── 6. CPU Saturation ────────────────────────────────────────────────
    cpu_busy = _get_os(data, "cpu_busy_pct")
    if (cpu_busy > 85 or aas > cpus * 1.2) and db_cpu_pct > 30:
        insights.append({
            "severity": "critical" if cpu_busy > 95 or aas > cpus * 2 else "warning",
            "title": "CPU Saturation",
            "summary": (
                f"Host CPU is {cpu_busy:.1f}% busy, DB CPU is {db_cpu_pct:.1f}% of DB time. "
                f"AAS ({aas:.1f}) {'exceeds' if aas > cpus else 'approaches'} CPU count ({cpus})."
            ),
            "evidence": [f"Host CPU: {cpu_busy:.1f}%", f"DB CPU: {db_cpu_pct:.1f}% of DB time", f"AAS: {aas:.1f}, CPUs: {cpus}"],
            "root_cause": "CPU-intensive SQL — inefficient plans, unnecessary full scans, or PL/SQL row-by-row processing.",
            "action": "Check SQL ordered by CPU Time. Use SQL Tuning Advisor. Consider parallel query hints for large scans.",
        })

    # ── 7. ADDM Cross-reference ──────────────────────────────────────────
    addm = data.get("addm_findings", [])
    if addm:
        top_findings = {}
        for f in addm:
            name = f.get("finding_name", "")
            pct = f.get("pct_active_sessions", 0)
            if name and (name not in top_findings or pct > top_findings[name]):
                top_findings[name] = pct

        # Special handling: "High Watermark Waits" overrides other hypotheses
        hw_addm_name = None
        for name in top_findings:
            if "high watermark" in name.lower() or "high water mark" in name.lower():
                hw_addm_name = name
                break
        if hw_addm_name:
            hw_addm_pct = top_findings[hw_addm_name]
            hw_wait = _wait_pct(data, "enq: HW")
            evidence = [f"ADDM finding: {hw_addm_name} at {hw_addm_pct:.0f}% active sessions"]
            if hw_wait > 0:
                evidence.append(f"enq: HW - contention: {hw_wait:.1f}% DB time — CROSS-CONFIRMED")
            insights.append({
                "severity": "critical",
                "title": f"ADDM CONFIRMED: {hw_addm_name}",
                "summary": (
                    f"Oracle ADDM detected segment extension as primary wait cause ({hw_addm_pct:.0f}% active sessions). "
                    f"This overrides all other root cause hypotheses for this period. "
                    f"{'enq: HW at ' + str(round(hw_wait,1)) + '% DB time confirms the diagnosis.' if hw_wait > 0 else ''} "
                    f"Find which segment (table/index) is being extended — cross-reference with top INSERT SQL."
                ),
                "evidence": evidence,
                "root_cause": (
                    "ADDM's own diagnostic conclusion: segment extension contention is the dominant issue. "
                    "Never ignore this in favor of a different manual hypothesis."
                ),
                "action": (
                    "1. Find hot segment: SELECT * FROM V$SEGMENT_STATISTICS WHERE statistic_name = 'segment scans' ORDER BY value DESC. "
                    "2. Cross-reference with top INSERT SQL by executions. "
                    "3. Pre-allocate extents: ALTER TABLE <hot_table> ALLOCATE EXTENT (SIZE 100M)."
                ),
            })

        # Special handling: "Undersized SGA" and "Buffer Busy Hot Objects"
        for name, pct in top_findings.items():
            name_lower = name.lower()
            if "undersized sga" in name_lower or "buffer busy" in name_lower:
                insights.append({
                    "severity": "warning",
                    "title": f"ADDM: {name}",
                    "summary": (
                        f"Oracle ADDM found '{name}' at {pct:.0f}% active sessions. "
                        f"{'SGA memory is insufficient — buffer cache or shared pool too small.' if 'sga' in name_lower else 'Hot object contention detected by ADDM.'}"
                    ),
                    "evidence": [f"ADDM finding: {name} at {pct:.0f}% active sessions"],
                    "root_cause": f"ADDM auto-detected: {name}.",
                    "action": f"Follow ADDM recommendations for '{name}'.",
                })

        for name, pct in top_findings.items():
            if pct > 50 and name != hw_addm_name and "undersized sga" not in name.lower() and "buffer busy" not in name.lower():
                insights.append({
                    "severity": "critical" if pct > 80 else "warning",
                    "title": f"ADDM: {name}",
                    "summary": f"Oracle ADDM found '{name}' consuming {pct:.0f}% of active sessions. Primary bottleneck.",
                    "evidence": [f"ADDM finding: {name} at {pct:.0f}% active sessions"],
                    "root_cause": f"ADDM auto-detected this as the dominant issue.",
                    "action": f"Follow ADDM recommendations for '{name}'. Cross-reference with top SQL and wait events above.",
                })

    # ── 8. Memory Pressure ───────────────────────────────────────────────
    free_mem = _get_os(data, "free_mem_gb")
    phys_mem = _get_os(data, "phys_mem_gb")
    if phys_mem == 0:
        phys_mem = data.get("memory_gb", 0) or 1

    if phys_mem > 0 and free_mem > 0:
        free_pct = (free_mem / phys_mem) * 100
        if free_pct < 10:
            insights.append({
                "severity": "critical" if free_pct < 5 else "warning",
                "title": "Host Memory Pressure",
                "summary": f"Only {free_mem:.1f} GB free of {phys_mem:.1f} GB ({free_pct:.1f}% free). OS swapping risk.",
                "evidence": [f"Free: {free_mem:.1f} GB", f"Total: {phys_mem:.1f} GB"],
                "root_cause": "SGA + PGA + OS overhead exceeding physical memory.",
                "action": "Check SGA/PGA sizing. Reduce PGA_AGGREGATE_TARGET if sort spills are low. Monitor OS swap.",
            })

    # ── 9. Healthy summary ───────────────────────────────────────────────
    if len(insights) <= 1:  # Only the DB Time breakdown
        insights.append({
            "severity": "good",
            "title": "System Healthy",
            "summary": "No significant performance issues detected in this AWR report.",
            "evidence": [
                f"DB Time ratio: {ratio:.2f}x",
                f"Buffer cache hit: {buffer_hit:.1f}%",
                f"Soft parse: {soft_parse_pct:.1f}%",
            ],
            "root_cause": "Normal operating conditions.",
            "action": "Continue monitoring. Baseline these metrics for future comparison.",
        })

    _sev_order = {"critical": 0, "warning": 1, "info": 2, "good": 3}
    insights.sort(key=lambda x: _sev_order.get(x["severity"], 9))
    return insights


# ──────────────────────────────────────────────────────────────────────────────
# Comparison dot-connection analysis
# ──────────────────────────────────────────────────────────────────────────────

def analyze_comparison(
    good_data: dict,
    bad_data: dict,
    report: dict,
) -> list[dict[str, Any]]:
    """Analyze a good vs bad comparison and produce connected insights.

    This follows the real-world DBA methodology:
    1. How much worse is it? (DB Time, AAS magnitude)
    2. WHERE is the extra time going? (Wait class shift)
    3. WHY? — SQL analysis: execution count change vs per-exec time change
    4. Cross-reference with wait events, efficiency, incidents
    """
    insights: list[dict[str, Any]] = []

    good_ratio = _db_time_ratio(good_data)
    bad_ratio = _db_time_ratio(bad_data)
    good_aas = _aas(good_data)
    bad_aas = _aas(bad_data)
    good_db_time = good_data.get("db_time_min", 0)
    bad_db_time = bad_data.get("db_time_min", 0)
    good_elapsed = good_data.get("elapsed_min", 0)
    bad_elapsed = bad_data.get("elapsed_min", 0)

    # ── 1. Magnitude of change ───────────────────────────────────────────
    db_time_change_pct = ((bad_db_time - good_db_time) / good_db_time * 100) if good_db_time > 0 else 0
    elapsed_change_pct = ((bad_elapsed - good_elapsed) / good_elapsed * 100) if good_elapsed > 0 else 0

    severity = "info"
    if abs(db_time_change_pct) > 100:
        severity = "critical"
    elif abs(db_time_change_pct) > 30:
        severity = "warning"

    insights.append({
        "severity": severity,
        "title": f"Workload Change: DB Time {'increased' if db_time_change_pct > 0 else 'decreased'} {abs(db_time_change_pct):.0f}%",
        "summary": (
            f"DB Time: {good_db_time:.1f} min → {bad_db_time:.1f} min ({db_time_change_pct:+.0f}%). "
            f"Elapsed: {good_elapsed:.1f} min → {bad_elapsed:.1f} min ({elapsed_change_pct:+.0f}%). "
            f"AAS: {good_aas:.1f} → {bad_aas:.1f}."
        ),
        "evidence": [
            f"Good: DB Time {good_db_time:.1f} min, Elapsed {good_elapsed:.1f} min, AAS {good_aas:.1f}",
            f"Bad: DB Time {bad_db_time:.1f} min, Elapsed {bad_elapsed:.1f} min, AAS {bad_aas:.1f}",
            f"DB Time change: {db_time_change_pct:+.0f}%",
            f"Elapsed change: {elapsed_change_pct:+.0f}%",
        ],
        "root_cause": (
            "Significant workload increase — more SQL activity, higher concurrency, or data volume growth."
            if db_time_change_pct > 50 else
            "Moderate change — could be data volume, timing, or a specific regression."
            if db_time_change_pct > 10 else
            "Minimal change — look for specific SQL or wait event shifts."
        ),
        "action": "Review the SQL and wait event analysis below to identify root cause.",
    })

    # ── 1b. Baseline Stress Detection — is the "good" period actually healthy? ──
    good_cpus = good_data.get("cpus", 0) or good_data.get("num_cpus", 0) or 1
    good_cpu_busy = _get_os(good_data, "cpu_busy_pct")
    good_latch_hit = _get_eff(good_data, "latch_hit_pct")
    good_buffer_hit = _get_eff(good_data, "buffer_cache_hit_pct")

    baseline_stressed = False
    stress_evidence = []

    if good_aas >= good_cpus * 0.9:
        baseline_stressed = True
        stress_evidence.append(f"Baseline AAS={good_aas:.1f} vs {good_cpus} CPUs ({good_aas/good_cpus*100:.0f}% utilization)")

    if good_cpu_busy >= 90:
        baseline_stressed = True
        stress_evidence.append(f"Baseline Host CPU: {good_cpu_busy:.0f}% busy (near-saturated)")

    if 0 < good_latch_hit < 99.0:
        stress_evidence.append(f"Baseline latch hit: {good_latch_hit:.1f}% (degraded — not newly introduced in problem period)")

    if 0 < good_buffer_hit < 95:
        stress_evidence.append(f"Baseline buffer cache hit: {good_buffer_hit:.1f}% (already low)")

    # Check ADDM for pre-existing issues in baseline
    good_addm = good_data.get("addm_findings", [])
    pre_existing_addm = []
    for f in good_addm:
        fname = (f.get("finding_name", "") or "").lower()
        if "undersized sga" in fname or "buffer busy" in fname or "hot object" in fname:
            pre_existing_addm.append(f.get("finding_name", ""))
            stress_evidence.append(f"ADDM baseline finding: {f.get('finding_name', '')}")

    if baseline_stressed:
        insights.append({
            "severity": "warning",
            "title": "⚠ Baseline Already Stressed — Not a Clean Healthy Reference",
            "summary": (
                f"The baseline period itself was near-saturated "
                f"(AAS={good_aas:.1f} vs {good_cpus} CPUs = {good_aas/good_cpus*100:.0f}% utilization"
                f"{', Host CPU ' + str(round(good_cpu_busy)) + '% busy' if good_cpu_busy >= 90 else ''}). "
                f"The problem period degradation is ON TOP OF an already overloaded system. "
                f"{'Pre-existing ADDM findings: ' + ', '.join(pre_existing_addm) + '. ' if pre_existing_addm else ''}"
                f"Performance deltas may understate the true severity."
            ),
            "evidence": stress_evidence,
            "root_cause": (
                "The 'good' period was not a clean healthy baseline — it was already at or near capacity. "
                "Issues visible in the problem period may have pre-existing roots."
            ),
            "action": (
                "Compare against a genuinely idle/healthy period if available. "
                "Look at ADDM findings for the baseline period — any findings indicate pre-existing issues. "
                "Do not attribute all problem-period issues solely to new workload."
            ),
        })

    # ── 2. Wait Class Shift — WHERE is extra time going? ─────────────────
    good_breakdown = _get_wait_class_breakdown(good_data)
    bad_breakdown = _get_wait_class_breakdown(bad_data)
    good_cpu = _wait_pct(good_data, "DB CPU") or _tm_pct(good_data, "DB CPU")
    bad_cpu = _wait_pct(bad_data, "DB CPU") or _tm_pct(bad_data, "DB CPU")

    all_classes = set(list(good_breakdown.keys()) + list(bad_breakdown.keys()))
    shifts = []
    for wc in all_classes:
        g = good_breakdown.get(wc, 0)
        b = bad_breakdown.get(wc, 0)
        if abs(b - g) > 3:
            shifts.append({"class": wc, "good": g, "bad": b, "delta": b - g})

    if shifts:
        shifts.sort(key=lambda x: -abs(x["delta"]))
        evidence = []
        if abs(bad_cpu - good_cpu) > 3:
            evidence.append(f"DB CPU: {good_cpu:.1f}% → {bad_cpu:.1f}% ({bad_cpu - good_cpu:+.1f}pp)")
        for s in shifts[:5]:
            evidence.append(f"{s['class']}: {s['good']:.1f}% → {s['bad']:.1f}% ({s['delta']:+.1f}pp)")

        biggest = shifts[0]
        insights.append({
            "severity": "warning" if abs(biggest["delta"]) > 10 else "info",
            "title": f"Wait Profile Shifted — {biggest['class']} {'increased' if biggest['delta'] > 0 else 'decreased'}",
            "summary": (
                f"The extra DB time is primarily going to {biggest['class']} "
                f"({biggest['good']:.0f}% → {biggest['bad']:.0f}%). "
                + ("Sessions spending more time on CPU — check for new expensive SQL. " if biggest["class"] == "DB CPU" or (bad_cpu - good_cpu) > 10 else "")
                + ("I/O increased — data volume change or missing indexes. " if "I/O" in biggest["class"] else "")
                + ("More lock contention — check concurrent batch jobs. " if biggest["class"] == "Concurrency" else "")
                + ("Commit overhead increased — check for commit-in-loop pattern. " if biggest["class"] == "Commit" else "")
            ),
            "evidence": evidence,
            "root_cause": f"Wait class '{biggest['class']}' changed by {biggest['delta']:+.1f} percentage points.",
            "action": "Cross-reference this with the SQL analysis below to find the specific queries driving this shift.",
        })

    # ── 3. SQL Execution Count vs Per-Execution Time Analysis ────────────
    # KEY INSIGHT: Separate data volume change from actual SQL regression
    sql_regs = report.get("sql_regressions", [])
    good_sqls = {s.get("sql_id"): s for s in _get_sql_stats(good_data)}
    bad_sqls = {s.get("sql_id"): s for s in _get_sql_stats(bad_data)}

    new_offenders = [s for s in sql_regs if s.get("tag") == "new_offender"]
    regressions = [s for s in sql_regs if s.get("tag") == "regression"]
    load_increases = [s for s in sql_regs if s.get("tag") == "load_increase"]

    # Analyze execution count changes for common SQL IDs
    exec_spikes = []
    per_exec_regressions = []
    volume_driven = []

    common_ids = set(good_sqls.keys()) & set(bad_sqls.keys())
    for sid in common_ids:
        g = good_sqls[sid]
        b = bad_sqls[sid]
        g_execs = g.get("executions", 0) or 1
        b_execs = b.get("executions", 0) or 1
        g_elapsed = g.get("elapsed_time_secs", 0)
        b_elapsed = b.get("elapsed_time_secs", 0)
        g_per_exec = g_elapsed / g_execs
        b_per_exec = b_elapsed / b_execs
        exec_change = ((b_execs - g_execs) / g_execs * 100) if g_execs > 0 else 0
        per_exec_change = ((b_per_exec - g_per_exec) / g_per_exec * 100) if g_per_exec > 0 else 0

        if b_elapsed < 10:
            continue  # Skip negligible SQL

        entry = {
            "sql_id": sid,
            "good_execs": g_execs, "bad_execs": b_execs, "exec_change_pct": exec_change,
            "good_per_exec": g_per_exec, "bad_per_exec": b_per_exec, "per_exec_change_pct": per_exec_change,
            "good_elapsed": g_elapsed, "bad_elapsed": b_elapsed,
            "sql_text": (b.get("sql_text") or g.get("sql_text") or "")[:80],
        }

        if exec_change > 50 and abs(per_exec_change) < 30:
            # Execution count spiked but per-exec time is similar = DATA VOLUME
            volume_driven.append(entry)
        elif per_exec_change > 50 and abs(exec_change) < 30:
            # Per-exec time increased but count is similar = PLAN REGRESSION
            per_exec_regressions.append(entry)
        elif exec_change > 100:
            exec_spikes.append(entry)

    # Report volume-driven changes
    if volume_driven:
        volume_driven.sort(key=lambda x: -x["bad_elapsed"])
        evidence = []
        for v in volume_driven[:5]:
            evidence.append(
                f"{v['sql_id']}: execs {v['good_execs']:,} → {v['bad_execs']:,} ({v['exec_change_pct']:+.0f}%), "
                f"per-exec {v['good_per_exec']:.3f}s → {v['bad_per_exec']:.3f}s (stable) — {v['sql_text'][:50]}"
            )

        insights.append({
            "severity": "warning",
            "title": f"Data Volume Increase Detected ({len(volume_driven)} SQLs)",
            "summary": (
                f"{len(volume_driven)} SQL statements show increased execution counts without per-execution time changes. "
                "This indicates data volume growth, not SQL regression. "
                "The queries themselves are fine — there's simply more data to process."
            ),
            "evidence": evidence,
            "root_cause": (
                "Data volume increased between the two periods. More rows to process means more executions "
                "of the same queries. Check: batch input data size, table row counts, partition growth."
            ),
            "action": (
                "Verify data volume change with: SELECT COUNT(*) and partition stats. "
                "If volume growth is expected, consider partitioning, parallel DML, or batch scheduling changes. "
                "These are NOT SQL tuning candidates — the per-execution time is stable."
            ),
        })

    # Report true plan regressions
    if per_exec_regressions:
        per_exec_regressions.sort(key=lambda x: -x["per_exec_change_pct"])
        evidence = []
        for v in per_exec_regressions[:5]:
            evidence.append(
                f"{v['sql_id']}: per-exec {v['good_per_exec']:.3f}s → {v['bad_per_exec']:.3f}s ({v['per_exec_change_pct']:+.0f}%), "
                f"execs {v['good_execs']:,} → {v['bad_execs']:,} (stable) — {v['sql_text'][:50]}"
            )

        insights.append({
            "severity": "critical",
            "title": f"SQL Plan Regressions ({len(per_exec_regressions)} SQLs)",
            "summary": (
                f"{len(per_exec_regressions)} SQL statements got slower per execution while execution count stayed stable. "
                "This is a true SQL regression — likely caused by plan flips, stale statistics, or index changes."
            ),
            "evidence": evidence,
            "root_cause": (
                "Execution plan changed due to: stale statistics (run DBMS_STATS), "
                "adaptive cursor sharing, index drop/rebuild, or parameter change."
            ),
            "action": (
                "Compare execution plans: SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_AWR(sql_id)). "
                "Lock good plans: EXEC DBMS_SPM.LOAD_PLANS_FROM_AWR. "
                "Gather fresh stats: EXEC DBMS_STATS.GATHER_TABLE_STATS."
            ),
        })

    # Report new SQL offenders
    if new_offenders:
        total_elapsed = sum(s.get("bad_elapsed_secs", 0) for s in new_offenders)
        evidence = []
        for s in new_offenders[:5]:
            sid = s.get("sql_id", "?")
            bad_s = bad_sqls.get(sid, {})
            execs = bad_s.get("executions", s.get("bad_executions", 0))
            evidence.append(f"{sid}: {s.get('bad_elapsed_secs',0):.1f}s, {execs} execs — {s.get('sql_text_truncated','')[:50]}")

        insights.append({
            "severity": "critical" if total_elapsed > 500 else "warning",
            "title": f"{len(new_offenders)} New SQL Statements in Bad Period",
            "summary": (
                f"{len(new_offenders)} SQL IDs appeared only in the bad period, consuming {total_elapsed:.0f}s total. "
                "These are either new application code, ad-hoc queries, or batch jobs that weren't running before."
            ),
            "evidence": evidence,
            "root_cause": "New code deployment, ad-hoc analysis queries, or different batch schedule.",
            "action": (
                "Identify source: SELECT MODULE, ACTION FROM V$SQLAREA WHERE SQL_ID IN (...). "
                "Check if these need indexes or plan optimization. "
                "Verify if these should have been running in this window."
            ),
        })

    # Report execution count spikes (ambiguous — could be volume + some regression)
    if exec_spikes and not volume_driven:
        exec_spikes.sort(key=lambda x: -x["bad_elapsed"])
        evidence = []
        for v in exec_spikes[:5]:
            evidence.append(
                f"{v['sql_id']}: execs {v['good_execs']:,} → {v['bad_execs']:,} ({v['exec_change_pct']:+.0f}%), "
                f"total {v['good_elapsed']:.0f}s → {v['bad_elapsed']:.0f}s"
            )

        insights.append({
            "severity": "warning",
            "title": f"Execution Count Spikes ({len(exec_spikes)} SQLs)",
            "summary": (
                f"{len(exec_spikes)} SQL statements have significantly more executions in the bad period. "
                "Check if data volume increased or if application is calling these more frequently."
            ),
            "evidence": evidence,
            "root_cause": "Data volume increase, application loop changes, or different batch window timing.",
            "action": (
                "Query DBA_HIST_SQLSTAT to see execution counts across snapshots. "
                "Check if all spikes happened in the same time window (batch job concentration). "
                "Compare table row counts between periods."
            ),
        })

    # ── 4. Existing regressions from comparator (for SQL not caught above)
    uncaught_regressions = [r for r in regressions
                           if r.get("sql_id") not in {v["sql_id"] for v in per_exec_regressions}
                           and r.get("sql_id") not in {v["sql_id"] for v in volume_driven}]
    if uncaught_regressions and not per_exec_regressions:
        worst = max(uncaught_regressions, key=lambda s: s.get("delta_pct", 0))
        insights.append({
            "severity": "critical" if len(uncaught_regressions) >= 3 else "warning",
            "title": f"{len(uncaught_regressions)} SQL Elapsed Time Regressions",
            "summary": (
                f"{len(uncaught_regressions)} existing SQL statements got slower. "
                f"Worst: {worst.get('sql_id','?')} regressed {worst.get('delta_pct',0):.0f}%. "
                "Check execution plans and statistics freshness."
            ),
            "evidence": [
                f"{s.get('sql_id','?')}: {s.get('good_elapsed_secs',0):.1f}s → {s.get('bad_elapsed_secs',0):.1f}s ({s.get('delta_pct',0):+.0f}%)"
                for s in uncaught_regressions[:5]
            ],
            "root_cause": "Execution plan changes from stale stats, adaptive cursor sharing, or schema changes.",
            "action": "Check DBA_HIST_SQL_PLAN for plan hash changes. Lock good plans with SQL Plan Baselines.",
        })

    # ── 5. Wait event shifts ─────────────────────────────────────────────
    wait_comps = report.get("top_wait_events", {}).get("comparisons", [])
    new_bottlenecks = [w for w in wait_comps if w.get("classification") == "new_bottleneck"]
    worsening = [w for w in wait_comps if w.get("classification") == "worsening"]

    if new_bottlenecks:
        insights.append({
            "severity": "critical",
            "title": f"{len(new_bottlenecks)} New Wait Event Bottlenecks",
            "summary": f"These wait events appeared only in the bad period — they're entirely new contention points.",
            "evidence": [
                f"{w.get('event_name','?')}: {w.get('bad_time_secs',0):.1f}s ({w.get('bad_pct_db_time',0):.1f}% DB time)"
                for w in new_bottlenecks[:5]
            ],
            "root_cause": "New contention from new SQL, changed concurrency, or infrastructure issues.",
            "action": "Match each new wait event to the SQL or session causing it via ASH data.",
        })

    if worsening:
        insights.append({
            "severity": "warning",
            "title": f"{len(worsening)} Wait Events Worsened",
            "summary": "These wait events existed before but got significantly worse.",
            "evidence": [
                f"{w.get('event_name','?')}: {w.get('good_time_secs',0):.1f}s → {w.get('bad_time_secs',0):.1f}s"
                for w in worsening[:5]
            ],
            "root_cause": "Increased contention or resource pressure in the bad period.",
            "action": "Check if the worsening correlates with the SQL execution count changes identified above.",
        })

    # ── 6. Efficiency degradation ────────────────────────────────────────
    eff_alerts = report.get("instance_efficiency", {}).get("alerts", [])
    if eff_alerts:
        insights.append({
            "severity": "warning",
            "title": f"{len(eff_alerts)} Efficiency Metrics Degraded",
            "summary": "Instance efficiency ratios dropped between periods.",
            "evidence": [a.get("message", "") for a in eff_alerts[:5]],
            "root_cause": "Buffer cache misses, parsing overhead, or latch contention increased.",
            "action": "Address each degraded metric — increase cache, use bind variables, reduce contention.",
        })

    # ── 7. Commit frequency comparison ───────────────────────────────────
    good_commits = _lp_val(good_data, "user commit") or _lp_val(good_data, "commit")
    bad_commits = _lp_val(bad_data, "user commit") or _lp_val(bad_data, "commit")
    good_log_sync = _wait_pct(good_data, "log file sync")
    bad_log_sync = _wait_pct(bad_data, "log file sync")

    if bad_commits > good_commits * 2 and bad_log_sync > 2:
        insights.append({
            "severity": "warning",
            "title": "Commit Frequency Increased",
            "summary": (
                f"Commits/sec: {good_commits:.0f} → {bad_commits:.0f}. "
                f"Log file sync: {good_log_sync:.1f}% → {bad_log_sync:.1f}% of DB time. "
                "More frequent commits are adding overhead."
            ),
            "evidence": [
                f"Commits/sec: {good_commits:.0f} → {bad_commits:.0f}",
                f"Log file sync: {good_log_sync:.1f}% → {bad_log_sync:.1f}%",
            ],
            "root_cause": "Application change or data volume increase causing more transaction commits.",
            "action": "Check if application is committing too frequently. Batch commits where possible.",
        })

    # ── 8. Incident indicators ───────────────────────────────────────────
    incidents = report.get("incident_indicators", [])
    for inc in incidents:
        if inc.get("severity") == "critical":
            insights.append({
                "severity": "critical",
                "title": f"Incident: {inc.get('indicator', 'unknown').replace('_', ' ').title()}",
                "summary": inc.get("description", ""),
                "evidence": [str(inc.get("evidence", {}))],
                "root_cause": inc.get("description", ""),
                "action": inc.get("remediation", ""),
            })

    _sev_order = {"critical": 0, "warning": 1, "info": 2, "good": 3}
    insights.sort(key=lambda x: _sev_order.get(x["severity"], 9))
    return insights
