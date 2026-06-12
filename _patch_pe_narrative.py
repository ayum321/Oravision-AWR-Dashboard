"""
PE Narrative patch — 6 targeted fixes.

FIX H (CRITICAL): domSql.cpuPct is ALWAYS undefined/null in the narrative
  The sqlAtt array built in generateComparisonVerdictNarrative does NOT include
  cpuPct, rowsPerExec, rowsPerExec1, diskReads, diskReads1.
  - Part2: cpuFrac = null, highCpuSql = false always →
    CARDINALITY/LOGICAL-IO path (part2 + part4) NEVER fires.
  - rows/exec delta completely absent — key PE signal for data volume change.
  - SQL-specific disk reads not available — falls back to system-wide LP delta.
  Fix: add all missing fields to sqlAtt.

FIX I (HIGH): physReadSpike uses system-wide load profile, not SQL-specific reads.
  (lp2.physical_reads||0) > (lp1.physical_reads||0) * 2 fires when TOTAL physical
  reads doubled — but the dominant SQL's reads could spike while others improved.
  Conversely, if the SQL drives most reads and they doubled, but other SQLs also
  improved, the LP delta may be flat even though the SQL's reads exploded.
  Fix: use domSql.diskReads vs domSql.diskReads1 (SQL-specific), fall back to
  LP delta only when SQL disk reads are low (<= 1000).

FIX J (HIGH): No gets/row cardinality check.
  buffer_gets/rows_per_exec > 500 is the canonical Oracle cardinality-underestimate
  indicator. It fires even when cpuPct is unavailable. The CARDINALITY path was
  previously gated only on highCpuSql (always false due to Fix H). With this fix,
  the gets/row ratio independently routes to the cardinality path.
  Also: contentionPath must exclude highGetsPerRow (high gets/row is not contention).

FIX K (MEDIUM): No rows/exec delta annotation in part2 SQL narrative.
  After part2 root cause text is assembled, append:
  (a) rows/exec delta note when rowsPerExec increased >= 2x — signals data volume
      growth or selectivity change.
  (b) gets/row ratio note when > 500 — confirms cardinality underestimate.
  Both notes are diagnostic context, not action steps.

FIX L (MEDIUM): Part3 overconfidence at >= 40% SQL share.
  "resolving this single statement will directly restore baseline performance
  without any other changes required" — factually incorrect when contributing
  verdicts or secondary SQL share > 5%.
  Fix: soften to "will directly resolve the dominant cost driver" with a conditional
  caveat when secondary contributors are present.

FIX M (LOW): "uncommitted redo entries" — technically incorrect Oracle terminology.
  LGWR writes ALL outstanding redo in the log buffer up to the commit SCN, not just
  "uncommitted" redo. The redo is for a transaction that is IN THE ACT of committing
  — calling it "uncommitted" is the wrong state. Standard Oracle terminology:
  "outstanding redo entries" or "pending redo up to the commit SCN".
"""

import re

PATH = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'
f = open(PATH, encoding='utf-8')
c = f.read()
f.close()

# ── FIX H ── Enrich sqlAtt with cpuPct, rowsPerExec, diskReads etc. ───────────
OLD_H = """\
        const gets = s2x.buffer_gets_per_exec||s2x.buffer_gets||0;
        const execs = s2x.executions||0;
        sqlAtt.push({id:s2x.sql_id,epe1,epe2,isNew,isPlanChg,pctDb,gets,execs,
            module:s2x.module||'',table_name:s2x.table_name||'',
            plan_hash_v2:s2x.plan_hash_value||'',plan_hash_v1:s1x?.plan_hash_value||''});"""

NEW_H = """\
        const gets = s2x.buffer_gets_per_exec||s2x.buffer_gets||0;
        const execs = s2x.executions||0;
        // cpuPct: fraction of elapsed that is CPU (critical for decision-tree routing)
        // null = data absent; 0 = all wait; 100 = all CPU
        const cpuPct = (s2x.elapsed_time_secs||0) > 0.001
            ? ((s2x.cpu_time_secs||0) / (s2x.elapsed_time_secs||1) * 100) : null;
        // rowsPerExec: data volume per call — delta signals selectivity/volume change
        const rowsPerExec  = execs > 0 && (s2x.rows_processed||0) > 0
            ? (s2x.rows_processed / execs) : null;
        const rowsPerExec1 = s1x && (s1x.executions||0) > 0 && (s1x.rows_processed||0) > 0
            ? (s1x.rows_processed / s1x.executions) : null;
        // diskReads: SQL-specific physical reads — more targeted than LP-wide delta
        const diskReads  = s2x.disk_reads  || 0;
        const diskReads1 = s1x ? (s1x.disk_reads||0) : null;
        // getsIsPerExec: true when buffer_gets_per_exec is the source (enables gets/row ratio)
        const getsIsPerExec = (s2x.buffer_gets_per_exec||0) > 0;
        sqlAtt.push({id:s2x.sql_id,epe1,epe2,isNew,isPlanChg,pctDb,gets,execs,
            module:s2x.module||'',table_name:s2x.table_name||'',
            plan_hash_v2:s2x.plan_hash_value||'',plan_hash_v1:s1x?.plan_hash_value||'',
            cpuPct, rowsPerExec, rowsPerExec1, diskReads, diskReads1, getsIsPerExec});"""

assert c.count(OLD_H) == 1, f"FIX H: {c.count(OLD_H)} matches"
c = c.replace(OLD_H, NEW_H)
print("FIX H applied")

# ── FIX I + J ── Rewrite part2 decision tree inputs ──────────────────────────
# Fixes: physReadSpike → SQL-specific; add getsPerRow/highGetsPerRow;
#        update contentionPath to exclude highGetsPerRow
OLD_IJ = """\
        const epeRatio      = domSql.epe1 > 0 ? domSql.epe2 / domSql.epe1 : 0;
        const cpuFrac       = (domSql.cpuPct != null) ? domSql.cpuPct : null;   // % of elapsed = CPU
        const highCpuSql    = cpuFrac != null && cpuFrac > 60;
        const highGets      = domSql.gets > 50000;
        const physReadSpike = (lp2.physical_reads||0) > (lp1.physical_reads||0) * 2;
        // Contention: high elapsed, low CPU, low IO ? lock/queue, not compute
        const contentionPath = !domSql.isPlanChg && !highCpuSql && domSql.epe2 > 5
                               && (seqEv?.pct_db_time||0) < 10 && (scaEv?.pct_db_time||0) < 10;"""

NEW_IJ = """\
        const epeRatio      = domSql.epe1 > 0 ? domSql.epe2 / domSql.epe1 : 0;
        const cpuFrac       = (domSql.cpuPct != null) ? domSql.cpuPct : null;   // % of elapsed = CPU
        const highCpuSql    = cpuFrac != null && cpuFrac > 60;
        const highGets      = domSql.gets > 50000;
        // SQL-specific physical read spike (preferred over system-wide LP delta which can mask
        // per-SQL changes when other SQLs improve simultaneously)
        const physReadSpike = domSql.diskReads > 1000
            ? (domSql.diskReads1 === null || domSql.diskReads > (domSql.diskReads1||0) * 1.5)
            : ((lp2.physical_reads||0) > (lp1.physical_reads||0) * 2);  // LP fallback
        // Gets-per-row: canonical Oracle cardinality-underestimate indicator.
        // > 500 gets/row = CBO underestimated rows at a key plan step → excess index probes.
        // Only valid when gets is per-exec (buffer_gets_per_exec field was source).
        const getsPerRow     = domSql.getsIsPerExec && (domSql.rowsPerExec||0) > 0
            ? (domSql.gets / domSql.rowsPerExec) : 0;
        const highGetsPerRow = getsPerRow > 500;
        // Contention: high elapsed, low CPU, low IO, no cardinality issue → lock/queue
        const contentionPath = !domSql.isPlanChg && !highCpuSql && !highGetsPerRow && domSql.epe2 > 5
                               && (seqEv?.pct_db_time||0) < 10 && (scaEv?.pct_db_time||0) < 10;"""

assert c.count(OLD_IJ) == 1, f"FIX I+J (part2 inputs): {c.count(OLD_IJ)} matches"
c = c.replace(OLD_IJ, NEW_IJ)
print("FIX I+J (part2 inputs) applied")

# ── FIX J continued ── Update part2 cardinality branch condition ─────────────
OLD_J2 = "        } else if (highGets && highCpuSql) {\n            // -- LOGICAL I/O / CARDINALITY PATH"
NEW_J2 = "        } else if (highGets && (highCpuSql || highGetsPerRow)) {\n            // -- LOGICAL I/O / CARDINALITY PATH"

assert c.count(OLD_J2) == 1, f"FIX J2 (part2 branch): {c.count(OLD_J2)} matches"
c = c.replace(OLD_J2, NEW_J2)
print("FIX J (part2 cardinality branch) applied")

# ── FIX K ── Add rows/exec delta + gets/row annotation after part2Root+hrNote ─
OLD_K = """\
        const hrNote = (lp2.hard_parses||0) > 200
            ? ` <em>Additional note:</em> Hard parse rate of <strong>${f0(lp2.hard_parses)}/s</strong> adds shared pool CPU overhead — each hard parse invokes syntax check, privilege validation, and CBO evaluation without advancing application work.`
            : '';
        part2 = part2Root + hrNote;"""

NEW_K = """\
        const hrNote = (lp2.hard_parses||0) > 200
            ? ` <em>Additional note:</em> Hard parse rate of <strong>${f0(lp2.hard_parses)}/s</strong> adds shared pool CPU overhead — each hard parse invokes syntax check, privilege validation, and CBO evaluation without advancing application work.`
            : '';
        part2 = part2Root + hrNote;

        // -- Rows/exec delta annotation (Fix K) --------------------------------
        // Append when rows processed per execution changed materially between periods.
        // This is a key PE signal: rows/exec increase = data volume growth or selectivity change;
        // rows/exec decrease = predicate push-down, partition pruning improvement, or wrong plan.
        if (domSql.rowsPerExec != null && domSql.rowsPerExec1 != null && domSql.rowsPerExec1 > 0) {
            const _rowsRatio = domSql.rowsPerExec / domSql.rowsPerExec1;
            if (_rowsRatio >= 2) {
                part2 += ` <em style="color:#94a3b8"><strong style="color:#fbbf24">Rows/exec delta:</strong> ${Math.round(domSql.rowsPerExec1).toLocaleString()} → ${Math.round(domSql.rowsPerExec).toLocaleString()} rows per execution (${f1(_rowsRatio)}× increase). Each call is now processing materially more data. This is consistent with data volume growth crossing a threshold, a plan regression from a range scan to a full scan, or a selectivity change caused by stale statistics. Note: fixing this SQL addresses the dominant cost driver in this AWR window — secondary contributors may sustain residual elevation after the SQL is resolved.</em>`;
            } else if (_rowsRatio <= 0.3 && domSql.rowsPerExec1 > 100) {
                part2 += ` <em style="color:#94a3b8"><strong style="color:#34d399">Rows/exec delta:</strong> ${Math.round(domSql.rowsPerExec1).toLocaleString()} → ${Math.round(domSql.rowsPerExec).toLocaleString()} rows per execution — each call processes far fewer rows than baseline. If DB Time is still elevated, the overhead is in per-row cost (e.g. row-level lock contention or index probes per row), not raw data volume.</em>`;
            }
        }
        // -- Gets/row cardinality confirmation note ----------------------------
        if (highGetsPerRow && !domSql.isPlanChg) {
            part2 += ` <em style="color:#94a3b8"><strong style="color:#f87171">Cardinality indicator:</strong> ${Math.round(getsPerRow).toLocaleString()} buffer gets per row returned (threshold: >500). This confirms the optimizer's row estimate is significantly lower than actual rows processed at a key plan step — each index probe returns far fewer rows than predicted, forcing far more probes than the cost model expected. Primary investigation: compare E-Rows vs A-Rows in <code style="color:#94a3b8">V\$SQL_PLAN_STATISTICS_ALL</code> for SQL ${esc(domSqlId)}.</em>`;
        }"""

assert c.count(OLD_K) == 1, f"FIX K: {c.count(OLD_K)} matches"
c = c.replace(OLD_K, NEW_K)
print("FIX K (rows/exec delta + gets/row annotation) applied")

# ── FIX L (part 1) ── Part3 overconfidence for >= 40% SQL share ───────────────
OLD_L1 = """\
        const severity = domSqlShare >= 40
            ? `At ${f1(domSqlShare)}% DB Time, SQL ${esc(domSqlId)} alone accounts for nearly half of all database activity — <strong>resolving this single statement will directly restore baseline performance</strong> without any other changes required.`
            : `At ${f1(domSqlShare)}% DB Time, SQL ${esc(domSqlId)} is the single largest consumer — tuning it will have proportional impact, though secondary SQL contributors (${sqlAtt.slice(1,3).map(s=>s.id).filter(Boolean).join(', ') || 'see SQL tab'}) may sustain some residual elevation.`;"""

NEW_L1 = """\
        // Determine whether secondary contributors could sustain residual elevation after SQL fix.
        const _hasSecondaryContrib = _contributing.length > 0 ||
            (sqlAtt[1] && (sqlAtt[1].pctDb||0) > 5);
        const severity = domSqlShare >= 40
            ? `At ${f1(domSqlShare)}% DB Time, SQL ${esc(domSqlId)} alone accounts for nearly half of all database activity — <strong>resolving this single statement will directly eliminate the dominant cost driver</strong>.${_hasSecondaryContrib ? ` Based on this AWR window, this SQL is the primary lever; however, secondary contributors (${sqlAtt.slice(1,2).map(s=>s.id).filter(Boolean).join(', ') || _contributing[0]?.category || 'see contributing verdicts'}) may sustain residual elevation — validate with the next AWR comparison after the SQL is addressed.` : ' No secondary contributors at significant scale were detected in this AWR window.'}`
            : `At ${f1(domSqlShare)}% DB Time, SQL ${esc(domSqlId)} is the single largest consumer — tuning it will have proportional impact, though secondary SQL contributors (${sqlAtt.slice(1,3).map(s=>s.id).filter(Boolean).join(', ') || 'see SQL tab'}) may sustain some residual elevation.`;"""

assert c.count(OLD_L1) == 1, f"FIX L1: {c.count(OLD_L1)} matches"
c = c.replace(OLD_L1, NEW_L1)
print("FIX L (part3 overconfidence) applied")

# ── FIX I + J ── Part4 re-derivation — same physReadSpike + getsPerRow fixes ──
OLD_IJ4 = """\
        const _cpuFrac    = domSql?.cpuPct != null ? domSql.cpuPct : null;
        const _highCpuS   = _cpuFrac != null && _cpuFrac > 60;
        const _highGets   = (domSql?.gets||0) > 50000;
        const _physSpike  = (lp2.physical_reads||0) > (lp1.physical_reads||0)*2;
        const _contPath   = domSql && !domSql.isPlanChg && !_highCpuS && domSql.epe2>5
                            && (seqEv?.pct_db_time||0)<10 && (scaEv?.pct_db_time||0)<10;"""

NEW_IJ4 = """\
        const _cpuFrac    = domSql?.cpuPct != null ? domSql.cpuPct : null;
        const _highCpuS   = _cpuFrac != null && _cpuFrac > 60;
        const _highGets   = (domSql?.gets||0) > 50000;
        // SQL-specific physical read spike (same logic as part2 — see FIX I)
        const _physSpike  = (domSql?.diskReads||0) > 1000
            ? ((domSql.diskReads1 === null) || (domSql.diskReads > (domSql.diskReads1||0) * 1.5))
            : ((lp2.physical_reads||0) > (lp1.physical_reads||0)*2);
        // Gets/row cardinality indicator (same logic as part2 — see FIX J)
        const _getsPerRow4     = (domSql?.getsIsPerExec && (domSql?.rowsPerExec||0) > 0)
            ? ((domSql?.gets||0) / domSql.rowsPerExec) : 0;
        const _highGPR4        = _getsPerRow4 > 500;
        const _contPath   = domSql && !domSql.isPlanChg && !_highCpuS && !_highGPR4 && domSql.epe2>5
                            && (seqEv?.pct_db_time||0)<10 && (scaEv?.pct_db_time||0)<10;"""

assert c.count(OLD_IJ4) == 1, f"FIX I+J (part4 re-derive): {c.count(OLD_IJ4)} matches"
c = c.replace(OLD_IJ4, NEW_IJ4)
print("FIX I+J (part4 re-derivation) applied")

# ── FIX J ── Part4 branch conditions ─────────────────────────────────────────
OLD_J4a = "        } else if (_physSpike && !_highCpuS) {"
NEW_J4a = "        } else if (_physSpike && !_highCpuS && !_highGPR4) {"
assert c.count(OLD_J4a) == 1, f"FIX J4a: {c.count(OLD_J4a)} matches"
c = c.replace(OLD_J4a, NEW_J4a)

OLD_J4b = "        } else if (_highGets && _highCpuS) {"
NEW_J4b = "        } else if (_highGets && (_highCpuS || _highGPR4)) {"
assert c.count(OLD_J4b) == 1, f"FIX J4b: {c.count(OLD_J4b)} matches"
c = c.replace(OLD_J4b, NEW_J4b)
print("FIX J (part4 branch conditions) applied")

# ── FIX M ── Correct Oracle mechanism language: "uncommitted" → "outstanding" ─
OLD_M = "which must physically write all uncommitted redo entries from the log buffer to the online redo log file and return an acknowledgement before the session can proceed."
NEW_M = "which must physically write all outstanding redo entries from the log buffer up to and including the current commit SCN to the online redo log file, and return an acknowledgement before the session can proceed."
assert c.count(OLD_M) == 1, f"FIX M: {c.count(OLD_M)} matches"
c = c.replace(OLD_M, NEW_M)
print("FIX M (redo terminology) applied")

# ── Write ──────────────────────────────────────────────────────────────────────
with open(PATH, 'w', encoding='utf-8') as f:
    f.write(c)
print("Written OK")

# ── Syntax check ──────────────────────────────────────────────────────────────
orphaned  = len(re.findall(r'`\s*;\s*\$\{', c))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', c))
print(f'orphaned={orphaned} brokenTag={brokenTag}')
assert orphaned == 0 and brokenTag == 0, "SYNTAX CHECK FAILED"
print("Syntax check PASSED")
