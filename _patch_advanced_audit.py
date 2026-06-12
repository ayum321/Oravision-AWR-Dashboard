"""
Advanced audit patch — 4 targeted fixes.

BUG A (HIGH): _buildVerdictSignalScore sigKey fallback
  TX_INDEX_CONTENTION / TX_ROW_LOCK_CONTENTION fall back to 'CPU_SATURATION'
  scorecard because they are not in SIGNALS{}. Shows wrong diagnostic checklist.
  Fix: map to CONCURRENCY; UNDO_SEGMENT_EXTENSION → COMMIT_LOGGING;
       BUFFER_WRITE_PRESSURE → IO_BOTTLENECK.

BUG B (MEDIUM): PARALLEL_EXPANSION has no part1/part2/part3 narrative path.
  When _finalPv is set to 'PARALLEL_EXPANSION' the entire narrative falls
  into the generic else-branch ("significant increase in database workload
  intensity"). CPU_SATURATION narrative already has a _parallelMask branch
  that correctly handles this case.
  Fix: map PARALLEL_EXPANSION to CPU_SATURATION at the _finalPv override site.

BUG C (MEDIUM): domSql / domSqlShare mismatch when evidence SQL ID absent from sql2.
  If _ev.dominantSQL (_sqlId) doesn't exist in the bad-period sql_stats,
  domSql falls back to topSql but domSqlShare still uses _sqlShare (a share
  that belongs to _sqlId, not topSql). The narrative describes the wrong SQL
  at the wrong share percentage.
  Fix: derive _domSqlExact separately; when falling back to topSql, use
       topSql.pctDb for domSqlShare.

BUG D (LOW-MEDIUM): physDelta in scorecard uses 0 when baseline physical_reads=0
  but the main classifier (_pct helper) uses 200 in that case (indicating
  new physical I/O with no baseline). scorecard "Physical reads spike > 50%"
  stays unfired even when baseline=0 and bad period has significant reads.
  Fix: match the main classifier sentinel (200) in the scorecard computation.
"""

import re

PATH = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'
f = open(PATH, encoding='utf-8')
c = f.read()
f.close()

# ── BUG A ── map non-SIGNALS verdicts to correct scorecard ────────────────────
OLD_A = "    var sigKey = SQL_VERDICTS.indexOf(finalPv) >= 0 ? 'SQL_VERDICT' : (SIGNALS[finalPv] ? finalPv : 'CPU_SATURATION');"

NEW_A = """\
    // Verdict-to-scorecard map for verdicts that don't have their own SIGNALS entry.
    // These share their diagnostic checklist with the closest structural analogue.
    var VERDICT_SCORECARD_MAP = {
        'TX_INDEX_CONTENTION':    'CONCURRENCY',    // TX enqueue = serialisation class
        'TX_ROW_LOCK_CONTENTION': 'CONCURRENCY',    // TX enqueue = serialisation class
        'UNDO_SEGMENT_EXTENSION': 'COMMIT_LOGGING', // undo pressure = redo/DML volume class
        'BUFFER_WRITE_PRESSURE':  'IO_BOTTLENECK',  // DBWR saturation = I/O throughput class
        'PARALLEL_EXPANSION':     'CPU_SATURATION', // PX worker inflation = CPU demand class
    };
    var sigKey = SQL_VERDICTS.indexOf(finalPv) >= 0 ? 'SQL_VERDICT'
               : (SIGNALS[finalPv] ? finalPv
               : (VERDICT_SCORECARD_MAP[finalPv] || 'CPU_SATURATION'));"""

assert c.count(OLD_A) == 1, f"BUG A: expected 1 match, got {c.count(OLD_A)}"
c = c.replace(OLD_A, NEW_A)
print("BUG A applied")

# ── BUG B ── PARALLEL_EXPANSION → CPU_SATURATION (has no narrative path) ─────
OLD_B = "        _finalPv = _parallel ? 'PARALLEL_EXPANSION' : 'CPU_SATURATION';"

NEW_B = """\
        // PARALLEL_EXPANSION has no dedicated part1/part2/part3 narrative path.
        // CPU_SATURATION already has a _parallelMask branch that describes
        // PX worker inflation correctly — use it as the narrative vehicle.
        _finalPv = 'CPU_SATURATION';\
"""

assert c.count(OLD_B) == 1, f"BUG B: expected 1 match, got {c.count(OLD_B)}"
c = c.replace(OLD_B, NEW_B)
print("BUG B applied")

# ── BUG C ── domSql / domSqlShare consistency ──────────────────────────────────
OLD_C = """\
    const domSqlId = _sqlId || (topSql?.id) || '';
    const domSqlShare = _sqlShare > 0 ? _sqlShare : (topSql?.pctDb||0);
    const domSql = sqlAtt.find(s=>s.id===domSqlId) || topSql;"""

NEW_C = """\
    const domSqlId = _sqlId || (topSql?.id) || '';
    // Resolve domSql exactly so domSqlShare always matches domSql.
    // If _sqlId from evidence doesn't appear in the bad-period sql_stats
    // (e.g. the SQL only ran in the baseline), fall back to topSql and use
    // topSql's own share — prevents describing topSql with a mismatched share.
    const _domSqlExact  = sqlAtt.find(s => s.id === domSqlId);
    const domSql        = _domSqlExact || topSql;
    const domSqlShare   = _domSqlExact
        ? (_sqlShare > 0 ? _sqlShare : (_domSqlExact.pctDb || 0))
        : (topSql?.pctDb || 0);"""

assert c.count(OLD_C) == 1, f"BUG C: expected 1 match, got {c.count(OLD_C)}"
c = c.replace(OLD_C, NEW_C)
print("BUG C applied")

# ── BUG D ── physDelta sentinel in scorecard matches main classifier ───────────
OLD_D = "    var physDelta = lp1.physical_reads > 0.001 ? ((lp2.physical_reads||0)-(lp1.physical_reads||0))/(lp1.physical_reads)*100 : 0;"

NEW_D = "    var physDelta = lp1.physical_reads > 0.001 ? ((lp2.physical_reads||0)-(lp1.physical_reads||0))/(lp1.physical_reads)*100 : ((lp2.physical_reads||0) > 0 ? 200 : 0);"

assert c.count(OLD_D) == 1, f"BUG D: expected 1 match, got {c.count(OLD_D)}"
c = c.replace(OLD_D, NEW_D)
print("BUG D applied")

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
