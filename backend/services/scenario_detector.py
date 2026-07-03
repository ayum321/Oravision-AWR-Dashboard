"""
Scenario Detector — Performance-Architect Pattern Recognition
=============================================================
The AWR comparison tells us *what changed* (a SQL got slower, a wait rose, a
plan flipped). This module adds the *why* — it reads the structural shape of
what the AWR captured and recognises the small set of recurring production
patterns a senior performance engineer would call out by name, then explains
the mechanism that drove the wait/CPU/I/O numbers up.

Design principles
-----------------
- Grounded only in fields the AWR actually captured (SQL text, target table,
  plan-hash change, executions, rows, CPU/I/O, elapsed). No invented numbers.
- Deterministic and auditable — pure rules, no LLM, no embeddings.
- The *mechanism* ("why") is generic Oracle architecture knowledge; the
  *fix* is never invented here — it comes from the expert KB cross-reference
  (kb_digest), so the two stay cleanly separated.
- Honest confidence: a pattern is stated as the most likely structural cause
  to confirm, not as a proven fact, matching the dashboard's confidence tiers.

Each finding:
    {
      "scenario":  machine key,
      "title":     engineer-voice headline,
      "severity":  "critical" | "warning" | "info",
      "sql_id":    str,
      "tables":    [str, ...],
      "evidence":  [str, ...],   # concrete, pulled from the AWR numbers
      "why":       str,          # the architect's mechanism explanation
      "confirm":   str,          # the one thing to verify next
      "kb_tags":   [str, ...],   # used to bias the KB cross-reference
      "kb_match":  {...} | None  # attached later by link_kb()
    }
"""
from __future__ import annotations

import re
from typing import Any

# Tables that are masters/parents in a supply-chain schema tend to carry wide
# child FK fan-out. Used as a *hint* only — the generic high-I/O DELETE path
# below catches masters not on this list.
_MASTER_HINTS = {
    "SKU", "DFU", "ITEM", "ITEMLOC", "LOC", "LOCATION", "TRANSMODE",
    "ORDER", "ORDERLINE", "SHIPMENT", "DELIVERY", "SUPPLYITEM", "DEMAND",
    "PRODUCT", "CUSTOMER", "VEHICLELOAD", "VEHICLELOADLINE", "INVENTORY",
}

_DELETE_RE = re.compile(r"^\s*DELETE\b", re.IGNORECASE)
# Allow an inline optimizer hint / comment between DELETE and FROM, e.g.
#   delete /* SkuStatStaticPurgeHint */ from SKUSTATSTATIC ...
# Without this the deleted table is mis-read as the subquery's driving table.
_DELETE_FROM_RE = re.compile(
    r"\bDELETE\b(?:\s*/\*.*?\*/)*\s+FROM\s+([A-Za-z0-9_$#.]+)", re.IGNORECASE
)
_DBMS_STATS_RE = re.compile(r"\bDBMS_STATS\b|\bGATHER_TABLE_STATS\b|\bGATHER_SCHEMA_STATS\b", re.IGNORECASE)

# Single-block / direct read + redo/undo waits that a heavy DML drives up.
_IO_REDO_WAITS = (
    "db file sequential read", "db file scattered read", "direct path read",
    "direct path write", "db file parallel read", "log file sync",
    "log file parallel write", "free buffer waits", "write complete waits",
)


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _n(v: Any) -> str:
    """Format a number with thousands separators, no trailing .0."""
    f = _f(v)
    return f"{f:,.0f}" if abs(f - round(f)) < 0.05 else f"{f:,.1f}"


def _pct(good: float, bad: float) -> float:
    if good <= 0:
        return 100.0 if bad > 0 else 0.0
    return (bad - good) / good * 100.0


def _sql_text(sr: dict) -> str:
    return str(sr.get("sql_text_full") or sr.get("sql_text_truncated") or "").strip()


def _target_table(sr: dict) -> str:
    m = _DELETE_FROM_RE.search(_sql_text(sr))
    if m:
        return m.group(1).strip().upper()
    refs = sr.get("tables_referenced") or []
    return str(refs[0]).strip().upper() if refs else ""


def _rose_io_waits(report: dict) -> list[str]:
    out: list[str] = []
    comps = (report.get("top_wait_events") or {}).get("comparisons") or []
    for w in comps:
        name = str(w.get("event_name", "")).strip().lower()
        if not name:
            continue
        if any(k in name for k in _IO_REDO_WAITS):
            if _f(w.get("bad_time_secs")) > _f(w.get("good_time_secs")):
                out.append(str(w.get("event_name")))
    return out


def _latency_spike(report: dict) -> list[dict]:
    """Generic per-wait LATENCY regression probe \u2014 independent of volume/share.

    Total wait time = occurrences x avg latency, so an event whose per-wait
    latency blows up but whose occurrence count is low stays small in both
    %DB-time and absolute total-time terms, and the volume-based classifier
    silently buckets it as "stable". This rule reads the avg-latency delta
    directly (good_avg_wait_ms -> bad_avg_wait_ms) so a huge or newly-appeared
    latency is never missed just because it hasn't accumulated volume yet.
    Fires for ANY wait event \u2014 no event name is hardcoded.
    """
    findings: list[dict] = []
    comps = (report.get("top_wait_events") or {}).get("comparisons") or []
    for w in comps:
        good_ms = _f(w.get("good_avg_wait_ms"))
        bad_ms = _f(w.get("bad_avg_wait_ms"))
        if bad_ms <= 0:
            continue
        is_new = good_ms <= 0
        delta_pct = _f(w.get("latency_delta_pct"))
        # Material thresholds: relative jump on an already-nontrivial latency,
        # OR an already-huge absolute latency (>=1s/wait) that still grew, OR
        # a brand-new event whose latency alone is already high.
        material = (
            (delta_pct >= 50.0 and bad_ms >= 20.0)
            or (bad_ms >= 1000.0 and good_ms > 0 and bad_ms > good_ms * 1.1)
            or (is_new and bad_ms >= 50.0)
        )
        if not material:
            continue
        name = str(w.get("event_name", "")).strip()
        findings.append({
            "scenario": "latency_spike",
            "title": (
                f"{name}: per-wait latency {'appeared new at' if is_new else 'grew to'} "
                f"{_n(bad_ms)}ms" + ("" if is_new else f" (from {_n(good_ms)}ms, {delta_pct:+.0f}%)")
            ),
            "severity": "critical" if bad_ms >= 500.0 else "warning",
            "sql_id": "",
            "tables": [],
            "evidence": [
                (
                    f"Avg latency per wait: {_n(good_ms)}ms \u2192 {_n(bad_ms)}ms"
                    + (" (new event)" if is_new else f" ({delta_pct:+.0f}%)")
                ),
                f"Share of DB time: {_f(w.get('good_pct_db_time')):.1f}% \u2192 {_f(w.get('bad_pct_db_time')):.1f}%",
                f"Wait class: {w.get('wait_class', '')}",
            ],
            "why": (
                "The volume of this wait (occurrence count / share of DB time) can look "
                "unchanged or even small, but each individual occurrence is taking far "
                "longer to clear \u2014 a classic sign of a degrading resource (a storage "
                "device slowing down, a lock being held longer, a queue backing up) "
                "rather than more work being submitted. Volume-based thresholds miss "
                "this because total time = occurrences x latency, and a latency blowup "
                "on a low-occurrence event still stays small in aggregate even though "
                "every session that hits it now pays the higher cost."
            ),
            "confirm": (
                "Check the underlying resource for this wait class directly (storage "
                "device latency for I/O waits, blocking session hold time for locks/"
                "enqueues) \u2014 aggregate share/total-time understate this signal."
            ),
            "kb_tags": ["latency", "per-wait", "storage", "contention"],
            "kb_match": None,
        })
    return findings


def _dirty_buffer_write_pressure(report: dict) -> list[dict]:
    """Generic root-cause DISAMBIGUATION: DBWR write-throughput pressure vs an
    undersized buffer cache.

    "free buffer waits" alone is ambiguous: it can mean the cache is too small
    (few clean buffers exist to begin with) OR that DBWR simply cannot drain
    dirty buffers fast enough (cache is fine, write throughput is the limit).
    These have OPPOSITE fixes: increasing db_cache_size actually makes write
    pressure worse (more dirty buffers to drain), while it's the correct fix
    for a genuinely undersized cache.

    This probe reads three independently-computed, already-parsed AWR facts
    and only fires when ALL three agree that it's a WRITE-THROUGHPUT problem,
    not a sizing problem:
      (a) free buffer waits dominate DB time (>=50%) in the bad period,
      (b) buffer cache hit ratio is already excellent (>=95%) \u2014 the cache
          itself is not missing, ruling out "just add more cache",
      (c) DBWR is demonstrably saturated: it had to inspect several dirty
          buffers for every one it could actually flush (ratio >= 2x).
    No table/SQL/event name is hardcoded \u2014 this is a pure metric join.
    """
    findings: list[dict] = []
    comps = (report.get("top_wait_events") or {}).get("comparisons") or []
    fbw = next((w for w in comps if str(w.get("event_name", "")).strip().lower() == "free buffer waits"), None)
    if not fbw:
        return findings
    free_buf_pct = _f(fbw.get("bad_pct_db_time"))
    if free_buf_pct < 50.0:
        return findings

    eff_comps = (report.get("instance_efficiency") or {}).get("comparisons") or []
    hit_row = next((e for e in eff_comps if e.get("metric") == "buffer_cache_hit_pct"), None)
    buffer_hit_bad = _f(hit_row.get("bad_val")) if hit_row else 0.0
    if buffer_hit_bad < 95.0:
        return findings

    dbwr = report.get("dbwr_activity") or {}
    ratio_bad = _f(dbwr.get("dirty_to_written_ratio_bad"))
    dirty_stat = (dbwr.get("stats") or {}).get("dirty_buffers_inspected") or {}
    written_stat = (dbwr.get("stats") or {}).get("dbwr_checkpoint_written") or {}
    if ratio_bad < 2.0:
        return findings

    findings.append({
        "scenario": "dirty_buffer_write_pressure",
        "title": (
            f"Free buffer waits ({_n(free_buf_pct)}% DB time) are DBWR write pressure, "
            f"not an undersized cache \u2014 buffer hit is {_n(buffer_hit_bad)}%"
        ),
        "severity": "critical",
        "sql_id": "",
        "tables": [],
        "evidence": [
            f"free buffer waits: {_n(free_buf_pct)}% of DB time in the bad period",
            f"Buffer cache hit ratio: {_n(buffer_hit_bad)}% (>=95% \u2014 the cache is not missing)",
            (
                f"DBWR saturation ratio: {_n(dirty_stat.get('bad_total', 0))} dirty buffers inspected vs "
                f"{_n(written_stat.get('bad_total', 0))} actually written = {ratio_bad:.2f}x \u2014 DBWR scanned "
                f"~{ratio_bad:.1f} dirty buffers for every one it could flush"
            ),
        ],
        "why": (
            "These three facts together rule out 'cache too small': if the cache were undersized, "
            "the buffer hit ratio would be visibly degraded, not sitting above 95%. Instead, DBWR "
            "itself cannot drain dirty buffers as fast as the workload is creating them \u2014 the "
            "saturation ratio shows it scanning multiple dirty buffers for every one it manages to "
            "write. Growing db_cache_size would make this WORSE, not better: a bigger cache holds "
            "more dirty buffers, giving DBWR an even larger backlog to drain at the same throughput. "
            "The real levers are workload-side: reduce the rate dirty buffers are generated "
            "(lower PARALLEL degree on the driving DML, batch commits instead of one giant "
            "transaction) or raise DBWR's own throughput (db_writer_processes, faster storage, "
            "confirm DISK_ASYNCH_IO is enabled)."
        ),
        "confirm": (
            "Check V$DB_CACHE_ADVICE \u2014 confirm estd_physical_read_factor does NOT improve at a "
            "larger cache size (it won't, since misses aren't the problem). Then check the PARALLEL "
            "degree and commit frequency of the top DML driving dirty buffers, and DBWR's own I/O "
            "latency (db file parallel write) to see if storage or process count is the throughput limit."
        ),
        "kb_tags": ["dbwr", "free_buffer_waits", "write_pressure", "buffer_cache"],
        "kb_match": None,
    })
    return findings


# ── individual probes ────────────────────────────────────────────────────────

def _cascading_delete(report: dict) -> list[dict]:
    findings: list[dict] = []
    io_waits = _rose_io_waits(report)
    for sr in (report.get("sql_regressions") or []):
        text = _sql_text(sr)
        if not _DELETE_RE.match(text):
            continue
        bad_el = _f(sr.get("bad_elapsed_secs"))
        good_el = _f(sr.get("good_elapsed_secs"))
        tag = str(sr.get("tag", "")).lower()
        # A DELETE worth flagging: it's a real regression or a heavyweight.
        is_heavy = bad_el >= 120 or tag in ("new_offender", "regression", "load_increase")
        if not is_heavy:
            continue
        table = _target_table(sr)
        short = table.split(".")[-1]
        is_master = short in _MASTER_HINTS
        bad_dr = _f(sr.get("bad_disk_reads"))
        good_dr = _f(sr.get("good_disk_reads"))
        bad_rows = _f(sr.get("bad_rows_processed"))
        # Heavy I/O-per-row is the FK-cascade fingerprint AWR can see.
        io_per_row = (bad_dr / bad_rows) if bad_rows > 0 else bad_dr
        fk_signature = is_master or io_per_row >= 50 or bad_dr >= 1_000_000

        if not fk_signature:
            continue

        evidence = [
            f"Statement is a DELETE on {table or 'a target table'}"
            + (f" (master/parent table)" if is_master else ""),
            f"Elapsed {_n(good_el)}s → {_n(bad_el)}s ({_pct(good_el, bad_el):+.0f}%)",
        ]
        if bad_dr > good_dr:
            evidence.append(f"Disk reads {_n(good_dr)} → {_n(bad_dr)} ({_pct(good_dr, bad_dr):+.0f}%)")
        if bad_rows:
            evidence.append(f"{_n(bad_rows)} rows removed ≈ {_n(io_per_row)} block reads/row")
        if not bool(sr.get("plan_changed")):
            evidence.append("Plan hash unchanged — this is structural work, not a plan flip")
        if io_waits:
            evidence.append("Rising I/O/redo waits: " + ", ".join(io_waits[:3]))

        why = (
            (f"A DELETE of this size against a master/parent table is rarely a plan problem. "
             if is_master else
             f"A DELETE that drives this much block I/O is rarely a plan problem. ")
            + f"For every row removed Oracle must resolve each foreign-key relationship to the "
            f"child tables — cascading the delete where ON DELETE CASCADE is defined, or scanning "
            f"the child segments to prove there are no orphans where it is not. Both paths read "
            f"child tables and their indexes block-by-block and generate large volumes of undo and "
            f"redo. That is what pushes single-block read I/O, CPU and log/redo waits up while the "
            f"plan stays the same. The cost scales with the number of child tables and the rows "
            f"being deleted, not with the master row count alone."
        )
        findings.append({
            "scenario": "cascading_delete",
            "title": (f"Long-running DELETE on master table {table}" if (table and is_master)
                      else f"Long-running DELETE on {table} (heavy child-table I/O)" if table
                      else "Long-running DELETE with heavy child I/O"),
            "severity": "critical" if bad_el >= 600 else "warning",
            "sql_id": str(sr.get("sql_id", "")),
            "tables": [table] if table else (sr.get("tables_referenced") or []),
            "evidence": evidence,
            "why": why,
            "confirm": (
                f"Map the child foreign keys on {short or 'the target table'} "
                f"(parent→child fan-out) before tuning the statement — the dependency "
                f"depth, not the statement text, governs the runtime."
            ),
            "kb_tags": ["delete", "cascade", "master-child", "foreign-key"],
            "kb_match": None,
        })
    return findings


def _concurrent_maintenance(report: dict) -> list[dict]:
    findings: list[dict] = []
    # Maintenance SQL that ran heavy in the bad window.
    maint = []
    for sr in (report.get("sql_maintenance") or report.get("sql_regressions") or []):
        text = _sql_text(sr)
        is_maint = bool(sr.get("is_oracle_maintenance")) or _DBMS_STATS_RE.search(text)
        if is_maint and _f(sr.get("bad_elapsed_secs")) >= 120:
            maint.append(sr)
    if not maint:
        return findings

    # Application SQL that slowed WITHOUT a plan change = contention victim.
    victims = []
    for sr in (report.get("sql_regressions") or []):
        if bool(sr.get("is_oracle_maintenance")):
            continue
        if bool(sr.get("plan_changed")):
            continue
        tag = str(sr.get("tag", "")).lower()
        if tag in ("regression", "load_increase", "new_offender") or \
           _f(sr.get("avg_elapsed_delta_pct")) >= 20:
            victims.append(sr)
    if not victims:
        return findings

    m0 = maint[0]
    mname = _target_table(m0) or (m0.get("tables_referenced") or [""])[0] or "a statistics job"
    victim_ids = ", ".join(v.get("sql_id", "") for v in victims[:4] if v.get("sql_id"))
    evidence = [
        f"Maintenance SQL {m0.get('sql_id','')} ran {_n(m0.get('bad_elapsed_secs'))}s in the bad window"
        + (f" on {mname}" if mname else ""),
        f"{len(victims)} application SQL slowed with NO plan change: {victim_ids}",
    ]
    io_waits = _rose_io_waits(report)
    if io_waits:
        evidence.append("Concurrent I/O pressure: " + ", ".join(io_waits[:3]))

    why = (
        "The application SQL did not change plan — its elapsed time rose because a "
        "statistics/maintenance job was running inside the same window. A parallel "
        "DBMS_STATS gather (high DOP) competes with the live batch for CPU and I/O "
        "bandwidth and can transiently invalidate cursors, so the foreground SQL waits "
        "longer to do identical work. In AWR this looks like elapsed-time inflation with "
        "an unchanged plan and elevated I/O — a scheduling collision, not a SQL regression. "
        "Deleting a table's stats immediately before the gather makes it worse: if the "
        "gather fails the table is left with no stats at all."
    )
    findings.append({
        "scenario": "concurrent_maintenance",
        "title": "Statistics/maintenance job colliding with the live batch",
        "severity": "warning",
        "sql_id": str(m0.get("sql_id", "")),
        "tables": [mname] if mname else [],
        "evidence": evidence,
        "why": why,
        "confirm": (
            "Check the gather-stats schedule against the batch window — gather AFTER the "
            "load completes, not in parallel with it, and avoid an explicit delete-stats "
            "before the gather."
        ),
        "kb_tags": ["stats", "gather", "parallel", "maintenance", "concurrency"],
        "kb_match": None,
    })
    return findings


def _plan_flip(report: dict) -> list[dict]:
    findings: list[dict] = []
    for sr in (report.get("sql_regressions") or []):
        if not bool(sr.get("plan_changed")):
            continue
        good_avg = _f(sr.get("good_avg_elapsed"))
        bad_avg = _f(sr.get("bad_avg_elapsed"))
        if bad_avg <= good_avg or bad_avg < good_avg * 1.2:
            continue  # plan changed but per-exec time did not worsen
        gph, bph = str(sr.get("good_plan_hash", "")), str(sr.get("bad_plan_hash", ""))
        findings.append({
            "scenario": "plan_flip",
            "title": f"Execution-plan flip on {sr.get('sql_id','')}",
            "severity": "critical" if bad_avg >= good_avg * 2 else "warning",
            "sql_id": str(sr.get("sql_id", "")),
            "tables": sr.get("tables_referenced") or [],
            "evidence": [
                f"Plan hash {gph} → {bph}",
                f"Avg elapsed/exec {_n(good_avg)}s → {_n(bad_avg)}s ({_pct(good_avg, bad_avg):+.0f}%)",
                f"Executions {_n(sr.get('good_executions'))} → {_n(sr.get('bad_executions'))}",
            ],
            "why": (
                "Per-execution time rose together with a changed plan hash — the optimizer "
                "picked a different access path (commonly a nested-loop/index plan flipping to "
                "a hash/full-scan or vice-versa after a stats change or bind-peek). The data "
                "volume is steady; the plan is the regression. Pinning the known-good plan hash "
                "restores the prior runtime."
            ),
            "confirm": "Compare the two plans and pin the known-good plan hash via SQL plan baseline.",
            "kb_tags": ["plan", "plan-change", "pin", "baseline"],
            "kb_match": None,
        })
    return findings


def _volume_growth(report: dict) -> list[dict]:
    findings: list[dict] = []
    for sr in (report.get("sql_regressions") or []):
        if bool(sr.get("plan_changed")):
            continue
        good_rpe = _f(sr.get("good_rows_per_exec"))
        bad_rpe = _f(sr.get("bad_rows_per_exec"))
        good_el = _f(sr.get("good_elapsed_secs"))
        bad_el = _f(sr.get("bad_elapsed_secs"))
        # Rows-per-exec (or executions) up materially, elapsed tracks it, plan steady.
        rows_up = bad_rpe >= good_rpe * 1.25 and good_rpe > 0
        if not (rows_up and bad_el > good_el and bad_el >= 120):
            continue
        findings.append({
            "scenario": "data_volume_growth",
            "title": f"Data-volume growth on {sr.get('sql_id','')} (not a plan regression)",
            "severity": "info",
            "sql_id": str(sr.get("sql_id", "")),
            "tables": sr.get("tables_referenced") or [],
            "evidence": [
                f"Rows/exec {_n(good_rpe)} → {_n(bad_rpe)} ({_pct(good_rpe, bad_rpe):+.0f}%)",
                f"Elapsed {_n(good_el)}s → {_n(bad_el)}s ({_pct(good_el, bad_el):+.0f}%)",
                "Plan hash unchanged",
            ],
            "why": (
                "The plan is unchanged and per-row cost is steady — the statement is simply "
                "processing more data this run. Elapsed time grew in proportion to the rows/"
                "executions, so this is workload growth, not a SQL regression. The lever is the "
                "data volume (archiving, partition pruning, an index to cut the rows touched), "
                "not the plan."
            ),
            "confirm": "Confirm the upstream data growth and whether an index can reduce rows touched.",
            "kb_tags": ["volume", "growth", "index"],
            "kb_match": None,
        })
    return findings


def _library_cache_hard_parse_thrash(report: dict) -> list[dict]:
    """Generic hard-parse / no-bind-variable pressure probe.

    A main cause of shared pool and library cache latch contention is parsing
    (Oracle Performance Tuning Guide, "Identifying Unnecessary Parsing").
    Statements that cannot share an existing SQL area — most often literal
    values used instead of bind variables — force a hard parse on every
    execution. That hard-parse load shows up as BOTH a falling soft-parse
    ratio and a falling library cache hit ratio at the same time; requiring
    both to degrade together (not just one drifting alone) rules out an
    isolated one-off blip in either metric.
    """
    findings: list[dict] = []
    eff_comps = (report.get("instance_efficiency") or {}).get("comparisons") or []
    soft_row = next((e for e in eff_comps if e.get("metric") == "soft_parse_pct"), None)
    lib_row = next((e for e in eff_comps if e.get("metric") == "library_cache_hit_pct"), None)
    if not soft_row or not lib_row:
        return findings
    soft_bad = _f(soft_row.get("bad_val"))
    soft_good = _f(soft_row.get("good_val"))
    lib_bad = _f(lib_row.get("bad_val"))
    lib_good = _f(lib_row.get("good_val"))
    if not (soft_bad < 90.0 and lib_bad < 95.0):
        return findings
    if not (soft_bad < soft_good - 2.0 or lib_bad < lib_good - 2.0):
        return findings
    findings.append({
        "scenario": "hard_parse_thrash",
        "title": f"Hard-parse / shared-pool thrash — soft parse {_n(soft_bad)}%, library cache hit {_n(lib_bad)}%",
        "severity": "critical" if (soft_bad < 80.0 or lib_bad < 90.0) else "warning",
        "sql_id": "",
        "tables": [],
        "evidence": [
            f"Soft parse %: {_n(soft_good)}% → {_n(soft_bad)}%",
            f"Library cache hit %: {_n(lib_good)}% → {_n(lib_bad)}%",
        ],
        "why": (
            "Soft-parse ratio and library cache hit ratio degrading TOGETHER is the signature "
            "of hard-parse thrash: statements that cannot share an existing SQL area (most often "
            "literal values instead of bind variables, or a CURSOR_SHARING mismatch) force a full "
            "hard parse on every execution. A main cause of shared pool / library cache latch "
            "contention is exactly this repeated parsing — it burns CPU on parsing work and holds "
            "the library cache latch longer, which is why both ratios move together rather than "
            "just one drifting on its own."
        ),
        "confirm": (
            "Check V$SQLAREA / V$SQL for statements with a high version_count or a very low "
            "executions-per-parse ratio and literal (non-bound) predicates. If the application "
            "cannot bind, CURSOR_SHARING=FORCE is a stop-gap, not a permanent fix — the real fix "
            "is binding variables at the application layer."
        ),
        "kb_tags": ["parse", "shared_pool", "library_cache", "cursor_sharing", "latch"],
        "kb_match": None,
    })
    return findings


def _latch_wait_amplification(report: dict) -> list[dict]:
    """Generic latch-contention probe: a named 'latch: ...' wait event rising
    alongside a degraded latch hit ratio.

    Latches protect in-memory structures (shared pool, library cache) with a
    spin-then-sleep strategy — a session that cannot immediately acquire a
    latch first spins on CPU, and only posts a 'latch: X' wait once it gives
    up spinning and sleeps. So a rising 'latch: ...' wait time alongside a
    falling latch hit ratio means real contention, not just background spin
    noise silently absorbed as CPU.
    """
    findings: list[dict] = []
    eff_comps = (report.get("instance_efficiency") or {}).get("comparisons") or []
    latch_row = next((e for e in eff_comps if e.get("metric") == "latch_hit_pct"), None)
    if not latch_row:
        return findings
    latch_bad = _f(latch_row.get("bad_val"))
    latch_good = _f(latch_row.get("good_val"))
    if latch_bad >= 99.0:
        return findings
    comps = (report.get("top_wait_events") or {}).get("comparisons") or []
    latch_waits = [w for w in comps if str(w.get("event_name", "")).strip().lower().startswith("latch:")]
    risen = [
        w for w in latch_waits
        if _f(w.get("bad_time_secs")) > _f(w.get("good_time_secs")) and _f(w.get("bad_pct_db_time")) >= 2.0
    ]
    if not risen:
        return findings
    top = max(risen, key=lambda w: _f(w.get("bad_pct_db_time")))
    findings.append({
        "scenario": "latch_contention",
        "title": f"{top.get('event_name','')} rising with latch hit ratio down to {_n(latch_bad)}%",
        "severity": "critical" if latch_bad < 95.0 else "warning",
        "sql_id": "",
        "tables": [],
        "evidence": [
            f"Latch hit ratio: {_n(latch_good)}% → {_n(latch_bad)}%",
            f"{top.get('event_name','')}: {_n(_f(top.get('good_time_secs')))}s → "
            f"{_n(_f(top.get('bad_time_secs')))}s ({_n(_f(top.get('bad_pct_db_time')))}% of DB time)",
        ],
        "why": (
            "Latches use a spin-then-sleep strategy — a session that cannot immediately "
            "acquire a latch spins on CPU first, and only records a 'latch: ...' wait once it "
            "gives up spinning and sleeps. Seeing the named latch wait actually rise in the AWR "
            "(not just absorbed as background CPU) together with a falling latch hit ratio means "
            "the contention is heavy enough to push sessions into real sleeps, not just spin noise. "
            "This is almost always driven by many sessions concurrently hammering the same "
            "in-memory structure — very often the same hard-parse thrash on non-shared SQL text "
            "contending for the library cache / shared pool latch."
        ),
        "confirm": (
            "Check V$LATCH / V$LATCHHOLDER for the specific latch name during the problem window, "
            "and cross-reference against parse activity — latch contention is very often a "
            "symptom of hard-parse thrash rather than an independent cause."
        ),
        "kb_tags": ["latch", "contention", "cpu", "shared_pool"],
        "kb_match": None,
    })
    return findings


# NOTE: a "log file switch (checkpoint incomplete)" probe was deliberately NOT
# added here — comparator.py's _detect_incidents() already has a more mature
# "Log Switch / Redo File Undersizing" check (broader event match + redo-size
# correlation). That check's real problem was that it (and 14 siblings) were
# computed but never rendered anywhere in the UI — fixed by wiring
# incident_indicators into renderScenarioIntel() in index.html instead of
# duplicating the check here.


# ── public API ───────────────────────────────────────────────────────────────

_SEV_RANK = {"critical": 0, "warning": 1, "info": 2}

# Matches PARALLEL(16), PARALLEL (16), and PARALLEL(table_alias, 16) hint forms.
# Fallback only — comparator.py already computes parallel_degree per SQL; this
# regex is used solely when an older cached report lacks that field.
_PARALLEL_HINT_RE = re.compile(r"PARALLEL\s*\(\s*(?:[A-Za-z0-9_$#.\"]+\s*,\s*)?(\d+)\s*\)", re.IGNORECASE)


def _parallel_degree_of(sr: dict) -> int:
    deg = sr.get("parallel_degree")
    if isinstance(deg, (int, float)) and deg:
        return int(deg)
    m = _PARALLEL_HINT_RE.search(_sql_text(sr))
    return int(m.group(1)) if m else 0


def _parallel_oversubscription(report: dict, cpu_count: int) -> list[dict]:
    """Generic PARALLEL(N)-vs-CPU-count oversubscription probe.

    Any SQL statement requesting a parallel degree greater than the host's
    CPU count forces its slaves to queue for CPU and, for a DML statement,
    generates dirty buffers faster than DBWR can flush them \u2014 the classic
    mechanism behind free buffer waits and the checkpoint-forcing enqueues
    (enq: KO / enq: CR) that follow. This rule is purely "requested degree
    vs available CPUs" \u2014 it never references a specific SQL_ID, table, or
    incident; it fires for ANY future AWR pair where the pattern occurs.
    """
    findings: list[dict] = []
    if not cpu_count or cpu_count <= 0:
        return findings
    for sr in (report.get("sql_regressions") or []):
        degree = _parallel_degree_of(sr)
        if degree <= cpu_count:
            continue
        ratio = degree / cpu_count
        bad_elapsed = _f(sr.get("bad_elapsed_secs"))
        is_dml = bool(sr.get("is_dml"))
        # DML oversubscription is critical at ANY degree above CPU count — even a
        # modest 2-worker overshoot (e.g. 16 vs 14 CPUs) is enough to outpace DBWR
        # when the statement is also generating heavy dirty-buffer volume. A
        # read-only (SELECT) oversubscription is a lesser concern unless severe.
        if is_dml:
            severity = "critical"
        elif ratio >= 2.0:
            severity = "critical"
        else:
            severity = "warning"
        findings.append({
            "scenario": "parallel_oversubscription",
            "title": f"PARALLEL({degree}) exceeds host CPU count ({cpu_count}) on {sr.get('sql_id', '')}",
            "severity": severity,
            "sql_id": str(sr.get("sql_id", "")),
            "tables": sr.get("tables_referenced") or [],
            "evidence": [
                f"Requested PARALLEL degree {degree} vs {cpu_count} CPUs on the host ({ratio:.1f}x oversubscribed)",
                f"Bad-period elapsed {_n(bad_elapsed)}s across {_n(sr.get('bad_executions'))} execution(s)",
                "Statement type: " + ("DML (writes dirty buffers)" if is_dml else "read-only (SELECT)"),
            ],
            "why": (
                "Requesting more parallel server processes than the host has CPUs means the "
                "parallel slaves queue for CPU and, for a DML statement, generate dirty buffers "
                "faster than DBWR can flush them \u2014 the classic driver behind free buffer waits "
                "and the checkpoint-forcing enqueues (enq: KO \u2014 fast object checkpoint, "
                "enq: CR \u2014 block range reuse ckpt) that follow. The oversubscription itself, "
                "not the SQL logic, is the mechanism."
            ) if is_dml else (
                "Requesting more parallel server processes than the host has CPUs causes the "
                "slaves to queue for CPU, extending elapsed time and starving other concurrent "
                "work of CPU capacity, even though this statement is read-only."
            ),
            "confirm": (
                f"Reduce PARALLEL degree to at or below {cpu_count} (or use PARALLEL AUTO / DOP "
                "capped by the resource manager); for DML, also batch into smaller committed chunks."
            ),
            "kb_tags": ["parallel", "oversubscription", "dbwr", "checkpoint", "cpu"],
            "kb_match": None,
        })
    return findings


def detect(report: dict, cpu_count: int = 0) -> list[dict]:
    """Return the list of recognised performance-architect scenarios for a report.
    Failure-proof: never raises, returns [] on any problem.

    cpu_count (optional): raw host CPU count from the bad period's AWRData,
    used only by generic resource-ceiling-vs-demand probes (e.g. PARALLEL
    oversubscription). Callers that omit it simply skip those probes.
    """
    try:
        findings: list[dict] = []
        findings += _cascading_delete(report or {})
        findings += _concurrent_maintenance(report or {})
        findings += _plan_flip(report or {})
        findings += _volume_growth(report or {})
        findings += _parallel_oversubscription(report or {}, cpu_count)
        findings += _latency_spike(report or {})
        findings += _dirty_buffer_write_pressure(report or {})
        findings += _library_cache_hard_parse_thrash(report or {})
        findings += _latch_wait_amplification(report or {})
        findings.sort(key=lambda f: _SEV_RANK.get(f.get("severity", "info"), 3))
        return findings
    except Exception:  # noqa: BLE001 — the dashboard must never break on this
        return []


# Only borrow a recommended fix from a prior incident when the pattern match is
# strong (>= 80% similarity). A weaker overlap stays an in-house architect call.
_MIN_REFERENCE_CONFIDENCE = 0.80


def link_kb(findings: list[dict], kb_crossref: dict) -> list[dict]:
    """Fold a prior expert fix into a scenario's recommended action — but only
    when the match is strong (>= 80%). The past incident is never displayed as a
    standalone card; it silently sharpens the recommended fix.

    A reference is taken when the finding and an incident share a SQL_ID (an
    identity match on the statement) or when the incident's overall similarity
    (kb_digest confidence) clears the 80% bar AND the scenario tags overlap.
    """
    try:
        matches = (kb_crossref or {}).get("matches") or []
        if not matches:
            return findings
        for fnd in findings:
            sid = str(fnd.get("sql_id", "")).lower()
            tags = {t.lower() for t in (fnd.get("kb_tags") or [])}
            best, best_conf = None, 0.0
            for m in matches:
                matched_on = " ".join(str(x).lower() for x in (m.get("matched_on") or []))
                inc_tags = {str(t).lower() for t in (m.get("tags") or [])}
                conf = float(m.get("confidence", 0.0) or 0.0)
                sql_hit = bool(sid and sid in matched_on)
                # SQL_ID identity counts as a full match; otherwise require the
                # KB similarity to clear 80% and the scenario tags to overlap.
                if sql_hit:
                    conf = max(conf, 1.0)
                elif not (conf >= _MIN_REFERENCE_CONFIDENCE and (tags & inc_tags)):
                    continue
                if conf > best_conf:
                    best, best_conf = m, conf
            if best and best_conf >= _MIN_REFERENCE_CONFIDENCE:
                fix = str(best.get("fix", "")).strip()
                if fix:
                    fnd["recommended_fix"] = fix
                fnd["reference_confidence"] = round(best_conf, 3)
                fnd["kb_match"] = {
                    "root_cause": best.get("root_cause", ""),
                    "fix": fix,
                    "confidence": round(best_conf, 3),
                }
        return findings
    except Exception:  # noqa: BLE001
        return findings
