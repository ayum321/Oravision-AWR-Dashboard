"""
Fix: Add guard rails for DB Time decrease and structural similarity in verdict engine.

GR-9: Structural similarity — COMMIT_LOGGING disqualified if log file sync % was 
      already high in Good period (within 5pp) AND DB Time did not increase.
GR-10: DB Time decrease — suppress all regression-oriented verdicts when DB Time
       decreased substantially and no clear regression signal (per-exec) exists.
"""
import re

path = 'backend/templates/index.html'
content = open(path, encoding='utf-8').read()

# Step 1: Add _waitPctGood helper after _waitPct definition
old_waitpct = """    const _waitPct = (pat) => badWaits
        .filter(w => new RegExp(pat,'i').test(w.event_name||''))
        .reduce((s,w) => s+(w.pct_db_time||0), 0);"""

new_waitpct = """    const _waitPct = (pat) => badWaits
        .filter(w => new RegExp(pat,'i').test(w.event_name||''))
        .reduce((s,w) => s+(w.pct_db_time||0), 0);
    const _waitPctGood = (pat) => goodWaits
        .filter(w => new RegExp(pat,'i').test(w.event_name||''))
        .reduce((s,w) => s+(w.pct_db_time||0), 0);"""

assert old_waitpct in content, "_waitPct pattern not found"
content = content.replace(old_waitpct, new_waitpct, 1)
print("Added _waitPctGood helper")

# Step 2: Add GR-9 and GR-10 after GR-8
old_gr8_end = """    // GR-8: Connection management decreased ? LOGON_STORM impossible
    if (connMgmtGoodPct > 0.1 && connMgmtBadPct < connMgmtGoodPct * 0.5) {
        _disq('LOGON_STORM', `Impossible: connection management DB Time DECREASED from ${connMgmtGoodPct.toFixed(2)}% to ${connMgmtBadPct.toFixed(2)}%. Storm requires elevated connection overhead.`);
    }

    // ---------------------------------------------------------------
    // SECTION 7"""

# Build GR-9 and GR-10
new_gr8_end = """    // GR-8: Connection management decreased ? LOGON_STORM impossible
    if (connMgmtGoodPct > 0.1 && connMgmtBadPct < connMgmtGoodPct * 0.5) {
        _disq('LOGON_STORM', `Impossible: connection management DB Time DECREASED from ${connMgmtGoodPct.toFixed(2)}% to ${connMgmtBadPct.toFixed(2)}%. Storm requires elevated connection overhead.`);
    }
    // GR-9: Structural similarity — COMMIT_LOGGING suppressed if log file sync
    // was already high in the Good period (within 5pp) and did not worsen materially.
    // This prevents labelling a structural workload characteristic as a regression.
    {
        const _lfsPctGood = _waitPctGood('log file sync');
        const _lfsDelta = logFileSyncPct - _lfsPctGood;
        if (_lfsPctGood >= 3 && _lfsDelta < 5) {
            _disq('COMMIT_LOGGING', `Structural: log file sync was already ${_lfsPctGood.toFixed(1)}% in baseline (bad: ${logFileSyncPct.toFixed(1)}%, delta: ${_lfsDelta.toFixed(1)}pp). This is a workload characteristic, not a regression.`);
        }
    }
    // GR-10: DB Time decrease — when DB Time dropped >10% and no dominant SQL
    // or per-exec regression exists, suppress regression-oriented verdicts.
    // The comparison is not detecting a problem — there is no problem to diagnose.
    if (dtChange < -10 && !isDominant && !isExecReg) {
        const _suppressList = ['CPU_SATURATION','IO_BOTTLENECK','COMMIT_LOGGING','CONCURRENCY','WORKLOAD_GROWTH'];
        for (const _sv of _suppressList) {
            _disq(_sv, `DB Time DECREASED ${Math.abs(dtChange).toFixed(0)}% — no regression to diagnose. ${_sv} is a structural observation, not a problem signal.`);
        }
    }

    // ---------------------------------------------------------------
    // SECTION 7"""

# Check the arrow character is right
assert old_gr8_end in content, f"GR-8 end pattern not found. Looking for 'GR-8'..."
content = content.replace(old_gr8_end, new_gr8_end, 1)
print("Added GR-9 (structural similarity) and GR-10 (DB Time decrease)")

# Step 3: Also need to make dtChange available in the scoring function
# Check if dtChange is already destructured and available
dtchange_check = "dtChange=0,txDelta=0"
assert dtchange_check in content, "dtChange not found in function params"
print("dtChange already available in function scope")

# Step 4: Check isExecReg availability
exec_reg_check = "const isExecReg  = topCls === 'EXEC_REGRESSION'"
assert exec_reg_check in content, "isExecReg not found"
print("isExecReg already available")

# Write the fixed file
from pathlib import Path
Path(path).write_text(content, encoding='utf-8')
print(f"\nDone. File saved ({len(content)} chars)")

# Verify the fix
assert '_waitPctGood' in content
assert 'GR-9' in content
assert 'GR-10' in content
assert 'Structural: log file sync' in content
assert 'DB Time DECREASED' in content
print("All assertions passed")
