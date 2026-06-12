"""
_patch_conflict_audit.py
========================
Deep conflict/consistency audit fixes for the AWR dashboard.

Three root-cause conflicts fixed:

CONFLICT-1 (CRITICAL): Enqueue verdict overrides fired on absolute bad-period
thresholds with NO baseline comparison. If HW enqueue was 20% in baseline AND
20% in problem, the dashboard declared "HWM extension contention" as a
regression and recommended PE fixes — completely FALSE. A structural workload
characteristic was being mis-diagnosed as a bottleneck regression.
FIX: Add delta gate — only override when event is materially WORSE than baseline
(+5pp for HW/TX-row/US/free-buf, +2pp for TX-index which has a lower base rate).

CONFLICT-2 (HIGH): All part1/2/3/4 narrative branches had `|| isIoBound`,
`|| isCommit`, `|| isCpuBound` fallbacks. `isIoBound = btn2 === 'io'` uses
`classifyBottleneck()` which is based on wait_class grouping — independent from
`buildEvidenceObject()` which uses dual-gate scoring (physReadsDelta > 30% AND
ioTotalPct >= 5%). When these disagree, the wrong narrative fired. Example:
`_finalPv = 'COMMIT_LOGGING'` but `isIoBound = true` → IO narrative preempts
COMMIT_LOGGING narrative. `_finalPv` from buildEvidenceObject is authoritative.
FIX: Remove all || isIoBound / || isCommit / || isCpuBound fallbacks from every
narrative branch. _finalPv is the single authoritative routing value.

CONFLICT-3 (HIGH): `_confSignals` (used to set the PROBABLE/STRONG_CANDIDATE
confidence label) accumulated signals that were structurally UNRELATED to the
current verdict. "Wait event dominance" fired if ANY top wait > 20%, even if it
was an IO wait when the verdict was COMMIT_LOGGING — an IO signal does not
corroborate COMMIT_LOGGING. Similarly, "SQL attribution" fired for non-SQL
verdicts where the SQL share is coincidental (15% SQL + COMMIT_LOGGING verdict
does not mean the SQL confirms the commit bottleneck).
FIX: Gate "Wait event dominance" and "SQL attribution" on verdict alignment —
only count them when the signal category matches the current _finalPv.
"""
import re

PATH = r'C:\Users\1039081\Downloads\cluade\awr-dashboard\backend\templates\index.html'

with open(PATH, encoding='utf-8') as f:
    c = f.read()

original_len = len(c)

# =============================================================================
# CONFLICT-1 FIX: Enqueue override delta gate
# =============================================================================

# Step 1a: Add baseline enqueue helper + baseline pcts after bufBusyPct2 line.
OLD_BUFDELTA = '    const bufBusyPct2 = sumEv(/buffer busy waits/i);\n    const hwEnqEv'
NEW_BUFDELTA = (
    '    const bufBusyPct2 = sumEv(/buffer busy waits/i);\n'
    '    // Baseline enqueue pcts — for delta gate on enqueue override conditions.\n'
    '    // An enqueue event already elevated in the GOOD period is a structural\n'
    '    // workload characteristic, not a regression — do not override the verdict for it.\n'
    '    const _ev1All = waitEvents.good || [];\n'
    '    const sumEvG = (re) => _ev1All.filter(e=>re.test(e.event_name||\'\')).reduce((s,e)=>s+(e.pct_db_time||0),0);\n'
    '    const hwEnqGoodPct   = sumEvG(/enq:\\s*HW\\s*-\\s*contention/i);\n'
    '    const txIdxGoodPct   = sumEvG(/enq:\\s*TX\\s*-\\s*index contention/i);\n'
    '    const txRowGoodPct   = sumEvG(/enq:\\s*TX\\s*-\\s*row lock/i);\n'
    '    const usEnqGoodPct   = sumEvG(/enq:\\s*US\\s*-\\s*contention/i);\n'
    '    const freeBufGoodPct = sumEvG(/free buffer waits/i);\n'
    '    const hwEnqEv'
)
assert c.count(OLD_BUFDELTA) == 1, f"BUFDELTA: {c.count(OLD_BUFDELTA)} occurrences"
c = c.replace(OLD_BUFDELTA, NEW_BUFDELTA)
print("✓ CONFLICT-1a: Added baseline enqueue pct helpers")

# Step 1b: Replace the 5-line enqueue override block with delta-gated version.
OLD_OVERRIDE = (
    '    // Override: when a serialisation enqueue dominates DB Time, the real\n'
    '    // verdict is the wait, not the SQL — the SQL is a symptom carrier.\n'
    '    if      (hwEnqPct  >= 15) _finalPv = \'HW_ENQUEUE_CONTENTION\';\n'
    '    else if (txIdxPct  >= 5)  _finalPv = \'TX_INDEX_CONTENTION\';\n'
    '    else if (txRowPct  >= 10) _finalPv = \'TX_ROW_LOCK_CONTENTION\';\n'
    '    else if (usEnqPct  >= 10) _finalPv = \'UNDO_SEGMENT_EXTENSION\';\n'
    '    else if (freeBufPct2 >= 15) _finalPv = \'BUFFER_WRITE_PRESSURE\';\n'
)
NEW_OVERRIDE = (
    '    // Override: when a serialisation enqueue NEWLY or materially dominates DB Time,\n'
    '    // the real verdict is the wait, not the SQL — the SQL is a symptom carrier.\n'
    '    // DELTA GATE: only override when the event is NEW or materially WORSE than baseline\n'
    '    // (+5pp threshold; +2pp for TX-index which has a lower natural base rate).\n'
    '    // This prevents a structural workload characteristic (same level in both periods)\n'
    '    // from being mis-diagnosed as a regression and triggering incorrect PE actions.\n'
    '    if      (hwEnqPct  >= 15 && hwEnqPct  > hwEnqGoodPct   + 5)  _finalPv = \'HW_ENQUEUE_CONTENTION\';\n'
    '    else if (txIdxPct  >= 5  && txIdxPct  > txIdxGoodPct   + 2)  _finalPv = \'TX_INDEX_CONTENTION\';\n'
    '    else if (txRowPct  >= 10 && txRowPct  > txRowGoodPct   + 5)   _finalPv = \'TX_ROW_LOCK_CONTENTION\';\n'
    '    else if (usEnqPct  >= 10 && usEnqPct  > usEnqGoodPct   + 5)  _finalPv = \'UNDO_SEGMENT_EXTENSION\';\n'
    '    else if (freeBufPct2 >= 15 && freeBufPct2 > freeBufGoodPct + 5) _finalPv = \'BUFFER_WRITE_PRESSURE\';\n'
)
assert c.count(OLD_OVERRIDE) == 1, f"OVERRIDE: {c.count(OLD_OVERRIDE)} occurrences"
c = c.replace(OLD_OVERRIDE, NEW_OVERRIDE)
print("✓ CONFLICT-1b: Enqueue override delta gate applied")

# =============================================================================
# CONFLICT-2 FIX: Remove all || isIoBound / || isCommit / || isCpuBound
# fallbacks from narrative branch conditions.
# _finalPv (from buildEvidenceObject) is the single authoritative routing value.
# These fallbacks created false-positive narrative fires when the backend
# bottleneck classifier (classifyBottleneck, wait_class-based) disagreed with
# buildEvidenceObject's dual-gate scoring.
# =============================================================================

# Count before replacement
io_count   = c.count(' || isIoBound')
com_count  = c.count(' || isCommit')
cpu_count  = c.count(' || isCpuBound')
print(f"  Removing || isIoBound ({io_count} occurrences), || isCommit ({com_count}), || isCpuBound ({cpu_count})")

c = c.replace(' || isIoBound', '')
c = c.replace(' || isCommit', '')
c = c.replace(' || isCpuBound', '')

print("✓ CONFLICT-2: Removed all || isIoBound / || isCommit / || isCpuBound fallbacks")
print(f"  Removed: {io_count} IO, {com_count} Commit, {cpu_count} CPU fallbacks ({io_count+com_count+cpu_count} total)")

# =============================================================================
# CONFLICT-3 FIX: Make _confSignals verdict-relevant
# "Wait event dominance" and "SQL attribution" must align with _finalPv
# before they count as confidence-boosting signals.
# =============================================================================

OLD_CONFSIG = (
    '    const _confSignals = [];\n'
    '    if (topWaitPct > 20)                                _confSignals.push(\'Wait event dominance\');\n'
    '    if (domSqlShare > 15)                               _confSignals.push(\'SQL attribution\');\n'
    '    if (_lpCrit.filter(c => c.d > 0).length > 0)        _confSignals.push(\'Load profile shift\');\n'
    '    if (_ieCrit.length > 0)                             _confSignals.push(\'Efficiency degradation\');\n'
    '    if (addmCtx.length > 0)                             _confSignals.push(\'ADDM confirmation\');\n'
    '    if (aas2 > 0 && cpus > 0 && aas2 > cpus * 0.9)     _confSignals.push(\'AAS at/near saturation\');\n'
    '    if (_sigNew.length > 0)                             _confSignals.push(\'New wait events in problem period\');'
)
NEW_CONFSIG = (
    '    const _confSignals = [];\n'
    '    // "Wait event dominance" only counts when the top wait is in the SAME category\n'
    '    // as _finalPv. An IO wait at 22% does not corroborate a COMMIT_LOGGING verdict;\n'
    '    // including it as a confidence signal inflates certainty on the wrong bottleneck.\n'
    '    const _topWaitFitsVerdict = (() => {\n'
    '        if (!topWait) return false;\n'
    '        const tn = topWait.event_name || \'\';\n'
    '        if (isSqlVerdict)                                     return true;\n'
    '        if (_finalPv === \'IO_BOTTLENECK\')                    return /db file|direct path|cell smart/i.test(tn);\n'
    '        if (_finalPv === \'COMMIT_LOGGING\')                   return /log file sync|log buffer|log switch/i.test(tn);\n'
    '        if (_finalPv === \'CONCURRENCY\')                      return /latch|buffer busy|enq:|gc |mutex|cursor.*pin/i.test(tn);\n'
    '        if (_finalPv === \'CPU_SATURATION\')                   return /DB CPU|cursor.*pin|resmgr/i.test(tn);\n'
    '        if (_finalPv === \'HW_ENQUEUE_CONTENTION\')            return /enq:\\s*HW/i.test(tn);\n'
    '        if (_finalPv === \'TX_INDEX_CONTENTION\')              return /enq:\\s*TX.*index/i.test(tn);\n'
    '        if (_finalPv === \'TX_ROW_LOCK_CONTENTION\')           return /enq:\\s*TX.*row lock/i.test(tn);\n'
    '        if (_finalPv === \'UNDO_SEGMENT_EXTENSION\')           return /enq:\\s*US/i.test(tn);\n'
    '        if (_finalPv === \'BUFFER_WRITE_PRESSURE\')            return /free buffer waits/i.test(tn);\n'
    '        return topWaitPct > 20;\n'
    '    })();\n'
    '    // "SQL attribution" is a confidence signal only when the SQL drives the\n'
    '    // bottleneck category. For COMMIT_LOGGING or CONCURRENCY, a 18% DB-Time SQL\n'
    '    // is coincidental — it does not confirm log-writer pressure or latch contention.\n'
    '    const _sqlFitsVerdict = isSqlVerdict ||\n'
    '        _finalPv === \'IO_BOTTLENECK\' || _finalPv === \'CPU_SATURATION\' ||\n'
    '        _finalPv === \'HW_ENQUEUE_CONTENTION\' || _finalPv === \'BUFFER_WRITE_PRESSURE\';\n'
    '    if (topWaitPct > 20 && _topWaitFitsVerdict)             _confSignals.push(\'Wait event dominance\');\n'
    '    if (domSqlShare > 15 && _sqlFitsVerdict)               _confSignals.push(\'SQL attribution\');\n'
    '    if (_lpCrit.filter(c => c.d > 0).length > 0)           _confSignals.push(\'Load profile shift\');\n'
    '    if (_ieCrit.length > 0)                                _confSignals.push(\'Efficiency degradation\');\n'
    '    if (addmCtx.length > 0)                                _confSignals.push(\'ADDM confirmation\');\n'
    '    if (aas2 > 0 && cpus > 0 && aas2 > cpus * 0.9)        _confSignals.push(\'AAS at/near saturation\');\n'
    '    if (_sigNew.length > 0)                                _confSignals.push(\'New wait events in problem period\');'
)
assert c.count(OLD_CONFSIG) == 1, f"CONFSIG: {c.count(OLD_CONFSIG)} occurrences"
c = c.replace(OLD_CONFSIG, NEW_CONFSIG)
print("✓ CONFLICT-3: _confSignals verdict-alignment gate applied")

# =============================================================================
# VERIFY MANDATORY SYNTAX INVARIANTS
# =============================================================================
orphaned  = len(re.findall(r'`\s*;\s*\$\{', c))
brokenTag = len(re.findall(r'`<[a-z]{1,4}\(', c))
print(f"\n--- SYNTAX CHECK ---")
print(f"orphaned backtick-semicolons:  {orphaned}  (must be 0)")
print(f"broken template-tag patterns:  {brokenTag}  (must be 0)")
assert orphaned == 0,  "SYNTAX ERROR: orphaned backtick-semicolons found!"
assert brokenTag == 0, "SYNTAX ERROR: broken template-tag patterns found!"
print(f"File size change: {original_len} → {len(c)} ({len(c)-original_len:+d} chars)")

with open(PATH, 'w', encoding='utf-8') as f:
    f.write(c)

print("\n✅ _patch_conflict_audit.py applied successfully — all 3 conflicts fixed")
print("   CONFLICT-1: Enqueue override delta gate (prevents structural-characteristic mis-diagnosis)")
print("   CONFLICT-2: Removed || isIoBound/isCommit/isCpuBound fallbacks (prevents narrative route hijack)")
print("   CONFLICT-3: _confSignals verdict-alignment gate (prevents confidence inflation from unrelated signals)")
